// ═══════════════════════════════════════════════════════════════
//  Swing Screener Pro — Frontend App Controller
// ═══════════════════════════════════════════════════════════════

let allStocks = [];
let isScanning = false;
let activeModalSymbol = null; // keeps track of the currently open modal's symbol
let currentSortField = 'score'; // default sort by score
let currentSortOrder = 'desc';  // default descending order

// Performance Evaluation sorting state
let currentPerfResults = [];
let currentPerfSortField = 'performance'; // default sort by Change %
let currentPerfSortOrder = 'desc';        // default descending order (best gains first)

// ── User Risk Settings (live, changeable) ───────────────────────
let userCapital = 100000;   // default ₹1,00,000
let userRiskPct = 1;        // default 1% risk per trade
let userTargetPct = 10;     // default 10% target goal percentage


// ── AUTHENTICATION HELPERS ──────────────────────────────────────
let pendingAuthAction = null;

function getAuthHeaders() {
    return {
        'X-Api-Password': sessionStorage.getItem('settings_password') || ''
    };
}

function checkPasswordProtection(action) {
    if (sessionStorage.getItem('settings_password')) {
        action();
    } else {
        pendingAuthAction = action;
        openPasswordModal();
    }
}

function openPasswordModal() {
    document.getElementById('passwordModalOverlay').style.display = 'flex';
    const input = document.getElementById('passwordInput');
    input.value = '';
    input.focus();
    document.getElementById('passwordErrorMsg').style.display = 'none';
}

function closePasswordModal() {
    document.getElementById('passwordModalOverlay').style.display = 'none';
    pendingAuthAction = null;
}

async function submitPassword() {
    const input = document.getElementById('passwordInput');
    const errorMsg = document.getElementById('passwordErrorMsg');
    const pwd = input.value;
    
    try {
        const res = await fetch('/api/verify-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pwd })
        });
        const result = await res.json();
        
        if (res.ok && result.status === 'ok') {
            sessionStorage.setItem('settings_password', pwd);
            const actionToRun = pendingAuthAction;
            closePasswordModal();
            if (actionToRun) {
                actionToRun();
            }
        } else {
            errorMsg.innerHTML = '<i class="fa-solid fa-circle-xmark" style="margin-right:6px;"></i> Incorrect passcode. Try again.';
            errorMsg.style.display = 'block';
            input.value = '';
            input.focus();
        }
    } catch (e) {
        console.error("Verification error:", e);
        errorMsg.innerHTML = '<i class="fa-solid fa-circle-xmark" style="margin-right:6px;"></i> Server connection error.';
        errorMsg.style.display = 'block';
    }
}

// Bind password modal event listeners
if (document.getElementById('btnSubmitPassword')) {
    document.getElementById('btnSubmitPassword').addEventListener('click', submitPassword);
}
if (document.getElementById('btnSubmitPasswordCancel')) {
    document.getElementById('btnSubmitPasswordCancel').addEventListener('click', closePasswordModal);
}
if (document.getElementById('btnCancelPassword')) {
    document.getElementById('btnCancelPassword').addEventListener('click', closePasswordModal);
}
if (document.getElementById('passwordInput')) {
    document.getElementById('passwordInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') submitPassword();
    });
}


// ═══════════════════════════════════════════════════════════════
//  POSITION SIZING ENGINE
//  Pure math, runs on the frontend — no scan needed.
// ═══════════════════════════════════════════════════════════════
function calcPosition(stock) {
    const price = stock.price || 0;
    const slPrice = stock.slPrice || price;
    const slPoints = Math.max(price - slPrice, 0.01);

    const maxRisk = userCapital * (userRiskPct / 100);
    const sharesRisk = Math.floor(maxRisk / slPoints);
    const sharesCap = price > 0 ? Math.floor(userCapital / price) : 0;

    const shares = sharesCap > 0 ? Math.max(1, Math.min(sharesRisk, sharesCap)) : 0;
    const capitalUsed = shares * price;
    const maxLoss = shares * slPoints;
    const profit1x = shares * slPoints;
    const profit2x = shares * slPoints * 2;
    const profit3x = shares * slPoints * 3;
    const tgt1Price = price + slPoints;
    const tgt2Price = stock.tgt2 || (price + slPoints * 2);
    const tgt3Price = stock.tgt3 || (price + slPoints * 3);
    const portfolioPct = userCapital > 0 ? ((capitalUsed / userCapital) * 100).toFixed(1) : 0;

    // Custom Target calculations
    const customTgtPrice = price * (1 + userTargetPct / 100);
    const customTgtProfit = shares * (price * (userTargetPct / 100));
    const slPct = stock.slPct || (price > 0 ? (slPoints / price) * 100 : 0.01);
    const customRrRatio = slPct > 0 ? (userTargetPct / slPct).toFixed(1) : "0.0";

    return {
        shares, capitalUsed, maxLoss,
        profit1x, profit2x, profit3x,
        tgt1Price, tgt2Price, tgt3Price,
        portfolioPct, slPoints, maxRisk,
        customTgtPrice, customTgtProfit, customRrRatio
    };
}


// ── Update Risk Summary Panel ────────────────────────────────────
function updateRiskPanel() {
    const maxRisk = userCapital * (userRiskPct / 100);
    const maxPositions = userRiskPct > 0 ? Math.floor(100 / userRiskPct) : 0;

    // Average capital per trade based on buy signals
    const buyStocks = allStocks.filter(s => s.signal === "BUY" || s.signal === "STRONG BUY");
    let avgCapPerTrade = "—";
    if (buyStocks.length > 0) {
        const totalCap = buyStocks.reduce((sum, s) => sum + calcPosition(s).capitalUsed, 0);
        avgCapPerTrade = formatINR(totalCap / buyStocks.length);
    }

    document.getElementById('riskPerTrade').textContent = formatINR(maxRisk);
    document.getElementById('maxPositions').textContent = maxPositions + " trades";
    document.getElementById('capitalPerTrade').textContent = avgCapPerTrade;

    // Update slider background gradient
    const slider = document.getElementById('riskPctSlider');
    const pct = ((userRiskPct - 0.5) / (5 - 0.5)) * 100;
    slider.style.background = `linear-gradient(to right, var(--accent) 0%, var(--accent) ${pct}%, rgba(255,255,255,0.1) ${pct}%, rgba(255,255,255,0.1) 100%)`;

    // Target slider gradient initialization
    const targetSlider = document.getElementById('targetPctSlider');
    if (targetSlider) {
        const targetPct = ((userTargetPct - 1) / (15 - 1)) * 100;
        targetSlider.style.background = `linear-gradient(to right, var(--accent) 0%, var(--accent) ${targetPct}%, rgba(255,255,255,0.1) ${targetPct}%, rgba(255,255,255,0.1) 100%)`;
    }
}


// ── Format Helpers ───────────────────────────────────────────────
function formatINR(num) {
    if (!num && num !== 0) return "—";
    return "₹" + parseFloat(num).toLocaleString('en-IN', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    });
}

function formatINR2(num) {
    if (!num && num !== 0) return "—";
    return "₹" + parseFloat(num).toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}


// ═══════════════════════════════════════════════════════════════
//  DATA LOADING
// ═══════════════════════════════════════════════════════════════
async function loadData() {
    try {
        const response = await fetch('/api/data');
        const result = await response.json();
        const data = result.data;

        allStocks = (data.stocks || []).filter(s => s.status === "ok");

        document.getElementById('lastScan').innerHTML =
            `<i class="fa-regular fa-clock"></i> Last Scan: ${data.scanned_at || 'Never'}`;

        let buyCount = 0, watchCount = 0, avoidCount = 0;
        allStocks.forEach(s => {
            if (s.signal === "BUY" || s.signal === "STRONG BUY") buyCount++;
            else if (s.signal === "WATCH") watchCount++;
            else avoidCount++;
        });

        document.getElementById('totalStocks').textContent = allStocks.length;
        document.getElementById('buyCount').textContent = buyCount;
        document.getElementById('watchCount').textContent = watchCount;
        document.getElementById('avoidCount').textContent = avoidCount;

        const uptrend = data.uptrend_count !== undefined ? data.uptrend_count : 0;
        const downtrend = data.downtrend_count !== undefined ? data.downtrend_count : 0;
        const sideways = data.sideways_count !== undefined ? data.sideways_count : 0;
        const total = uptrend + downtrend + sideways || 1;

        const uptrendPct = ((uptrend / total) * 100).toFixed(1);
        const downtrendPct = ((downtrend / total) * 100).toFixed(1);
        const sidewaysPct = ((sideways / total) * 100).toFixed(1);

        document.getElementById('uptrendCount').textContent = uptrend;
        document.getElementById('downtrendCount').textContent = downtrend;
        document.getElementById('sidewaysCount').textContent = sideways;

        document.getElementById('uptrendPct').textContent = `(${uptrendPct}%)`;
        document.getElementById('downtrendPct').textContent = `(${downtrendPct}%)`;
        document.getElementById('sidewaysPct').textContent = `(${sidewaysPct}%)`;

        document.getElementById('uptrendBar').style.width = uptrendPct + '%';
        document.getElementById('sidewaysBar').style.width = sidewaysPct + '%';
        document.getElementById('downtrendBar').style.width = downtrendPct + '%';

        updateRiskPanel();
        renderTopPicks();
        renderTable();

    } catch (err) {
        console.error("Error loading screener data:", err);
    }
}

async function loadNifty() {
    try {
        const response = await fetch('/api/nifty');
        const nifty = await response.json();

        if (nifty.status === "ok") {
            const sign = nifty.change >= 0 ? "+" : "";
            document.getElementById('niftyPrice').innerHTML =
                `₹${parseFloat(nifty.price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

            const moodEl = document.getElementById('marketMood');
            moodEl.textContent = `${nifty.mood} (${sign}${nifty.change}%)`;
            moodEl.className = "mood-badge " + nifty.mood.toLowerCase();
            moodEl.title = nifty.advice;
        }
    } catch (err) {
        console.error("Error fetching Nifty:", err);
    }
}


// ═══════════════════════════════════════════════════════════════
//  SCAN TRIGGER
// ═══════════════════════════════════════════════════════════════
let lightweightChart = null;
let scoreTrendChart = null;
let chartObserver = null;
let scoreObserver = null;
let pollInterval = null;

// Destroys any existing charts to prevent memory leaks or dual charts
function clearCharts() {
    if (chartObserver) {
        chartObserver.disconnect();
        chartObserver = null;
    }
    if (scoreObserver) {
        scoreObserver.disconnect();
        scoreObserver = null;
    }
    if (lightweightChart) {
        try {
            lightweightChart.remove();
        } catch(e) {}
        lightweightChart = null;
    }
    if (scoreTrendChart) {
        try {
            scoreTrendChart.remove();
        } catch(e) {}
        scoreTrendChart = null;
    }
    document.getElementById('modalChartContainer').innerHTML = '';
    document.getElementById('modalScoreHistoryContainer').innerHTML = '';
}

// Renders the technical candlestick chart with EMA overlay and S&R lines
async function renderTechnicalChart(sym, price, slPrice, tgt2Price) {
    const container = document.getElementById('modalChartContainer');
    container.innerHTML = `<div class="text-center text-muted" style="line-height:300px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading chart...</div>`;
    
    try {
        const res = await fetch(`/api/stock/${sym}/history`);
        const result = await res.json();
        
        if (result.status !== "ok" || !result.history || result.history.length === 0) {
            container.innerHTML = `<div class="text-center text-muted" style="line-height:300px;">Failed to load chart data.</div>`;
            return;
        }
        
        container.innerHTML = '';
        
        const isLight = document.body.classList.contains('light-mode');
        const textColor = isLight ? '#475569' : '#cbd5e1';
        const lineGridColor = isLight ? 'rgba(15, 23, 42, 0.06)' : 'rgba(255, 255, 255, 0.05)';
        const borderGridColor = isLight ? 'rgba(15, 23, 42, 0.15)' : 'rgba(255, 255, 255, 0.1)';

        const chartOptions = {
            width: container.clientWidth || 460,
            height: 300,
            layout: {
                background: { type: 'solid', color: 'transparent' },
                textColor: textColor,
            },
            grid: {
                vertLines: { color: lineGridColor },
                horzLines: { color: lineGridColor },
            },
            crosshair: {
                mode: 1,
            },
            rightPriceScale: {
                borderColor: borderGridColor,
            },
            timeScale: {
                borderColor: borderGridColor,
            },
        };
        
        lightweightChart = LightweightCharts.createChart(container, chartOptions);
        
        // Add candlestick series
        const candleSeries = lightweightChart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: '#34d399',
            downColor: '#f43f5e',
            borderVisible: false,
            wickUpColor: '#34d399',
            wickDownColor: '#f43f5e',
        });
        
        const candleData = result.history.map(x => ({
            time: x.time,
            open: x.open,
            high: x.high,
            low: x.low,
            close: x.close
        }));
        candleSeries.setData(candleData);
        
        // Add EMA lines
        const ema9Series = lightweightChart.addSeries(LightweightCharts.LineSeries, { color: '#f59e0b', lineWidth: 1.5, title: 'EMA 9' });
        const ema9Data = result.history.filter(x => x.ema9 != null).map(x => ({ time: x.time, value: x.ema9 }));
        ema9Series.setData(ema9Data);
        
        const ema20Series = lightweightChart.addSeries(LightweightCharts.LineSeries, { color: '#9ca3af', lineWidth: 1.5, title: 'EMA 20' });
        const ema20Data = result.history.filter(x => x.ema20 != null).map(x => ({ time: x.time, value: x.ema20 }));
        ema20Series.setData(ema20Data);
        
        const ema21Series = lightweightChart.addSeries(LightweightCharts.LineSeries, { color: '#3b82f6', lineWidth: 1.5, title: 'EMA 21' });
        const ema21Data = result.history.filter(x => x.ema21 != null).map(x => ({ time: x.time, value: x.ema21 }));
        ema21Series.setData(ema21Data);
        
        const ema50Series = lightweightChart.addSeries(LightweightCharts.LineSeries, { color: '#8b5cf6', lineWidth: 1.5, title: 'EMA 50' });
        const ema50Data = result.history.filter(x => x.ema50 != null).map(x => ({ time: x.time, value: x.ema50 }));
        ema50Series.setData(ema50Data);
        
        const ema200Series = lightweightChart.addSeries(LightweightCharts.LineSeries, { color: '#60a5fa', lineWidth: 2.0, title: 'EMA 200' });
        const ema200Data = result.history.filter(x => x.ema200 != null).map(x => ({ time: x.time, value: x.ema200 }));
        ema200Series.setData(ema200Data);
        
        // Add price lines for SL and Target
        candleSeries.createPriceLine({
            price: price,
            color: '#3b82f6',
            lineWidth: 1.5,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: 'Entry',
        });
        
        candleSeries.createPriceLine({
            price: slPrice,
            color: '#f87171',
            lineWidth: 1.5,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: 'SL',
        });
        
        candleSeries.createPriceLine({
            price: tgt2Price,
            color: '#4ade80',
            lineWidth: 1.5,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: 'Tgt 2:1',
        });
        
        lightweightChart.timeScale().fitContent();
        
        // Resize observer to make chart responsive to container width changes
        chartObserver = new ResizeObserver(entries => {
            if (lightweightChart) {
                const w = container.clientWidth;
                if (w > 0) lightweightChart.resize(w, 300);
            }
        });
        chartObserver.observe(container);
        
    } catch(err) {
        console.error("Error rendering technical chart:", err);
        container.innerHTML = `<div class="text-center text-muted" style="line-height:300px;">Failed to load chart data.</div>`;
    }
}

// Renders the score history line chart from SQLite logs
async function renderScoreHistory(sym) {
    const container = document.getElementById('modalScoreHistoryContainer');
    container.innerHTML = `<div class="text-center text-muted" style="line-height:300px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading scores...</div>`;
    
    try {
        const res = await fetch(`/api/stock/${sym}/score-history`);
        const result = await res.json();
        
        if (result.status !== "ok" || !result.history || result.history.length === 0) {
            container.innerHTML = `<div class="text-center text-muted" style="line-height:300px;padding:20px;">No historical score data available yet. Run more full scans to log score history.</div>`;
            return;
        }
        
        container.innerHTML = '';
        
        const isLight = document.body.classList.contains('light-mode');
        const textColor = isLight ? '#475569' : '#cbd5e1';
        const lineGridColor = isLight ? 'rgba(15, 23, 42, 0.06)' : 'rgba(255, 255, 255, 0.05)';
        const borderGridColor = isLight ? 'rgba(15, 23, 42, 0.15)' : 'rgba(255, 255, 255, 0.1)';

        const chartOptions = {
            width: container.clientWidth || 460,
            height: 300,
            layout: {
                background: { type: 'solid', color: 'transparent' },
                textColor: textColor,
            },
            grid: {
                vertLines: { color: lineGridColor },
                horzLines: { color: lineGridColor },
            },
            crosshair: {
                mode: 1,
            },
            rightPriceScale: {
                borderColor: borderGridColor,
            },
            timeScale: {
                borderColor: borderGridColor,
            },
        };
        
        scoreTrendChart = LightweightCharts.createChart(container, chartOptions);
        
        const lineSeries = scoreTrendChart.addSeries(LightweightCharts.LineSeries, {
            color: '#60a5fa',
            lineWidth: 2.5,
            title: 'Screener Score',
        });
        
        const dataPoints = result.history.map(x => {
            let timeStr = x.scanned_at.split(' ')[0];
            return {
                time: timeStr,
                value: x.score
            };
        });
        
        // Deduplicate time field
        const uniqueDataPoints = [];
        const timesSeen = new Set();
        dataPoints.forEach(pt => {
            if (!timesSeen.has(pt.time)) {
                timesSeen.add(pt.time);
                uniqueDataPoints.push(pt);
            }
        });
        
        if (uniqueDataPoints.length === 0) {
            container.innerHTML = `<div class="text-center text-muted" style="line-height:300px;">No trend data.</div>`;
            return;
        }
        
        lineSeries.setData(uniqueDataPoints);
        scoreTrendChart.timeScale().fitContent();
        
        // Resize observer to make score trend chart responsive
        scoreObserver = new ResizeObserver(entries => {
            if (scoreTrendChart) {
                const w = container.clientWidth;
                if (w > 0) scoreTrendChart.resize(w, 300);
            }
        });
        scoreObserver.observe(container);
        
    } catch(err) {
        console.error("Error rendering score history:", err);
        container.innerHTML = `<div class="text-center text-muted" style="line-height:300px;">Failed to load score history.</div>`;
    }
}

// Starts polling scan status
function startScanPolling() {
    if (pollInterval) clearInterval(pollInterval);
    
    const banner = document.getElementById('scanProgressBanner');
    const fill = document.getElementById('progressBarFill');
    const text = document.getElementById('progressText');
    const pctText = document.getElementById('progressPctText');
    const scanBtn = document.getElementById('btnScan');
    const scanBtnTxt = document.getElementById('btnScanText');
    
    banner.style.display = 'flex';
    scanBtn.classList.add('loading');
    scanBtnTxt.textContent = "Scanning...";
    isScanning = true;
    
    pollInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/scan/status');
            const progress = await res.json();
            
            if (progress.is_scanning) {
                const current = progress.current || 0;
                const total = progress.total || 1;
                const symbol = progress.symbol || '...';
                const pct = Math.round((current / total) * 100);
                
                fill.style.width = pct + '%';
                pctText.textContent = pct + '%';
                text.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scanning ${symbol} (${current} of ${total})...`;
            } else {
                // Done!
                clearInterval(pollInterval);
                pollInterval = null;
                isScanning = false;
                banner.style.display = 'none';
                scanBtn.classList.remove('loading');
                scanBtnTxt.textContent = "Run Full Scan";
                
                await loadData();
                await loadNifty();
            }
        } catch (e) {
            console.error("Error polling scan status:", e);
        }
    }, 1500);
}

// Check if server is already scanning on initial page load
async function checkActiveScan() {
    try {
        const res = await fetch('/api/scan/status');
        const progress = await res.json();
        if (progress.is_scanning) {
            startScanPolling();
        }
    } catch (e) {
        console.error("Error checking active scan:", e);
    }
}

async function triggerScan() {
    if (isScanning) return;
    
    const capitalInput = parseInt(document.getElementById('capitalInput').value, 10);
    const capital = isNaN(capitalInput) || capitalInput < 1000 ? 100000 : capitalInput;
    
    try {
        const res = await fetch(`/api/scan?capital=${capital}`, {
            headers: getAuthHeaders()
        });
        const result = await res.json();
        
        if (result.status === "ok") {
            startScanPolling();
        } else {
            alert("Scan failed to start: " + (result.message || "Unknown error"));
        }
    } catch (err) {
        console.error("Scan error:", err);
        alert("Scan timed out or server error.");
    }
}


// ═══════════════════════════════════════════════════════════════
//  RENDER TOP PICKS (sidebar)
// ═══════════════════════════════════════════════════════════════
function renderTopPicks() {
    const container = document.getElementById('topPicks');
    const top = [...allStocks]
        .filter(x => x.signal === "BUY" || x.signal === "STRONG BUY")
        .sort((a, b) => b.score - a.score)
        .slice(0, 10);

    if (top.length === 0) {
        container.innerHTML = `<div class="text-center text-muted" style="padding:20px 0;">No buy setups found.</div>`;
        return;
    }

    container.innerHTML = top.map(x => {
        const pos = calcPosition(x);
        const scoreClass = x.signal === "STRONG BUY" ? "pick-score strong" : "pick-score";
        return `
        <div class="pick-item" onclick="openModal('${x.sym}')" style="cursor:pointer;">
            <div class="pick-left">
                <span class="pick-sym">${x.sym}</span>
                <span class="pick-sector">${x.sector} · ${x.candle}</span>
            </div>
            <div class="pick-right">
                <span class="${scoreClass}">${x.score} pts</span>
                <span class="pick-price">${formatINR2(x.price)}</span>
                <span class="pick-vol">${pos.shares} shares · ${formatINR(pos.capitalUsed)}</span>
            </div>
        </div>`;
    }).join('');
}


// ═══════════════════════════════════════════════════════════════
//  EOD PERFORMANCE TABLE SORTING
// ═══════════════════════════════════════════════════════════════
function updatePerfSortHeadersUI() {
    const headers = document.querySelectorAll('.sortable-headers-perf th');
    headers.forEach(th => {
        const field = th.getAttribute('data-sort-perf');
        const iconSpan = th.querySelector('.sort-icon');
        if (!iconSpan) return;

        if (field === currentPerfSortField) {
            th.classList.add('active-sort');
            const iconClass = currentPerfSortOrder === 'asc' ? 'fa-sort-up' : 'fa-sort-down';
            iconSpan.innerHTML = `<i class="fa-solid ${iconClass}"></i>`;
        } else {
            th.classList.remove('active-sort');
            iconSpan.innerHTML = '<i class="fa-solid fa-sort"></i>';
        }
    });
}

function renderPerformanceTable() {
    const tbody = document.getElementById('performanceTableBody');
    if (!tbody || currentPerfResults.length === 0) return;

    updatePerfSortHeadersUI();

    const sorted = [...currentPerfResults];
    if (currentPerfSortField && currentPerfSortOrder) {
        sorted.sort((a, b) => {
            let valA, valB;
            switch (currentPerfSortField) {
                case 'sym':
                    valA = a.sym || '';
                    valB = b.sym || '';
                    break;
                case 'score':
                    valA = a.score || 0;
                    valB = b.score || 0;
                    break;
                case 'signal':
                    const sigMap = { "STRONG BUY": 4, "BUY": 3, "WATCH": 2, "AVOID": 1 };
                    valA = sigMap[a.signal] || 0;
                    valB = sigMap[b.signal] || 0;
                    break;
                case 'initialPrice':
                    valA = a.initialPrice || 0;
                    valB = b.initialPrice || 0;
                    break;
                case 'currentPrice':
                    valA = a.currentPrice || 0;
                    valB = b.currentPrice || 0;
                    break;
                case 'performance':
                    valA = a.performance || 0;
                    valB = b.performance || 0;
                    break;
                case 'status':
                    valA = a.performance >= 0 ? 1 : 0;
                    valB = b.performance >= 0 ? 1 : 0;
                    break;
                default:
                    valA = 0;
                    valB = 0;
            }

            if (typeof valA === 'string') {
                return currentPerfSortOrder === 'asc' 
                    ? valA.localeCompare(valB) 
                    : valB.localeCompare(valA);
            } else {
                return currentPerfSortOrder === 'asc' 
                    ? valA - valB 
                    : valB - valA;
            }
        });
    }

    tbody.innerHTML = sorted.map(r => {
        const changeCls = r.performance >= 0 ? 'pos-cell profit' : 'pos-cell loss';
        const changeText = `${r.performance > 0 ? '+' : ''}${r.performance.toFixed(2)}%`;
        const statusBadge = r.performance >= 0 ? '<span class="signal-pill buy">WIN</span>' : '<span class="signal-pill avoid">LOSS</span>';
        let sigClass = "signal-pill ";
        if (r.signal === "STRONG BUY") sigClass += "strong-buy";
        else if (r.signal === "BUY") sigClass += "buy";

        return `
        <tr class="row-clickable" onclick="openModal('${r.sym}')">
            <td><span class="symbol-column">${r.sym}</span></td>
            <td class="text-center" style="font-weight:600;">${r.score}</td>
            <td class="text-center"><span class="${sigClass}">${r.signal}</span></td>
            <td class="text-end" style="font-family:var(--font-heading);font-weight:500;">${formatINR2(r.initialPrice)}</td>
            <td class="text-end" style="font-family:var(--font-heading);font-weight:500;">${formatINR2(r.currentPrice)}</td>
            <td class="text-end ${changeCls}">${changeText}</td>
            <td class="text-center">${statusBadge}</td>
        </tr>`;
    }).join('');
}


// ═══════════════════════════════════════════════════════════════
//  RENDER SCREENER TABLE
// ═══════════════════════════════════════════════════════════════
function updateSortHeadersUI() {
    const headers = document.querySelectorAll('.sortable-headers th');
    headers.forEach(th => {
        const field = th.getAttribute('data-sort');
        const iconSpan = th.querySelector('.sort-icon');
        if (!iconSpan) return;

        if (field === currentSortField) {
            th.classList.add('active-sort');
            const iconClass = currentSortOrder === 'asc' ? 'fa-sort-up' : 'fa-sort-down';
            iconSpan.innerHTML = `<i class="fa-solid ${iconClass}"></i>`;
        } else {
            th.classList.remove('active-sort');
            iconSpan.innerHTML = '<i class="fa-solid fa-sort"></i>';
        }
    });
}

function renderTable() {
    const search          = document.getElementById('searchBox').value.toUpperCase();
    const filter          = document.getElementById('signalFilter').value;
    const capFilter       = document.getElementById('capFilter') ? document.getElementById('capFilter').value : '';
    const indicatorFilter = document.getElementById('indicatorFilter') ? document.getElementById('indicatorFilter').value : '';

    updateSortHeadersUI();

    const tgtHeader = document.getElementById('tableTgtHeader');
    if (tgtHeader) {
        tgtHeader.textContent = `Tgt (${userTargetPct}%)`;
    }

    const rows = allStocks.filter(stock => {
        const matchSearch    = stock.sym.includes(search) || stock.sector.toUpperCase().includes(search);
        const matchSignal    = !filter    || stock.signal      === filter;
        const matchCap       = !capFilter || stock.capCategory === capFilter;

        let matchIndicator = true;
        if (indicatorFilter) {
            switch (indicatorFilter) {
                // ⚡ Swing Setups
                case 'pullbackBuy':       matchIndicator = stock.pullbackBuy === true; break;
                case 'breakoutResistance':matchIndicator = stock.breakoutResistance === true; break;
                case 'vcpSetup':          matchIndicator = stock.vcpSetup === true; break;
                case 'highRs':            matchIndicator = stock.mansfieldRs > 0; break;
                // ── Trend ──
                case 'supertrendBuy':   matchIndicator = stock.supertrendDir === 'BUY'; break;
                case 'supertrendSell':  matchIndicator = stock.supertrendDir === 'SELL'; break;
                case 'weeklyBull':      matchIndicator = stock.weeklyTrend === 'UPTREND'; break;
                case 'emaCross':        matchIndicator = stock.emaCrossAlert === true; break;
                case 'adxStrong':       matchIndicator = stock.adxStrong === true; break;
                // ── Momentum ──
                case 'macdBull':        matchIndicator = stock.macdBull === true; break;
                case 'macdAbove':       matchIndicator = stock.macdAbove === true; break;
                case 'vwapBullish':     matchIndicator = stock.closeAboveVwap === true; break;
                case 'rsiOversold':     matchIndicator = stock.rsi <= 30; break;
                case 'rsiOverbought':   matchIndicator = stock.rsi >= 70; break;
                // ── Volume & Price ──
                case 'volSpike':        matchIndicator = stock.volSpike === true; break;
                case 'gapUp':           matchIndicator = stock.gapUp === true; break;
                case 'near52wHigh':     matchIndicator = stock.near52wHigh === true; break;
                case 'breakout52w':     matchIndicator = stock.breakout52w === true; break;
                case 'nearSupport':     matchIndicator = stock.nearSupport === true; break;
                case 'bbSqueeze':       matchIndicator = stock.bbSqueeze === true; break;
                case 'nearLowerBand':   matchIndicator = stock.nearLowerBand === true; break;
                // ── CPR / Pivot ──
                case 'cprBullish':      matchIndicator = stock.cprSignal === 'BULLISH'; break;
                case 'cprNarrow':       matchIndicator = stock.cprWidth != null && stock.cprWidth <= 0.25; break;
                default: matchIndicator = true;
            }
        }

        return matchSearch && matchSignal && matchCap && matchIndicator;
    });

    // Apply Sorting
    if (currentSortField && currentSortOrder) {
        rows.sort((a, b) => {
            let valA, valB;

            switch (currentSortField) {
                case 'sym':
                    valA = a.sym || '';
                    valB = b.sym || '';
                    break;
                case 'sector':
                    valA = a.sector || '';
                    valB = b.sector || '';
                    break;
                case 'score':
                    valA = a.score || 0;
                    valB = b.score || 0;
                    break;
                case 'rsi':
                    valA = a.rsi || 0;
                    valB = b.rsi || 0;
                    break;
                case 'volRatio':
                    valA = a.volRatio || 0;
                    valB = b.volRatio || 0;
                    break;
                case 'mansfieldRs':
                    valA = a.mansfieldRs || 0.0;
                    valB = b.mansfieldRs || 0.0;
                    break;
                case 'signal':
                    const sigMap = { "STRONG BUY": 4, "BUY": 3, "WATCH": 2, "AVOID": 1 };
                    valA = sigMap[a.signal] || 0;
                    valB = sigMap[b.signal] || 0;
                    break;
                case 'price':
                    valA = a.price || 0;
                    valB = b.price || 0;
                    break;
                case 'shares':
                    valA = calcPosition(a).shares || 0;
                    valB = calcPosition(b).shares || 0;
                    break;
                case 'capitalUsed':
                    valA = calcPosition(a).capitalUsed || 0;
                    valB = calcPosition(b).capitalUsed || 0;
                    break;
                case 'maxLoss':
                    valA = calcPosition(a).maxLoss || 0;
                    valB = calcPosition(b).maxLoss || 0;
                    break;
                case 'customTgtPrice':
                    valA = calcPosition(a).customTgtPrice || 0;
                    valB = calcPosition(b).customTgtPrice || 0;
                    break;
                default:
                    valA = 0;
                    valB = 0;
            }

            if (typeof valA === 'string') {
                return currentSortOrder === 'asc' 
                    ? valA.localeCompare(valB) 
                    : valB.localeCompare(valA);
            } else {
                return currentSortOrder === 'asc' 
                    ? valA - valB 
                    : valB - valA;
            }
        });
    }

    const tbody = document.getElementById('stockTable');

    if (rows.length === 0) {
        tbody.innerHTML = `
        <tr><td colspan="12" class="text-center text-muted" style="padding:40px 0;">
            <i class="fa-solid fa-folder-open" style="font-size:2rem;opacity:0.4;display:block;margin-bottom:8px;"></i>
            No matching stocks found
        </td></tr>`;
        return;
    }

    tbody.innerHTML = rows.map(stock => {
        const pos = calcPosition(stock);

        // Signal pill
        let sigClass = "signal-pill ";
        if (stock.signal === "STRONG BUY") sigClass += "strong-buy";
        else if (stock.signal === "BUY") sigClass += "buy";
        else if (stock.signal === "WATCH") sigClass += "watch";
        else sigClass += "avoid";

        const scorePct = Math.min(100, Math.max(0, stock.score));
        const rsiZone = (stock.rsiZone || 'buyzone').toLowerCase();
        const isSpike = stock.volRatio >= 2.0 ? "spike" : "";
        const volDisplay = stock.volRatio != null ? `${stock.volRatio.toFixed(2)}x` : "—";

        // Position sizing cells
        const sharesCls = pos.shares === 0 ? "pos-cell shares zero" : "pos-cell shares";
        const sharesText = pos.shares === 0 ? "—" : pos.shares;
        const capText = pos.shares === 0 ? "—" : formatINR(pos.capitalUsed);
        const lossText = pos.shares === 0 ? "—" : formatINR(pos.maxLoss);
        const tgtText = pos.shares === 0 ? "—" : formatINR(pos.customTgtProfit);

        const stDir = stock.supertrendDir;
        const stClass = stDir ? stDir.toLowerCase() : '';
        const stBadge = stDir ? `<span class="supertrend-indicator ${stClass}">${stDir}</span>` : '';

        // Cap category badge
        const cap = stock.capCategory || 'Unknown';
        const capColor = cap === 'Large Cap' ? '#3b82f6' : cap === 'Mid Cap' ? '#f59e0b' : cap === 'Small Cap' ? '#ef4444' : '#6b7280';
        const capDot   = cap !== 'Unknown' ? `<span class="cap-dot" style="background:${capColor};" title="${cap} · ₹${stock.marketCap ? stock.marketCap.toLocaleString('en-IN') : '?'} Cr"></span>` : '';

        // Swing setup badges
        const pbBadge  = stock.pullbackBuy        ? `<span class="swing-badge pb" title="Pullback Buy Zone">PB</span>` : '';
        const rbBadge  = stock.breakoutResistance ? `<span class="swing-badge rb" title="Resistance Breakout">RB</span>` : '';

        return `
        <tr class="row-clickable" onclick="openModal('${stock.sym}')">
            <td>
                <span class="symbol-column">${stock.sym}</span>
                ${stBadge}${pbBadge}${rbBadge}
                <span class="symbol-name">${stock.name}</span>
                ${capDot}
            </td>
            <td><span class="sector-column">${stock.sector}</span></td>
            <td>
                <div class="score-wrapper">
                    <span class="score-number">${stock.score}</span>
                    <div class="score-meter-container">
                        <div class="score-meter-bar" style="width:${scorePct}%"></div>
                    </div>
                </div>
            </td>
            <td class="text-center">
                <span class="rsi-badge ${rsiZone}">${stock.rsi.toFixed(1)}</span>
            </td>
            <td class="text-center">
                <span class="vol-ratio-val ${isSpike}">${volDisplay}</span>
            </td>
            <td class="text-center">
                <span class="rsi-badge ${stock.mansfieldRs >= 0.0 ? 'buyzone' : 'oversold'}" style="font-weight:600;">
                    ${stock.mansfieldRs != null ? stock.mansfieldRs.toFixed(2) : "0.00"}
                </span>
            </td>
            <td class="text-center">
                <span class="${sigClass}">${stock.signal}</span>
            </td>
            <td class="text-end" style="font-weight:600;font-family:var(--font-heading);">
                ${formatINR2(stock.price)}
            </td>
            <td class="text-center ${sharesCls}">${sharesText}</td>
            <td class="text-end pos-cell">${capText}</td>
            <td class="text-end pos-cell loss">${lossText}</td>
            <td class="text-end pos-cell profit">${tgtText}</td>
        </tr>`;
    }).join('');
}


// ═══════════════════════════════════════════════════════════════
//  POSITION DETAIL MODAL
// ═══════════════════════════════════════════════════════════════
function updateModalDetails(stock) {
    if (!stock) return;
    const pos = calcPosition(stock);

    document.getElementById('posPrice').textContent = formatINR2(stock.price);
    document.getElementById('posSlPrice').textContent = formatINR2(stock.slPrice);
    document.getElementById('posSlPct').textContent = `-${stock.slPct || 0}%  (₹${pos.slPoints.toFixed(2)})`;
    document.getElementById('posShares').textContent = pos.shares === 0 ? "Unaffordable" : `${pos.shares} shares`;
    document.getElementById('posCapital').textContent = formatINR(pos.capitalUsed);
    document.getElementById('posPortfolioPct').textContent = `${pos.portfolioPct}% of capital`;
    document.getElementById('posMaxLossPct').textContent = `${userRiskPct}%`;
    document.getElementById('posMaxLoss').textContent = `-${formatINR(pos.maxLoss)}`;

    // Target 1
    document.getElementById('posTgt1Price').textContent = formatINR2(pos.tgt1Price);
    document.getElementById('posTgt1').textContent = `+${formatINR(pos.profit1x)}`;

    // Target 2
    document.getElementById('posTgt2Price').textContent = formatINR2(pos.tgt2Price);
    document.getElementById('posTgt2').textContent = `+${formatINR(pos.profit2x)}`;

    // Target 3
    document.getElementById('posTgt3Price').textContent = formatINR2(pos.tgt3Price);
    document.getElementById('posTgt3').textContent = `+${formatINR(pos.profit3x)}`;

    // Custom Target Goal elements
    const customTgtLabelEl = document.getElementById('posCustomTgtLabel');
    if (customTgtLabelEl) {
        customTgtLabelEl.textContent = `Custom Target (${userTargetPct}%)`;
    }
    const customTgtPriceEl = document.getElementById('posCustomTgtPrice');
    if (customTgtPriceEl) {
        customTgtPriceEl.textContent = formatINR2(pos.customTgtPrice);
    }
    const customTgtEl = document.getElementById('posCustomTgt');
    if (customTgtEl) {
        customTgtEl.textContent = `+${formatINR(pos.customTgtProfit)}`;
    }
    const customRrEl = document.getElementById('posCustomRrRatio');
    if (customRrEl) {
        customRrEl.textContent = `1 : ${pos.customRrRatio}`;
    }
}


// ═══════════════════════════════════════════════════════════════
//  POSITION DETAIL MODAL
// ═══════════════════════════════════════════════════════════════
function openModal(sym) {
    const stock = allStocks.find(s => s.sym === sym);
    if (!stock) return;

    activeModalSymbol = sym; // Track open modal

    document.getElementById('posModalSym').textContent = stock.sym;
    document.getElementById('posModalSector').textContent = `${stock.sector} · ${stock.name}`;
    
    // Set static indicator fields
    document.getElementById('posTrendDays').textContent = `${stock.trendDays || 0} days`;
    document.getElementById('posTrendContScore').textContent = `${stock.trendContinuationScore !== undefined ? stock.trendContinuationScore : 0} / 15`;
    
    // Supertrend binding
    const supertrendEl = document.getElementById('posSupertrend');
    if (supertrendEl) {
        const stDir = stock.supertrendDir;
        const stVal = stock.supertrendVal;
        if (stDir && stVal) {
            supertrendEl.textContent = `${stDir} @ ₹${stVal.toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
            supertrendEl.className = `pos-modal-val ${stDir === 'BUY' ? 'profit' : 'loss'}`;
        } else {
            supertrendEl.textContent = '—';
            supertrendEl.className = 'pos-modal-val';
        }
    }

    // VWAP binding
    const vwapEl = document.getElementById('posVwap');
    if (vwapEl) {
        const vwapVal = stock.vwapVal;
        const closeAboveVwap = stock.closeAboveVwap;
        if (vwapVal != null) {
            vwapEl.textContent = `₹${vwapVal.toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
            vwapEl.className = `pos-modal-val ${closeAboveVwap ? 'profit' : 'loss'}`;
        } else {
            vwapEl.textContent = '—';
            vwapEl.className = 'pos-modal-val';
        }
    }

    // CPR binding
    const cprEl = document.getElementById('posCprSignal');
    if (cprEl) {
        const cprDir = stock.cprSignal;
        const cprVal = stock.cprWidth;
        if (cprDir && cprVal != null) {
            cprEl.textContent = `${cprDir} (${cprVal.toFixed(3)}%)`;
            cprEl.className = `pos-modal-val ${cprDir === 'BULLISH' ? 'profit' : (cprDir === 'BEARISH' ? 'loss' : '')}`;
        } else {
            cprEl.textContent = '—';
            cprEl.className = 'pos-modal-val';
        }
    }

    // MACD binding
    const macdEl = document.getElementById('posMacd');
    if (macdEl) {
        if (stock.macdLine != null && stock.macdSignal != null) {
            const crossTxt = stock.macdBull ? ' fresh cross 📈' : '';
            macdEl.textContent = `${stock.macdLine} / ${stock.macdSignal}${crossTxt}`;
            macdEl.className = `pos-modal-val ${stock.macdAbove ? 'profit' : 'loss'}`;
        } else {
            macdEl.textContent = '—';
            macdEl.className = 'pos-modal-val';
        }
    }

    // Bollinger Bands binding
    const bbEl = document.getElementById('posBollinger');
    if (bbEl) {
        if (stock.bbLower != null && stock.bbUpper != null) {
            const squeezeTxt = stock.bbSqueeze ? ' (SQUEEZE)' : '';
            bbEl.textContent = `₹${stock.bbLower.toFixed(1)} – ₹${stock.bbUpper.toFixed(1)}${squeezeTxt}`;
            bbEl.className = `pos-modal-val ${stock.bbSqueeze ? 'accent' : (stock.nearLowerBand ? 'profit' : (stock.nearUpperBand ? 'loss' : ''))}`;
        } else {
            bbEl.textContent = '—';
            bbEl.className = 'pos-modal-val';
        }
    }

    // ADX binding
    const adxEl = document.getElementById('posAdx');
    if (adxEl) {
        if (stock.adxVal != null) {
            adxEl.textContent = `${stock.adxVal} (${stock.adxStrong ? 'Strong' : 'Weak'})`;
            adxEl.className = `pos-modal-val ${stock.adxStrong ? 'profit' : ''}`;
        } else {
            adxEl.textContent = '—';
            adxEl.className = 'pos-modal-val';
        }
    }

    // Weekly Trend binding
    const weeklyEl = document.getElementById('posWeeklyTrend');
    if (weeklyEl) {
        if (stock.weeklyTrend) {
            weeklyEl.textContent = `${stock.weeklyTrend} (${stock.weeklyRsi ? 'RSI ' + stock.weeklyRsi.toFixed(1) : ''})`;
            weeklyEl.className = `pos-modal-val ${stock.weeklyTrend === 'UPTREND' ? 'profit' : (stock.weeklyTrend === 'DOWNTREND' ? 'loss' : '')}`;
        } else {
            weeklyEl.textContent = '—';
            weeklyEl.className = 'pos-modal-val';
        }
    }

    // Gap Status binding
    const gapEl = document.getElementById('posGapStatus');
    if (gapEl) {
        const gapTxt = stock.gapUp ? 'GAP UP 🚀' : (stock.gapDown ? 'GAP DOWN 📉' : 'No Gap');
        gapEl.textContent = gapTxt;
        gapEl.className = `pos-modal-val ${stock.gapUp ? 'profit' : (stock.gapDown ? 'loss' : '')}`;
    }

    // 52-Week Range binding
    const w52El = document.getElementById('pos52wRange');
    if (w52El) {
        if (stock.low52w != null && stock.high52w != null) {
            w52El.textContent = `₹${stock.low52w.toFixed(1)} – ₹${stock.high52w.toFixed(1)} (${stock.w52Pct || 0}%)`;
            w52El.className = `pos-modal-val ${stock.w52Pct >= 90 ? 'profit' : ''}`;
        } else {
            w52El.textContent = '—';
            w52El.className = 'pos-modal-val';
        }
    }

    // Nifty RS (Index) binding
    const msRsEl = document.getElementById('posMansfieldRs');
    if (msRsEl) {
        if (stock.mansfieldRs != null) {
            msRsEl.textContent = `${stock.mansfieldRs > 0 ? '+' : ''}${stock.mansfieldRs.toFixed(2)}`;
            msRsEl.className = `pos-modal-val ${stock.mansfieldRs > 0 ? 'profit' : 'loss'}`;
        } else {
            msRsEl.textContent = '—';
            msRsEl.className = 'pos-modal-val';
        }
    }

    // VCP Setup binding
    const vcpEl = document.getElementById('posVcpSetup');
    if (vcpEl) {
        vcpEl.textContent = stock.vcpSetup ? 'VCP SETUP DETECTED 📈' : 'No VCP Contraction';
        vcpEl.className = `pos-modal-val ${stock.vcpSetup ? 'profit' : ''}`;
    }

    // Candle note
    document.getElementById('posCandle').innerHTML =
        `<strong>Candle:</strong> ${stock.candle} &nbsp;|&nbsp; <strong>Entry Note:</strong> ${stock.entryNote}`;

    // Update dynamic sizing fields
    updateModalDetails(stock);

    // Reset tabs
    document.getElementById('btnTabChart').classList.add('active');
    document.getElementById('btnTabScore').classList.remove('active');
    document.getElementById('modalChartContainer').style.display = 'block';
    document.getElementById('modalScoreHistoryContainer').style.display = 'none';

    document.getElementById('posModal').style.display = 'flex';

    // Draw charts after display
    clearCharts();
    setTimeout(() => {
        const pos = calcPosition(stock);
        renderTechnicalChart(stock.sym, stock.price, stock.slPrice, pos.tgt2Price);
    }, 150);
}

function closeModal() {
    document.getElementById('posModal').style.display = 'none';
    activeModalSymbol = null; // Clear open modal
    clearCharts();
}


// ═══════════════════════════════════════════════════════════════
//  CUSTOM STOCK CRUD ENGINE
// ═══════════════════════════════════════════════════════════════
async function loadCustomStocks() {
    const tbody = document.getElementById('customStocksTableBody');
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Loading custom symbols...</td></tr>`;
    
    try {
        const res = await fetch('/api/custom-stocks', {
            headers: getAuthHeaders()
        });
        const stocks = await res.json();
        
        if (stocks.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">No custom stocks added yet.</td></tr>`;
            return;
        }
        
        tbody.innerHTML = stocks.map(s => `
            <tr>
                <td><strong>${s.sym}</strong></td>
                <td>${s.name}</td>
                <td><span class="sector-column">${s.sector}</span></td>
                <td><code>${s.yahoo}</code></td>
                <td class="text-center">
                    <button class="btn-delete-stock" onclick="deleteCustomStock('${s.sym}')">
                        <i class="fa-solid fa-trash-can"></i> Delete
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (err) {
        console.error("Error loading custom stocks:", err);
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Failed to load custom symbols.</td></tr>`;
    }
}

async function addCustomStock(e) {
    e.preventDefault();
    const sym = document.getElementById('addSym').value.toUpperCase().trim();
    const yahoo = document.getElementById('addYahoo').value.trim();
    const name = document.getElementById('addName').value.trim();
    const sector = document.getElementById('addSector').value;
    
    try {
        const res = await fetch('/api/custom-stocks', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({ sym, yahoo, name, sector })
        });
        const result = await res.json();
        
        if (result.status === "ok") {
            document.getElementById('addStockForm').reset();
            await loadCustomStocks();
            await loadData();
        } else {
            alert("Error: " + (result.message || "Failed to add stock"));
        }
    } catch(err) {
        console.error("Error adding custom stock:", err);
        alert("Failed to connect to server.");
    }
}

async function deleteCustomStock(sym) {
    if (!confirm(`Are you sure you want to remove '${sym}'?`)) return;
    
    try {
        const res = await fetch(`/api/custom-stocks/${sym}`, { 
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const result = await res.json();
        
        if (result.status === "ok") {
            await loadCustomStocks();
            await loadData();
        } else {
            alert("Error: " + (result.message || "Failed to delete"));
        }
    } catch(err) {
        console.error("Error deleting custom stock:", err);
        alert("Failed to connect to server.");
    }
}

// Bind to window for inline onclick execution
window.deleteCustomStock = deleteCustomStock;

function openStocksModal() {
    checkPasswordProtection(() => {
        document.getElementById('stocksModal').style.display = 'flex';
        loadCustomStocks();
    });
}

function closeStocksModal() {
    document.getElementById('stocksModal').style.display = 'none';
}


// ═══════════════════════════════════════════════════════════════
//  EVENT LISTENERS
// ═══════════════════════════════════════════════════════════════
document.getElementById('searchBox').addEventListener('keyup', renderTable);
document.getElementById('signalFilter').addEventListener('change', renderTable);
if (document.getElementById('indicatorFilter')) {
    document.getElementById('indicatorFilter').addEventListener('change', renderTable);
}
document.getElementById('btnScan').addEventListener('click', triggerScan);

// Bind sortable headers
document.querySelectorAll('.sortable-headers th').forEach(th => {
    th.addEventListener('click', () => {
        const field = th.getAttribute('data-sort');
        if (!field) return;

        if (currentSortField === field) {
            currentSortOrder = currentSortOrder === 'desc' ? 'asc' : 'desc';
        } else {
            currentSortField = field;
            currentSortOrder = 'desc'; // default to descending
        }

        renderTable();
    });
});

// Bind sortable headers for performance table
document.querySelectorAll('.sortable-headers-perf th').forEach(th => {
    th.addEventListener('click', () => {
        const field = th.getAttribute('data-sort-perf');
        if (!field) return;

        if (currentPerfSortField === field) {
            currentPerfSortOrder = currentPerfSortOrder === 'desc' ? 'asc' : 'desc';
        } else {
            currentPerfSortField = field;
            currentPerfSortOrder = 'desc'; // default to descending
        }

        renderPerformanceTable();
    });
});


// CSV Upload handler
const btnUploadCSV = document.getElementById('btnUploadCSV');
const csvFileInput = document.getElementById('csvFileInput');

if (btnUploadCSV && csvFileInput) {
    btnUploadCSV.addEventListener('click', () => {
        checkPasswordProtection(() => {
            csvFileInput.click();
        });
    });

    csvFileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);
        
        csvFileInput.value = ''; // Reset

        try {
            btnUploadCSV.classList.add('loading');
            btnUploadCSV.querySelector('span').textContent = 'Uploading...';

            const response = await fetch('/api/upload-csv', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: formData
            });
            const result = await response.json();

            btnUploadCSV.classList.remove('loading');
            btnUploadCSV.querySelector('span').textContent = 'Upload CSV';

            if (result.status === 'ok') {
                alert(`CSV Processing Complete!\n\nImported: ${result.imported} new stocks\nSkipped duplicates: ${result.skipped_duplicates}\nFailed resolutions: ${result.failed_resolutions}`);
                await loadData();
            } else {
                alert('Upload failed: ' + (result.message || 'Unknown error'));
            }
        } catch (err) {
            btnUploadCSV.classList.remove('loading');
            btnUploadCSV.querySelector('span').textContent = 'Upload CSV';
            console.error('Error uploading CSV:', err);
            alert('Error connecting to backend server.');
        }
    });
}

// Capital Input change → recalculate everything instantly
document.getElementById('capitalInput').addEventListener('input', () => {
    const val = parseInt(document.getElementById('capitalInput').value, 10);
    userCapital = isNaN(val) || val < 1000 ? 1000 : val;
    updateRiskPanel();
    renderTopPicks();
    renderTable();
    if (activeModalSymbol) {
        const stock = allStocks.find(s => s.sym === activeModalSymbol);
        if (stock) updateModalDetails(stock);
    }
});

// Cap filter change → re-render table
const capFilterEl = document.getElementById('capFilter');
if (capFilterEl) capFilterEl.addEventListener('change', () => renderTable());

// Indicator filter change → re-render table
const indFilterEl = document.getElementById('indicatorFilter');
if (indFilterEl) indFilterEl.addEventListener('change', () => renderTable());

// Signal filter change → re-render table  
const sigFilterEl = document.getElementById('signalFilter');
if (sigFilterEl) sigFilterEl.addEventListener('change', () => renderTable());

// Search box → re-render table
const searchBoxEl = document.getElementById('searchBox');
if (searchBoxEl) searchBoxEl.addEventListener('input', () => renderTable());


// Risk % Slider change → update display and recalculate
document.getElementById('riskPctSlider').addEventListener('input', () => {
    userRiskPct = parseFloat(document.getElementById('riskPctSlider').value);
    document.getElementById('riskPctDisplay').textContent = userRiskPct + "%";
    updateRiskPanel();
    renderTopPicks();
    renderTable();
    if (activeModalSymbol) {
        const stock = allStocks.find(s => s.sym === activeModalSymbol);
        if (stock) updateModalDetails(stock);
    }
});

// Target Goal % Slider change → update display and recalculate
document.getElementById('targetPctSlider').addEventListener('input', () => {
    userTargetPct = parseInt(document.getElementById('targetPctSlider').value, 10);
    document.getElementById('targetPctDisplay').textContent = userTargetPct + "%";
    
    // Update slider background gradient matching theme design
    const slider = document.getElementById('targetPctSlider');
    const pct = ((userTargetPct - 1) / (15 - 1)) * 100;
    slider.style.background = `linear-gradient(to right, var(--accent) 0%, var(--accent) ${pct}%, rgba(255,255,255,0.1) ${pct}%, rgba(255,255,255,0.1) 100%)`;
    
    renderTable();
    if (activeModalSymbol) {
        const stock = allStocks.find(s => s.sym === activeModalSymbol);
        if (stock) updateModalDetails(stock);
    }
});

// Modal close button
document.getElementById('posModalClose').addEventListener('click', closeModal);

// Close modal when clicking outside
document.getElementById('posModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('posModal')) closeModal();
});

// Stocks Modal bindings
document.getElementById('btnManageStocks').addEventListener('click', openStocksModal);
document.getElementById('stocksModalClose').addEventListener('click', closeStocksModal);
document.getElementById('stocksModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('stocksModal')) closeStocksModal();
});
document.getElementById('addStockForm').addEventListener('submit', addCustomStock);

// Details tabs bindings
document.getElementById('btnTabChart').addEventListener('click', () => {
    document.getElementById('btnTabChart').classList.add('active');
    document.getElementById('btnTabScore').classList.remove('active');
    document.getElementById('modalChartContainer').style.display = 'block';
    document.getElementById('modalScoreHistoryContainer').style.display = 'none';
    
    const sym = document.getElementById('posModalSym').textContent;
    const stock = allStocks.find(s => s.sym === sym);
    if (stock) {
        if (!lightweightChart) {
            const pos = calcPosition(stock);
            renderTechnicalChart(stock.sym, stock.price, stock.slPrice, pos.tgt2Price);
        } else {
            // Trigger resize immediately to fit the block container
            const w = document.getElementById('modalChartContainer').clientWidth;
            if (w > 0) lightweightChart.resize(w, 300);
        }
    }
});

document.getElementById('btnTabScore').addEventListener('click', () => {
    document.getElementById('btnTabChart').classList.remove('active');
    document.getElementById('btnTabScore').classList.add('active');
    document.getElementById('modalChartContainer').style.display = 'none';
    document.getElementById('modalScoreHistoryContainer').style.display = 'block';
    
    const sym = document.getElementById('posModalSym').textContent;
    if (!scoreTrendChart) {
        renderScoreHistory(sym);
    } else {
        // Trigger resize immediately to fit the block container
        const w = document.getElementById('modalScoreHistoryContainer').clientWidth;
        if (w > 0) scoreTrendChart.resize(w, 300);
    }
});

// Escape key closes modals
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
        closeStocksModal();
        closeSettingsModal();
    }
});


// ═══════════════════════════════════════════════════════════════
//  SETTINGS MODAL — Telegram Alerts
// ═══════════════════════════════════════════════════════════════
function openSettingsModal() {
    checkPasswordProtection(() => {
        document.getElementById('settingsModalOverlay').style.display = 'flex';
        loadSettingsIntoModal();
    });
}

function closeSettingsModal() {
    document.getElementById('settingsModalOverlay').style.display = 'none';
    // Clear test status on close
    const st = document.getElementById('telegramTestStatus');
    st.style.display = 'none';
    st.className = 'test-status';
    st.textContent = '';
}

async function loadSettingsIntoModal() {
    try {
        const res  = await fetch('/api/settings', {
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (data.status !== 'ok') return;
        const s = data.settings;

        // Telegram token — show masked
        const tokenInput = document.getElementById('telegramToken');
        tokenInput.placeholder = s.telegram_token_masked || 'Enter Bot Token...';
        tokenInput.value = '';   // never pre-fill real token for security

        document.getElementById('telegramChatId').value    = s.telegram_chat_id || '';
        document.getElementById('alertsEnabled').checked   = !!s.alerts_enabled;
        document.getElementById('alertOnScan').checked     = s.alert_on_scan !== false;
        document.getElementById('alertLimit').value        = s.alert_limit || 10;
        const scoreSlider = document.getElementById('alertMinScore');
        const scoreVal    = document.getElementById('alertMinScoreVal');
        scoreSlider.value = s.alert_min_score || 70;
        scoreVal.textContent = scoreSlider.value;

        // Show green dot on Settings button if alerts are active
        const badge = document.getElementById('settingsAlertBadge');
        if (badge) badge.style.display = s.alerts_enabled ? 'block' : 'none';
    } catch (e) {
        console.error('Error loading settings:', e);
    }
}

async function saveSettings() {
    const token   = document.getElementById('telegramToken').value.trim();
    const chatId  = document.getElementById('telegramChatId').value.trim();
    const enabled = document.getElementById('alertsEnabled').checked;
    const onScan  = document.getElementById('alertOnScan').checked;
    const minScore= parseInt(document.getElementById('alertMinScore').value, 10);
    const limit   = parseInt(document.getElementById('alertLimit').value, 10) || 10;

    const payload = {
        alerts_enabled:   enabled,
        alert_on_scan:    onScan,
        alert_min_score:  minScore,
        alert_limit:      limit,
        telegram_chat_id: chatId,
    };
    if (token && !token.includes('•')) payload.telegram_token = token;

    try {
        const res  = await fetch('/api/settings', {
            method:  'POST',
            headers: { 
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body:    JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast('Settings saved successfully!', 'success');
            // Update badge
            const badge = document.getElementById('settingsAlertBadge');
            if (badge) badge.style.display = enabled ? 'block' : 'none';
            closeSettingsModal();
        } else {
            showToast('Failed to save settings.', 'error');
        }
    } catch (e) {
        showToast('Server error saving settings.', 'error');
    }
}

async function testTelegramConnection() {
    const token  = document.getElementById('telegramToken').value.trim();
    const chatId = document.getElementById('telegramChatId').value.trim();
    const btn    = document.getElementById('btnTestTelegram');
    const status = document.getElementById('telegramTestStatus');

    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sending...';
    status.style.display = 'none';

    try {
        const res  = await fetch('/api/settings/test', {
            method:  'POST',
            headers: { 
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body:    JSON.stringify({ telegram_token: token, telegram_chat_id: chatId })
        });
        const data = await res.json();
        status.style.display = 'inline-block';
        if (data.status === 'ok') {
            status.className = 'test-status success';
            status.innerHTML = '✅ ' + data.message;
        } else {
            status.className = 'test-status error';
            status.innerHTML = '❌ ' + data.message;
        }
    } catch (e) {
        status.style.display = 'inline-block';
        status.className = 'test-status error';
        status.innerHTML = '❌ Connection error. Is the server running?';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Test Connection';
    }
}

// Wire Settings modal buttons
document.getElementById('btnSettings').addEventListener('click', openSettingsModal);
document.getElementById('btnCloseSettings').addEventListener('click', closeSettingsModal);
document.getElementById('btnCancelSettings').addEventListener('click', closeSettingsModal);
document.getElementById('btnSaveSettings').addEventListener('click', saveSettings);
document.getElementById('btnTestTelegram').addEventListener('click', testTelegramConnection);
document.getElementById('settingsModalOverlay').addEventListener('click', (e) => {
    if (e.target === document.getElementById('settingsModalOverlay')) closeSettingsModal();
});

// Min-score slider live preview
document.getElementById('alertMinScore').addEventListener('input', (e) => {
    document.getElementById('alertMinScoreVal').textContent = e.target.value;
});


// ═══════════════════════════════════════════════════════════════
//  SECTOR HEATMAP WIDGET
// ═══════════════════════════════════════════════════════════════
async function loadSectorHeatmap() {
    const container = document.getElementById('sectorHeatmap');
    if (!container) return;

    try {
        const res  = await fetch('/api/sector-analysis');
        const data = await res.json();
        if (data.status !== 'ok' || !data.sectors || data.sectors.length === 0) {
            container.innerHTML = '<div class="text-muted" style="padding:12px 0;font-size:0.8rem;">No data yet. Run a scan first.</div>';
            return;
        }

        container.innerHTML = data.sectors.map(sec => {
            const buyRate  = Math.round(sec.buyRate);
            const heat     = buyRate >= 60 ? 'hot' : buyRate >= 30 ? 'warm' : 'cold';
            const barColor = heat === 'hot' ? '#10b981' : heat === 'warm' ? '#f59e0b' : '#6b7280';
            return `
            <div class="sector-heat-row" title="${sec.sector}: ${sec.buy} BUY / ${sec.total} stocks | Avg Score: ${sec.avgScore}">
                <div class="sector-heat-label">
                    <span class="sector-heat-name">${sec.sector}</span>
                    <span class="sector-heat-meta">${sec.buy}/${sec.total} BUY</span>
                </div>
                <div class="sector-heat-bar-track">
                    <div class="sector-heat-bar-fill" style="width:${buyRate}%;background:${barColor};"></div>
                </div>
                <span class="sector-heat-pct" style="color:${barColor};">${buyRate}%</span>
            </div>`;
        }).join('');
    } catch (e) {
        console.error('Error loading sector heatmap:', e);
    }
}

// Theme Toggle Event Listener
document.getElementById('btnThemeToggle').addEventListener('click', () => {
    document.body.classList.toggle('light-mode');
    const isLight = document.body.classList.contains('light-mode');
    
    // Update toggle icon
    const icon = document.getElementById('btnThemeToggle').querySelector('i');
    if (isLight) {
        icon.className = 'fa-solid fa-sun';
        localStorage.setItem('theme', 'light');
    } else {
        icon.className = 'fa-solid fa-moon';
        localStorage.setItem('theme', 'dark');
    }
    
    // Refresh open modal charts if visible to update chart colors
    const sym = document.getElementById('posModalSym').textContent;
    if (document.getElementById('posModal').style.display === 'flex' && sym !== 'STOCK') {
        clearCharts();
        const stock = allStocks.find(s => s.sym === sym);
        if (stock) {
            const pos = calcPosition(stock);
            const isScoreTab = document.getElementById('btnTabScore').classList.contains('active');
            if (isScoreTab) {
                renderScoreHistory(stock.sym);
            } else {
                renderTechnicalChart(stock.sym, stock.price, stock.slPrice, pos.tgt2Price);
            }
        }
    }
});


// ═══════════════════════════════════════════════════════════════
//  EOD PERFORMANCE TRACKER ENGINE
// ═══════════════════════════════════════════════════════════════
async function loadPerformanceEvaluation(compareScanId = null) {
    const tbody = document.getElementById('performanceTableBody');
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:40px 0;"><i class="fa-solid fa-spinner fa-spin"></i> Running performance calculations...</td></tr>`;
    currentPerfResults = [];


    try {
        let url = '/api/performance';
        if (compareScanId) {
            url += `?compare_scan_id=${compareScanId}`;
        }
        const res = await fetch(url);
        const data = await res.json();

        if (data.status === 'insufficient_data') {
            tbody.innerHTML = `
            <tr><td colspan="7" class="text-center text-muted" style="padding:40px 0;">
                <i class="fa-solid fa-triangle-exclamation" style="font-size:2rem;opacity:0.4;display:block;margin-bottom:8px;"></i>
                ${data.message}
            </td></tr>`;
            
            // Populate select with whatever scans exist
            populateScansDropdown(data.scans_list || [], null);
            resetPerformanceStats();
            return;
        }

        if (data.status !== 'ok') {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:40px 0;">Failed to load evaluation metrics: ${data.message || 'Unknown error'}</td></tr>`;
            return;
        }

        // 1. Populate scans dropdown
        populateScansDropdown(data.scans_list, data.compare_scan.id);

        // 2. Render aggregate metrics cards
        const m = data.metrics;
        document.getElementById('perfAvgReturn').textContent = `${m.avgReturn > 0 ? '+' : ''}${m.avgReturn}%`;
        document.getElementById('perfAvgReturn').className = `perf-val ${m.avgReturn >= 0 ? 'profit' : 'loss'}`;
        
        document.getElementById('perfWinRate').textContent = `${m.winRate}%`;
        document.getElementById('perfWinRate').className = `perf-val ${m.winRate >= 50 ? 'profit' : 'loss'}`;
        
        document.getElementById('perfNiftyReturn').textContent = `${m.niftyReturn > 0 ? '+' : ''}${m.niftyReturn}%`;
        document.getElementById('perfNiftyReturn').className = `perf-val ${m.niftyReturn >= 0 ? 'profit' : 'loss'}`;
        
        document.getElementById('perfTotalRecs').textContent = m.totalCount;

        // 3. Best / Worst Performers widget
        if (m.bestStock !== '—') {
            document.getElementById('perfBestStock').textContent = m.bestStock;
            document.getElementById('perfBestReturn').textContent = `+${m.bestReturn}%`;
        } else {
            document.getElementById('perfBestStock').textContent = '—';
            document.getElementById('perfBestReturn').textContent = '0.0%';
        }

        if (m.worstStock !== '—') {
            document.getElementById('perfWorstStock').textContent = m.worstStock;
            document.getElementById('perfWorstReturn').textContent = `${m.worstReturn}%`;
            document.getElementById('perfWorstReturn').className = m.worstReturn >= 0 ? 'profit' : 'loss';
        } else {
            document.getElementById('perfWorstStock').textContent = '—';
            document.getElementById('perfWorstReturn').textContent = '0.0%';
            document.getElementById('perfWorstReturn').className = 'loss';
        }

        // 4. Comparative list table rows
        currentPerfResults = data.results || [];
        if (currentPerfResults.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:40px 0;">No BUY/STRONG BUY signals in the selected historical scan to evaluate.</td></tr>`;
            return;
        }

        renderPerformanceTable();


    } catch (err) {
        console.error("Error evaluating performance:", err);
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:40px 0;">Failed to fetch evaluation metrics. Connection error.</td></tr>`;
    }
}

function populateScansDropdown(scansList, selectedScanId) {
    const select = document.getElementById('compareScanSelect');
    if (!select) return;

    if (scansList.length === 0) {
        select.innerHTML = '<option value="">No history available</option>';
        return;
    }

    // Generate options
    select.innerHTML = scansList.map((s, idx) => {
        // Skips the latest scan as we can't evaluate the latest scan against itself
        if (idx === 0) return '';
        
        const dateObj = new Date(s.scanned_at);
        const formattedDate = dateObj.toLocaleString('en-IN', {
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
        });
        const isSelected = s.id === selectedScanId ? 'selected' : '';
        const name = `Scan: ${formattedDate} (${s.nifty_mood})`;
        return `<option value="${s.id}" ${isSelected}>${name}</option>`;
    }).join('');
}

function resetPerformanceStats() {
    currentPerfResults = [];
    document.getElementById('perfAvgReturn').textContent = '0.0%';
    document.getElementById('perfAvgReturn').className = 'perf-val';
    document.getElementById('perfWinRate').textContent = '0.0%';
    document.getElementById('perfWinRate').className = 'perf-val';
    document.getElementById('perfNiftyReturn').textContent = '0.0%';
    document.getElementById('perfNiftyReturn').className = 'perf-val';
    document.getElementById('perfTotalRecs').textContent = '0';
    document.getElementById('perfBestStock').textContent = '—';
    document.getElementById('perfBestReturn').textContent = '0.0%';
    document.getElementById('perfWorstStock').textContent = '—';
    document.getElementById('perfWorstReturn').textContent = '0.0%';
}


// ═══════════════════════════════════════════════════════════════
//  DASHBOARD TAB SWITCHER & COMPARATIVE SCAN LISTENERS
// ═══════════════════════════════════════════════════════════════
// Tab Switcher
document.getElementById('btnTabScreener').addEventListener('click', () => {
    document.getElementById('btnTabScreener').classList.add('active');
    document.getElementById('btnTabPerformance').classList.remove('active');
    document.getElementById('screenerTablePanel').style.display = 'block';
    document.getElementById('performancePanel').style.display = 'none';
});

document.getElementById('btnTabPerformance').addEventListener('click', () => {
    document.getElementById('btnTabScreener').classList.remove('active');
    document.getElementById('btnTabPerformance').classList.add('active');
    document.getElementById('screenerTablePanel').style.display = 'none';
    document.getElementById('performancePanel').style.display = 'block';
    
    // Fetch and populate performance comparison
    loadPerformanceEvaluation();
});

// Dropdown change triggers loading scan EOD performance
document.getElementById('compareScanSelect').addEventListener('change', (e) => {
    const val = e.target.value;
    if (val) {
        loadPerformanceEvaluation(val);
    }
});


// ═══════════════════════════════════════════════════════════════
//  INITIALIZATION
// ═══════════════════════════════════════════════════════════════
// Load theme preference on initial boot
const savedTheme = localStorage.getItem('theme');
if (savedTheme === 'light') {
    document.body.classList.add('light-mode');
    document.getElementById('btnThemeToggle').querySelector('i').className = 'fa-solid fa-sun';
}

loadData();
loadNifty();
checkActiveScan();
loadSectorHeatmap();

// Load alert badge state on boot
loadSettingsIntoModal().catch(() => {});

// Auto-refresh every 30 seconds
setInterval(loadData, 30000);
setInterval(loadNifty, 30000);
setInterval(loadSectorHeatmap, 60000);

// Window resize handler to adjust TradingView charts dynamically
window.addEventListener('resize', () => {
    if (lightweightChart) {
        const container = document.getElementById('modalChartContainer');
        if (container) {
            lightweightChart.resize(container.clientWidth, 300);
        }
    }
    if (scoreTrendChart) {
        const container = document.getElementById('modalScoreHistoryContainer');
        if (container) {
            scoreTrendChart.resize(container.clientWidth, 300);
        }
    }
});

// Custom Visual Toast Notification Helper
function showToast(message, type = 'success') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast-item ${type}`;
    const icon = type === 'success' ? 'fa-circle-check' : 'fa-circle-xmark';
    const color = type === 'success' ? '#10B981' : '#EF4444';
    toast.innerHTML = `
        <i class="fa-solid ${icon}" style="color:${color};font-size:1.15rem;"></i>
        <span class="toast-message">${message}</span>
    `;
    container.appendChild(toast);
    setTimeout(() => { toast.classList.add('show'); }, 10);
    setTimeout(() => {
        toast.classList.remove('show');
        toast.classList.add('hide');
        setTimeout(() => {
            toast.remove();
            if (container.children.length === 0) {
                container.remove();
            }
        }, 300);
    }, 3500);
}