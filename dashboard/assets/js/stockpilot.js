/*
=======================================================================
   STOCKPILOT DASHBOARD CONTROLLER
   Built on the Spark Admin design system (Bootstrap 5 + ApexCharts)
=======================================================================
*/

document.addEventListener('DOMContentLoaded', function () {
    const cfg = window.STOCKPILOT || {};

    // -----------------------------------------------------------------
    // 1. Sidebar (mobile toggle + desktop minimize)
    // -----------------------------------------------------------------
    const sidebar = document.querySelector('.sidebar-wrapper');
    const toggleBtn = document.querySelector('.sidebar-toggle-btn');

    let overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    document.body.appendChild(overlay);

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            sidebar.classList.toggle('show');
            overlay.classList.toggle('show', sidebar.classList.contains('show'));
        });

        overlay.addEventListener('click', function () {
            sidebar.classList.remove('show');
            overlay.classList.remove('show');
        });
    }

    const desktopToggleBtn = document.querySelector('#desktop-sidebar-toggle');
    if (desktopToggleBtn) {
        desktopToggleBtn.addEventListener('click', function () {
            document.body.classList.toggle('sidebar-minimized');
            const icon = desktopToggleBtn.querySelector('i');
            if (icon) {
                icon.className = document.body.classList.contains('sidebar-minimized')
                    ? 'bi bi-chevron-bar-right'
                    : 'bi bi-chevron-bar-left';
            }
            setTimeout(function () {
                window.dispatchEvent(new Event('resize'));
            }, 300);
        });
    }

    // -----------------------------------------------------------------
    // 2. Fullscreen toggle
    // -----------------------------------------------------------------
    const fullscreenBtn = document.querySelector('#btn-fullscreen');
    if (fullscreenBtn) {
        const updateIcon = function (isFull) {
            const icon = fullscreenBtn.querySelector('i');
            if (icon) {
                icon.className = isFull ? 'bi bi-fullscreen-exit' : 'bi bi-arrows-fullscreen';
            }
        };

        fullscreenBtn.addEventListener('click', function () {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().then(function () {
                    updateIcon(true);
                }).catch(function () { });
            } else {
                document.exitFullscreen().then(function () {
                    updateIcon(false);
                }).catch(function () { });
            }
        });

        document.addEventListener('fullscreenchange', function () {
            updateIcon(!!document.fullscreenElement);
        });
    }

    // -----------------------------------------------------------------
    // 3. Revenue / Stock movement bar chart
    // -----------------------------------------------------------------
    const revenueChartEl = document.querySelector('#revenue-chart');
    if (revenueChartEl && window.ApexCharts) {
        new ApexCharts(revenueChartEl, {
            series: [
                { name: 'Sold', data: cfg.chartSales || [] },
                { name: 'Purchased', data: cfg.chartPurchases || [] }
            ],
            chart: {
                type: 'bar',
                height: 240,
                stacked: false,
                toolbar: { show: false },
                zoom: { enabled: false },
                fontFamily: 'Plus Jakarta Sans, sans-serif'
            },
            colors: ['#1F2937', '#B45309'],
            states: { hover: { filter: { type: 'none' } } },
            plotOptions: {
                bar: { horizontal: false, columnWidth: '48%', borderRadius: 0 }
            },
            dataLabels: { enabled: false },
            stroke: { show: true, width: 2, colors: ['transparent'] },
            legend: { show: false },
            grid: {
                borderColor: '#E5E7EB',
                strokeDashArray: 4,
                yaxis: { lines: { show: true } },
                xaxis: { lines: { show: false } },
                padding: { top: 0, right: 0, bottom: 0, left: 0 }
            },
            xaxis: {
                categories: cfg.chartLabels || [],
                labels: {
                    style: { colors: '#6B7280', fontSize: '11px', fontWeight: 500 }
                },
                axisBorder: { show: false },
                axisTicks: { show: false }
            },
            yaxis: {
                labels: {
                    style: { colors: '#6B7280', fontSize: '11px' }
                }
            },
            fill: { opacity: 1 },
            tooltip: {
                y: { formatter: function (val) { return val + ' units'; } },
                theme: 'dark'
            }
        }).render();
    }

    // -----------------------------------------------------------------
    // 4. Stock health donut chart
    // -----------------------------------------------------------------
    const viewsChartEl = document.querySelector('#views-chart');
    if (viewsChartEl && window.ApexCharts) {
        const health = cfg.stockHealth || { healthy: 0, low: 0, out: 0 };
        new ApexCharts(viewsChartEl, {
            series: [health.healthy, health.low, health.out],
            chart: {
                type: 'donut',
                height: 250,
                fontFamily: 'Plus Jakarta Sans, sans-serif'
            },
            labels: ['Healthy', 'Low Stock', 'Out of Stock'],
            colors: ['#B45309', '#D97706', '#DC2626'],
            states: { hover: { filter: { type: 'none' } } },
            legend: { show: false },
            dataLabels: { enabled: false },
            plotOptions: {
                pie: {
                    donut: {
                        size: '72%',
                        background: 'transparent',
                        labels: {
                            show: true,
                            name: {
                                show: true,
                                fontSize: '12px',
                                fontWeight: 500,
                                color: '#6B7280',
                                offsetY: -8
                            },
                            value: {
                                show: true,
                                fontSize: '26px',
                                fontWeight: 800,
                                color: '#1F2937',
                                offsetY: 8
                            },
                            total: {
                                show: true,
                                label: 'Total Items',
                                fontSize: '11px',
                                fontWeight: 500,
                                color: '#6B7280',
                                formatter: function () {
                                    return String(cfg.totalVariants || 0);
                                }
                            }
                        }
                    }
                }
            },
            tooltip: { theme: 'dark' }
        }).render();
    }

    // -----------------------------------------------------------------
    // 5. Sparklines (stock units + low stock)
    // -----------------------------------------------------------------
    if (window.ApexCharts) {
        const incomeSparkEl = document.querySelector('#income-sparkline');
        if (incomeSparkEl) {
            new ApexCharts(incomeSparkEl, {
                series: [{ name: 'Purchased', data: cfg.sparkPurchases || [] }],
                chart: {
                    type: 'area', height: 45,
                    sparkline: { enabled: true },
                    fontFamily: 'Plus Jakarta Sans, sans-serif'
                },
                stroke: { curve: 'smooth', width: 2 },
                fill: { opacity: 0.1, type: 'solid' },
                colors: ['#16A34A'],
                tooltip: { fixed: { enabled: false }, x: { show: false }, marker: { show: false } }
            }).render();
        }

        const returnSparkEl = document.querySelector('#return-sparkline');
        if (returnSparkEl) {
            new ApexCharts(returnSparkEl, {
                series: [{ name: 'Sold', data: cfg.sparkSales || [] }],
                chart: {
                    type: 'area', height: 45,
                    sparkline: { enabled: true },
                    fontFamily: 'Plus Jakarta Sans, sans-serif'
                },
                stroke: { curve: 'smooth', width: 2 },
                fill: { opacity: 0.1, type: 'solid' },
                colors: ['#DC2626'],
                tooltip: { fixed: { enabled: false }, x: { show: false }, marker: { show: false } }
            }).render();
        }
    }

    // -----------------------------------------------------------------
    // 6. Date range picker (visual parity with Spark Admin)
    // -----------------------------------------------------------------
    const datePickerTrigger = document.querySelector('#date-picker-trigger');
    const selectedRangeText = document.querySelector('#selected-date-range');
    if (datePickerTrigger && selectedRangeText && window.flatpickr) {
        flatpickr(datePickerTrigger, {
            mode: 'range',
            dateFormat: 'Y-m-d',
            onValueUpdate: function (selectedDates, dateStr, instance) {
                if (selectedDates.length === 2) {
                    const start = instance.formatDate(selectedDates[0], 'F j, Y');
                    const end = instance.formatDate(selectedDates[1], 'F j, Y');
                    selectedRangeText.textContent = start + ' - ' + end;
                } else if (selectedDates.length === 1) {
                    selectedRangeText.textContent = instance.formatDate(selectedDates[0], 'F j, Y');
                }
            }
        });
    }

    // -----------------------------------------------------------------
    // 7. Products table live search
    // -----------------------------------------------------------------
    const tableRows = document.querySelectorAll('#products-table tbody tr[data-search]');
    const tableSearch = document.querySelector('#table-search');
    const mainSearch = document.querySelector('#main-search');

    function filterTable(term) {
        const query = (term || '').toLowerCase().trim();
        tableRows.forEach(function (row) {
            const haystack = (row.getAttribute('data-search') || '').toLowerCase();
            row.style.display = !query || haystack.indexOf(query) !== -1 ? '' : 'none';
        });
    }

    if (tableSearch) {
        tableSearch.addEventListener('input', function () {
            filterTable(this.value);
        });
    }
    if (mainSearch) {
        mainSearch.addEventListener('input', function () {
            filterTable(this.value);
        });
    }

    // -----------------------------------------------------------------
    // 8. Record sale / purchase
    // -----------------------------------------------------------------
    const movementStatus = document.querySelector('#movement-status');
    const movementButtons = document.querySelectorAll('[data-movement]');

    function setStatus(text, isError) {
        if (!movementStatus) return;
        movementStatus.textContent = text;
        movementStatus.className = 'form-feedback-custom ' + (isError ? 'invalid-custom' : 'valid-custom');
    }

    movementButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            const select = document.querySelector('#movementProductSelect');
            const qtyInput = document.querySelector('#movementQty');
            if (!select || !qtyInput) return;

            const variantId = parseInt(select.value, 10);
            const qty = parseInt(qtyInput.value, 10);

            if (!variantId || isNaN(qty) || qty <= 0) {
                setStatus('Meharbani farma kar sahi quantity daalein!', true);
                return;
            }

            const type = btn.getAttribute('data-movement');
            btn.disabled = true;

            fetch('/movement/' + type + '/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ variant_id: variantId, qty: qty })
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data && data.message) {
                        setStatus(data.message + ' (New stock: ' + data.new_stock + ')', false);
                        window.location.reload();
                    } else {
                        setStatus('Error: ' + ((data && (data.detail || data.error)) || 'Unknown error'), true);
                    }
                })
                .catch(function (error) {
                    setStatus('Kuch masla ho gaya: ' + error, true);
                })
                .finally(function () {
                    btn.disabled = false;
                });
        });
    });
});
