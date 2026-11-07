from io import BytesIO
import os
from collections import defaultdict
from pathlib import Path
import pandas as pd
from sqlalchemy.orm import Session
from app.db import Base, engine, get_db
from app import models
from pydantic import BaseModel
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse


BASE_DIR = Path(__file__).resolve().parent.parent

Base.metadata.create_all(bind=engine)
app = FastAPI(title="StockPilot API")

# Spark Admin theme assets (CSS / JS / libs / images)
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "dashboard" / "assets")),
    name="static",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _month_series(months: int = 8):
    """Return the last N (year, month) keys, oldest first."""
    today = datetime.utcnow()
    keys = []
    for i in range(months - 1, -1, -1):
        month = today.month - i
        year = today.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        keys.append((year, month))
    return keys


@app.get("/")
def dashboard(request: Request, email_sent: bool = False, upload_success: bool = False,
              deleted: bool = False, updated: bool = False, product_added: bool = False, db: Session = Depends(get_db)):
    # Database se saare products nikaalein
    products_query = db.query(models.Product).all()
    products = []
    for p in products_query:
        for v in p.variants:
            products.append({
                "variant_id": v.id,
                "product": p.name,
                "variant": v.name,
                "sku": v.sku or "",
                "stock": v.stock_qty,
                "reorder_point": p.reorder_point
            })

    # Low stock alerts nikaalein
    alerts_query = db.query(models.Product, models.Variant).join(models.Variant).filter(
        models.Variant.stock_qty <= models.Product.reorder_point
    ).all()
    alerts = []
    for p, v in alerts_query:
        alerts.append({
            "product": p.name,
            "variant": v.name,
            "current_stock": v.stock_qty
        })

    # ------------------------- Dashboard statistics -------------------------
    total_products = len(products_query)
    total_variants = len(products)
    total_stock = sum(p["stock"] for p in products)
    low_stock_items = [p for p in products if p["stock"] <= p["reorder_point"]]
    out_of_stock_items = [p for p in products if p["stock"] <= 0]
    low_stock_count = len(low_stock_items)
    healthy_count = max(total_variants - low_stock_count, 0)
    stock_health = {
        "healthy": healthy_count,
        "low": max(low_stock_count - len(out_of_stock_items), 0),
        "out": len(out_of_stock_items),
    }

    # Recent stock movements (sale / purchase)
    recent_rows = (
        db.query(models.StockMovement, models.Variant, models.Product)
        .join(models.Variant, models.StockMovement.variant_id == models.Variant.id)
        .join(models.Product, models.Variant.product_id == models.Product.id)
        .order_by(models.StockMovement.created_at.desc())
        .limit(6)
        .all()
    )
    recent_movements = []
    for m, v, p in recent_rows:
        recent_movements.append({
            "type": m.type,
            "qty": m.qty,
            "product": p.name,
            "variant": v.name,
            "date": m.created_at,
        })

    # Last 8 months sale vs purchase chart
    keys = _month_series(8)
    start_date = datetime(keys[0][0], keys[0][1], 1)
    movements = db.query(models.StockMovement).filter(
        models.StockMovement.created_at >= start_date
    ).all()
    sales_map = defaultdict(int)
    purchase_map = defaultdict(int)
    for m in movements:
        key = (m.created_at.year, m.created_at.month)
        if m.type == "sale":
            sales_map[key] += m.qty
        elif m.type == "purchase":
            purchase_map[key] += m.qty
    chart_labels = [datetime(y, mo, 1).strftime("%b") for y, mo in keys]
    chart_sales = [sales_map[k] for k in keys]
    chart_purchases = [purchase_map[k] for k in keys]

    # Product overview (top products by stock)
    overview_sorted = sorted(products, key=lambda x: x["stock"], reverse=True)[:6]
    max_stock = max([x["stock"] for x in overview_sorted], default=0) or 1
    product_overview = []
    for item in overview_sorted:
        pct = int(round(min(item["stock"] / max_stock * 100, 100)))
        if item["stock"] <= 0:
            status = "out"
        elif item["stock"] <= item["reorder_point"]:
            status = "low"
        else:
            status = "healthy"
        product_overview.append({**item, "percent": pct, "status": status})

    # HTML file ko return karein data ke saath
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "products": products,
            "alerts": alerts,
            "email_sent": email_sent,
            "upload_success": upload_success,
            "deleted": deleted,
            "updated": updated,
            "product_added": product_added,
            "total_products": total_products,
            "total_variants": total_variants,
            "total_stock": total_stock,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": len(out_of_stock_items),
            "stock_health": stock_health,
            "recent_movements": recent_movements,
            "chart_labels": chart_labels,
            "chart_sales": chart_sales,
            "chart_purchases": chart_purchases,
            "product_overview": product_overview,
        }
    )
@app.post("/upload-excel/")
async def upload_excel(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    # 1. Check file format
    if not file.filename.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(status_code=400, detail="Sirf .xlsx ya .csv file allow hai")

    # 2. Read the file
    content = await file.read()
    try:
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
        else:
            df = pd.read_excel(BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File read nahi ho saki: {str(e)}")

    # 3. Check required columns
    required_cols = {"product_name", "opening_stock"}
    if not required_cols.issubset(df.columns):
        raise HTTPException(status_code=400, detail=f"File mein yeh columns hone chahiye: {required_cols}")

    # 4. Save to database
    created_count = 0
    for _, row in df.iterrows():
        name = str(row["product_name"]).strip()
        if not name or name.lower() == "nan":
            continue

        product = models.Product(
            user_id=1, # Abhi ke liye test user 1
            name=name,
            category=str(row.get("category", "General")).strip(),
            cost_price=float(row.get("cost_price", 0) or 0),
            sell_price=float(row.get("sell_price", 0) or 0),
            reorder_point=int(row.get("reorder_point", 5) or 5)
        )
        
        variant = models.Variant(
            name=str(row.get("variant_name", "Default")).strip(),
            sku=str(row.get("sku", "")).strip(),
            stock_qty=int(row.get("opening_stock", 0) or 0)
        )
        
        product.variants.append(variant)
        db.add(product)
        created_count += 1

    db.commit()
    # return {"message": "File upload ho gayi!", "products_added": created_count}
    return RedirectResponse(url="/?upload_success=true", status_code=303)


@app.get("/products/")
def get_products(db: Session = Depends(get_db)):
    products = db.query(models.Product).all()
    result = []
    for p in products:
        for v in p.variants:
            result.append({
                "id": p.id,
                "product": p.name,
                "variant": v.name,
                "stock": v.stock_qty,
                "reorder_point": p.reorder_point
            })
    return result


@app.get("/alerts/low-stock/")
def low_stock_alerts(db: Session = Depends(get_db)):
    # Un products ko dhoondein jinka stock reorder point se kam ya barabar hai
    alerts = db.query(models.Product, models.Variant).join(models.Variant).filter(
        models.Variant.stock_qty <= models.Product.reorder_point
    ).all()
    
    result = []
    for p, v in alerts:
        result.append({
            "product": p.name,
            "variant": v.name,
            "current_stock": v.stock_qty,
            "reorder_point": p.reorder_point,
            "message": f"{p.name} ({v.name}) khatam hone wala hai! Sirf {v.stock_qty} bache hain."
        })
    return result


# Request ka format set karna
class MovementRequest(BaseModel):
    variant_id: int
    qty: int

@app.post("/movement/sale/")
def record_sale(req: MovementRequest, db: Session = Depends(get_db)):
    variant = db.query(models.Variant).filter(models.Variant.id == req.variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Yeh Variant ID nahi mili")
    
    if variant.stock_qty < req.qty:
        raise HTTPException(status_code=400, detail="Itna stock available nahi hai!")
    
    # Stock kam karein
    variant.stock_qty -= req.qty
    movement = models.StockMovement(variant_id=variant.id, type="sale", qty=req.qty)
    
    db.add(movement)
    db.commit()
    return {"message": "Sale record ho gayi", "new_stock": variant.stock_qty}

@app.post("/movement/purchase/")
def record_purchase(req: MovementRequest, db: Session = Depends(get_db)):
    variant = db.query(models.Variant).filter(models.Variant.id == req.variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Yeh Variant ID nahi mili")
    
    # Stock barhayein
    variant.stock_qty += req.qty
    movement = models.StockMovement(variant_id=variant.id, type="purchase", qty=req.qty)
    
    db.add(movement)
    db.commit()
    return {"message": "Purchase record ho gayi", "new_stock": variant.stock_qty}




@app.get("/history/{variant_id}")
def get_sales_history(variant_id: int, db: Session = Depends(get_db)):
    # Us product ki saari sales nikaalein
    movements = db.query(models.StockMovement).filter(
        models.StockMovement.variant_id == variant_id,
        models.StockMovement.type == "sale"
    ).order_by(models.StockMovement.created_at.desc()).all()
    
    return [{"date": m.created_at, "qty_sold": m.qty} for m in movements]

@app.get("/forecast/{variant_id}")
def get_forecast(variant_id: int, db: Session = Depends(get_db)):
    # 1. Pichlay 30 din ki sales check karein
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    sales = db.query(models.StockMovement).filter(
        models.StockMovement.variant_id == variant_id,
        models.StockMovement.type == "sale",
        models.StockMovement.created_at >= thirty_days_ago
    ).all()
    
    total_sold = sum(s.qty for s in sales)
    
    # 2. Simple Average nikaalein (Total bika / 30 din)
    avg_daily_sales = total_sold / 30.0
    
    # 3. Aglay 7 din ka andaza lagayein
    predicted_next_7_days = round(avg_daily_sales * 7)
    
    # Product ki current stock check karein
    variant = db.query(models.Variant).filter(models.Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant nahi mila")
        
    product = db.query(models.Product).filter(models.Product.id == variant.product_id).first()
    
    # 4. Decision (Kya stock kaafi hai ya nahi)
    status = "Stock Kaafi Hai"
    if predicted_next_7_days > variant.stock_qty:
        status = "KHATAM HONE WALA HAI! Foran mangwayen."

    return {
        "product": product.name,
        "variant": variant.name,
        "current_stock": variant.stock_qty,
        "last_30_days_sales": total_sold,
        "average_daily_sales": round(avg_daily_sales, 2),
        "prediction_next_7_days": predicted_next_7_days,
        "status": status
    }

@app.get("/daily-summary/")
def generate_daily_summary(db: Session = Depends(get_db)):
    # 1. Un products ko dhoondein jinka stock khatam hone wala hai
    alerts = db.query(models.Product, models.Variant).join(models.Variant).filter(
        models.Variant.stock_qty <= models.Product.reorder_point
    ).all()
    
    if not alerts:
        return {"whatsapp_message": "StockPilot Report:\n\nSab theek hai! Aaj koi item khatam nahi ho raha. 👍"}

    # 2. Message tayyar karein (WhatsApp format mein)
    message = "📦 *StockPilot Daily Summary*\n\n"
    message += "⚠️ *Yeh items khatam hone wale hain:*\n"
    
    for p, v in alerts:
        # Har item ke liye andaza lagayein (simple logic)
        message += f"▪️ {p.name} ({v.name}): Sirf {v.stock_qty} bache hain.\n"
    
    message += "\nMeharbani farma kar foran inka order lagwayen! 🛒"
    
    return {
        "status": "Message Ready",
        "whatsapp_message": message
    }



# Email Settings (values .env file se aati hain, code me secrets nahi)
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL", "")

@app.get("/send-email-report/")
def send_email_report():
    db = next(get_db())
    alerts = db.query(models.Product, models.Variant).join(models.Variant).filter(
        models.Variant.stock_qty <= models.Product.reorder_point
    ).all()

    message_body = "📦 StockPilot Daily Summary\n\n"
    if alerts:
        message_body += "⚠️ Yeh items khatam hone wale hain:\n"
        for p, v in alerts:
            message_body += f"▪️ {p.name} ({v.name}): Sirf {v.stock_qty} bache hain.\n"
        message_body += "\nMeharbani farma kar foran inka order lagwayen! 🛒"
    else:
        message_body = "StockPilot Report:\n\nSab theek hai! Aaj koi item khatam nahi ho raha. 👍"

    # Email tayyar karna
    msg = MIMEText(message_body)
    msg['Subject'] = 'StockPilot - Daily Alerts'
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL

    # Email bhejna
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
             # Email kamyabi se jane par wapas Dashboard par bhejein
        return RedirectResponse(url="/?email_sent=true", status_code=303)
    except Exception as e:
        # Agar error aaye to JSON message dikhayein
        return {"status": "Email nahi gayi", "error": str(e)}

@app.get("/delete-variant/{variant_id}")
def delete_variant(variant_id: int, db: Session = Depends(get_db)):
    # Pehle us variant ki sales history (movements) delete karein
    db.query(models.StockMovement).filter(models.StockMovement.variant_id == variant_id).delete()
    
    # Phir variant delete karein
    variant = db.query(models.Variant).filter(models.Variant.id == variant_id).first()
    if variant:
        db.delete(variant)
        db.commit()
        
    return RedirectResponse(url="/?deleted=true", status_code=303)

@app.get("/edit-variant/{variant_id}")
def edit_variant_page(variant_id: int, request: Request, db: Session = Depends(get_db)):
    # Database se variant aur product nikaalein
    variant = db.query(models.Variant).filter(models.Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant nahi mila")
        
    product = db.query(models.Product).filter(models.Product.id == variant.product_id).first()
    
    # Purana data form mein dikhane ke liye tayyar karein
    data = {
        "variant_id": variant.id,
        "product_name": product.name,
        "variant_name": variant.name,
        "sku": variant.sku or "",
        "reorder_point": product.reorder_point,
        "stock": variant.stock_qty,  # <--- Yeh line add karein
    }
    
    return templates.TemplateResponse(
        request=request,
        name="edit.html",
        context={"p": data}
    )

@app.post("/edit-variant/{variant_id}")
def update_variant(
    variant_id: int,
    product_name: str = Form(...),
    variant_name: str = Form(...),
    sku: str = Form(None),
    reorder_point: int = Form(...),
    stock: int = Form(...),  # <--- Yeh line add karein
    db: Session = Depends(get_db)
):
    variant = db.query(models.Variant).filter(models.Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant nahi mila")
    
    product = db.query(models.Product).filter(models.Product.id == variant.product_id).first()
    
    # Data Update karein
    product.name = product_name
    product.reorder_point = reorder_point
    variant.name = variant_name
    variant.sku = sku
    variant.stock_qty = stock  # <--- Yeh line add karein
    
    db.commit()
    
    return RedirectResponse(url="/?updated=true", status_code=303)

@app.post("/add-product/")
def add_product_manual(
    product_name: str = Form(...),
    variant_name: str = Form(...),
    sku: str = Form(None),
    stock: int = Form(...),
    reorder_point: int = Form(5),
    db: Session = Depends(get_db)
):
    # Naya Product banayein
    product = models.Product(
        user_id=1,
        name=product_name,
        reorder_point=reorder_point,
        cost_price=0,
        sell_price=0
    )
    # Naya Variant banayein
    variant = models.Variant(
        name=variant_name,
        sku=sku,
        stock_qty=stock
    )
    product.variants.append(variant)
    db.add(product)
    db.commit()

    return RedirectResponse(url="/?product_added=true", status_code=303)