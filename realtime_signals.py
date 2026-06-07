"""
Real-Time Stock Signal Dashboard
=================================
Fetches live data from Yahoo Finance every 60 seconds,
computes technical indicators, and outputs BUY / SELL / HOLD signals.

Run:  python realtime_signals.py
Then open:  http://localhost:5000
"""

import warnings
warnings.filterwarnings("ignore")

import json, time, threading
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta

from flask import Flask, render_template_string

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
WATCHLIST = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "SPY"]
REFRESH_SECONDS = 60   # how often to pull new data
_cache = {}            # in-memory store: ticker → signal dict


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def compute_signals(ticker: str) -> dict:
    """
    Pull 6 months of daily OHLCV, compute indicators, and return a signal dict.
    Signal logic (rule-based, transparent):
      STRONG BUY  : RSI < 35  AND price > SMA20  AND MACD hist > 0
      BUY         : RSI < 45  AND price > SMA20
      STRONG SELL : RSI > 65  AND price < SMA20  AND MACD hist < 0
      SELL        : RSI > 55  AND price < SMA20
      HOLD        : everything else
    """
    try:
        df = yf.download(ticker, period="6mo", interval="1d",
                         auto_adjust=True, progress=False)
        if df.empty or len(df) < 30:
            return {"ticker": ticker, "error": "No data"}

        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        close = df["Close"].squeeze()
        high  = df["High"].squeeze()
        low   = df["Low"].squeeze()
        vol   = df["Volume"].squeeze()

        # Indicators
        rsi    = ta.rsi(close, length=14)
        macd_r = ta.macd(close, fast=12, slow=26, signal=9)
        sma20  = ta.sma(close, length=20)
        sma50  = ta.sma(close, length=50)
        bb     = ta.bbands(close, length=20, std=2)
        bb_cols = bb.columns.tolist()
        bb_upper = bb[[c for c in bb_cols if c.startswith("BBU")][0]]
        bb_lower = bb[[c for c in bb_cols if c.startswith("BBL")][0]]

        # Latest values
        price      = float(close.iloc[-1])
        prev_price = float(close.iloc[-2])
        chg_pct    = (price - prev_price) / prev_price * 100

        rsi_val    = float(rsi.iloc[-1])
        macd_hist  = float(macd_r.iloc[-1, 2])   # MACDh column
        sma20_val  = float(sma20.iloc[-1])
        sma50_val  = float(sma50.iloc[-1])
        bb_u       = float(bb_upper.iloc[-1])
        bb_l       = float(bb_lower.iloc[-1])
        bb_pct     = (price - bb_l) / (bb_u - bb_l + 1e-9)

        # 52-week high/low
        df_1y = yf.download(ticker, period="1y", interval="1d",
                            auto_adjust=True, progress=False)
        c1y = df_1y["Close"].squeeze() if not df_1y.empty else close
        wk52_high = float(c1y.max())
        wk52_low  = float(c1y.min())

        # Volume ratio
        avg_vol  = float(vol.rolling(10).mean().iloc[-1])
        curr_vol = float(vol.iloc[-1])
        vol_ratio = curr_vol / (avg_vol + 1)

        # ── Signal logic ────────────────────────────────────────────────────
        above_sma20 = price > sma20_val
        above_sma50 = price > sma50_val

        if rsi_val < 35 and above_sma20 and macd_hist > 0:
            signal = "STRONG BUY"
            confidence = 90
        elif rsi_val < 45 and above_sma20:
            signal = "BUY"
            confidence = 70
        elif rsi_val > 65 and not above_sma20 and macd_hist < 0:
            signal = "STRONG SELL"
            confidence = 88
        elif rsi_val > 55 and not above_sma20:
            signal = "SELL"
            confidence = 65
        elif rsi_val < 50 and above_sma20 and above_sma50:
            signal = "BUY"
            confidence = 60
        else:
            signal = "HOLD"
            confidence = 50

        # Adjust confidence by volume
        if vol_ratio > 1.5:
            confidence = min(95, confidence + 5)

        # Price targets (simple ATR-based)
        atr = float((high - low).rolling(14).mean().iloc[-1])
        if "BUY" in signal:
            target    = round(price + 2 * atr, 2)
            stop_loss = round(price - 1.5 * atr, 2)
        elif "SELL" in signal:
            target    = round(price - 2 * atr, 2)
            stop_loss = round(price + 1.5 * atr, 2)
        else:
            target    = round(price + atr, 2)
            stop_loss = round(price - atr, 2)

        # Spark data (last 30 closes normalised)
        spark = close.iloc[-30:].tolist()

        return {
            "ticker":     ticker,
            "price":      round(price, 2),
            "chg_pct":    round(chg_pct, 2),
            "signal":     signal,
            "confidence": confidence,
            "rsi":        round(rsi_val, 1),
            "macd_hist":  round(macd_hist, 4),
            "sma20":      round(sma20_val, 2),
            "sma50":      round(sma50_val, 2),
            "bb_pct":     round(bb_pct * 100, 1),
            "vol_ratio":  round(vol_ratio, 2),
            "target":     target,
            "stop_loss":  stop_loss,
            "wk52_high":  round(wk52_high, 2),
            "wk52_low":   round(wk52_low, 2),
            "spark":      [round(x, 2) for x in spark],
            "updated":    datetime.now().strftime("%H:%M:%S"),
            "error":      None,
        }

    except Exception as e:
        return {"ticker": ticker, "error": str(e), "signal": "N/A"}


def refresh_all():
    """Fetch signals for all tickers and update cache."""
    for ticker in WATCHLIST:
        _cache[ticker] = compute_signals(ticker)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Signals refreshed")


def background_refresh():
    """Background thread: refresh every REFRESH_SECONDS."""
    while True:
        refresh_all()
        time.sleep(REFRESH_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# HTML DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crystal Ball — Live Signals</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #080c10;
    --surface:  #0d1117;
    --card:     #111820;
    --border:   #1e2830;
    --text:     #cdd9e5;
    --muted:    #768390;
    --green:    #3fb950;
    --red:      #f85149;
    --blue:     #58a6ff;
    --yellow:   #d29922;
    --strong-buy:  #00ff88;
    --buy:         #3fb950;
    --hold:        #58a6ff;
    --sell:        #f0883e;
    --strong-sell: #f85149;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    min-height: 100vh;
  }

  /* ── HEADER ── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 32px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .logo {
    font-family: 'Space Mono', monospace;
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--blue);
    letter-spacing: 2px;
  }
  .logo span { color: var(--green); }
  .status {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.78rem;
    color: var(--muted);
    font-family: 'Space Mono', monospace;
  }
  .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  #countdown {
    color: var(--blue);
    font-weight: 700;
  }

  /* ── SUMMARY BAR ── */
  .summary {
    display: flex;
    gap: 16px;
    padding: 16px 32px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    overflow-x: auto;
  }
  .summary-pill {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    white-space: nowrap;
    font-family: 'Space Mono', monospace;
  }
  .pill-buy   { background: rgba(63,185,80,0.15);  color: var(--green); border: 1px solid rgba(63,185,80,0.3); }
  .pill-sell  { background: rgba(248,81,73,0.15);  color: var(--red);   border: 1px solid rgba(248,81,73,0.3); }
  .pill-hold  { background: rgba(88,166,255,0.15); color: var(--blue);  border: 1px solid rgba(88,166,255,0.3); }

  /* ── GRID ── */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
    padding: 24px 32px;
  }

  /* ── CARD ── */
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    transition: border-color 0.2s, transform 0.2s;
    position: relative;
    overflow: hidden;
  }
  .card:hover {
    transform: translateY(-2px);
    border-color: var(--blue);
  }
  .card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
  }
  .card.STRONG\\ BUY::before  { background: var(--strong-buy); }
  .card.BUY::before           { background: var(--buy); }
  .card.HOLD::before          { background: var(--hold); }
  .card.SELL::before          { background: var(--sell); }
  .card.STRONG\\ SELL::before { background: var(--strong-sell); }

  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 14px;
  }
  .ticker {
    font-family: 'Space Mono', monospace;
    font-size: 1.4rem;
    font-weight: 700;
    color: white;
  }
  .price-block { text-align: right; }
  .price {
    font-family: 'Space Mono', monospace;
    font-size: 1.3rem;
    font-weight: 700;
    color: white;
  }
  .chg {
    font-size: 0.82rem;
    font-weight: 600;
    font-family: 'Space Mono', monospace;
  }
  .chg.pos { color: var(--green); }
  .chg.neg { color: var(--red); }

  /* ── SIGNAL BADGE ── */
  .signal-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
  }
  .signal-badge {
    padding: 5px 14px;
    border-radius: 6px;
    font-family: 'Space Mono', monospace;
    font-size: 0.85rem;
    font-weight: 700;
    letter-spacing: 1px;
  }
  .badge-STRONG\\ BUY  { background: rgba(0,255,136,0.15); color: var(--strong-buy); border: 1px solid var(--strong-buy); }
  .badge-BUY          { background: rgba(63,185,80,0.15);  color: var(--buy);        border: 1px solid var(--buy); }
  .badge-HOLD         { background: rgba(88,166,255,0.15); color: var(--hold);       border: 1px solid var(--hold); }
  .badge-SELL         { background: rgba(240,136,62,0.15); color: var(--sell);       border: 1px solid var(--sell); }
  .badge-STRONG\\ SELL{ background: rgba(248,81,73,0.15);  color: var(--strong-sell);border: 1px solid var(--strong-sell); }

  .confidence {
    font-size: 0.78rem;
    color: var(--muted);
    font-family: 'Space Mono', monospace;
  }

  /* ── SPARK LINE ── */
  canvas.spark {
    width: 100%;
    height: 48px;
    margin-bottom: 14px;
    border-radius: 4px;
  }

  /* ── METRICS ── */
  .metrics {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
    margin-bottom: 14px;
  }
  .metric {
    background: var(--surface);
    border-radius: 6px;
    padding: 8px 10px;
    border: 1px solid var(--border);
  }
  .metric-label {
    font-size: 0.68rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 3px;
  }
  .metric-value {
    font-family: 'Space Mono', monospace;
    font-size: 0.88rem;
    font-weight: 700;
    color: white;
  }
  .metric-value.rsi-ob { color: var(--red); }
  .metric-value.rsi-os { color: var(--green); }

  /* ── TARGETS ── */
  .targets {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .target-box {
    border-radius: 6px;
    padding: 8px 12px;
    text-align: center;
  }
  .target-box.tp {
    background: rgba(63,185,80,0.08);
    border: 1px solid rgba(63,185,80,0.25);
  }
  .target-box.sl {
    background: rgba(248,81,73,0.08);
    border: 1px solid rgba(248,81,73,0.25);
  }
  .target-label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--muted);
    margin-bottom: 2px;
  }
  .target-value {
    font-family: 'Space Mono', monospace;
    font-size: 0.92rem;
    font-weight: 700;
  }
  .tp .target-value { color: var(--green); }
  .sl .target-value { color: var(--red); }

  /* ── RSI BAR ── */
  .rsi-bar-wrap {
    margin: 12px 0 4px;
  }
  .rsi-bar-label {
    font-size: 0.7rem;
    color: var(--muted);
    margin-bottom: 4px;
    display: flex;
    justify-content: space-between;
  }
  .rsi-track {
    height: 5px;
    background: var(--border);
    border-radius: 3px;
    position: relative;
    margin-bottom: 10px;
  }
  .rsi-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s;
  }
  .rsi-marker {
    position: absolute;
    top: -3px;
    width: 11px; height: 11px;
    border-radius: 50%;
    background: white;
    border: 2px solid var(--blue);
    transform: translateX(-50%);
    transition: left 0.5s;
  }

  .updated {
    font-size: 0.68rem;
    color: var(--muted);
    font-family: 'Space Mono', monospace;
    margin-top: 12px;
    text-align: right;
  }

  /* ── LOADING ── */
  .loading {
    text-align: center;
    padding: 80px;
    color: var(--muted);
    font-family: 'Space Mono', monospace;
    font-size: 0.9rem;
  }
  .spinner {
    width: 40px; height: 40px;
    border: 3px solid var(--border);
    border-top-color: var(--blue);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto 20px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── DISCLAIMER ── */
  .disclaimer {
    text-align: center;
    padding: 16px 32px;
    color: var(--muted);
    font-size: 0.72rem;
    border-top: 1px solid var(--border);
    margin-top: 8px;
  }
</style>
</head>
<body>

<header>
  <div class="logo">CRYSTAL <span>BALL</span> // SIGNALS</div>
  <div class="status">
    <div class="dot"></div>
    LIVE &nbsp;|&nbsp; refreshes in <span id="countdown">60</span>s &nbsp;|&nbsp;
    <span id="last-update">loading…</span>
  </div>
</header>

<div class="summary" id="summary-bar">
  <div class="summary-pill pill-hold">Loading signals…</div>
</div>

<div class="grid" id="grid">
  <div class="loading">
    <div class="spinner"></div>
    Fetching live market data…
  </div>
</div>

<div class="disclaimer">
  ⚠️ For educational purposes only. Not financial advice. Always do your own research before trading.
</div>

<script>
// ── Spark line renderer ──────────────────────────────────────────────────────
function drawSpark(canvas, data, signal) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width  = canvas.offsetWidth  * window.devicePixelRatio;
  const h = canvas.height = canvas.offsetHeight * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

  const W = canvas.offsetWidth;
  const H = canvas.offsetHeight;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const colorMap = {
    'STRONG BUY': '#00ff88',
    'BUY':        '#3fb950',
    'HOLD':       '#58a6ff',
    'SELL':       '#f0883e',
    'STRONG SELL':'#f85149',
  };
  const color = colorMap[signal] || '#58a6ff';

  ctx.beginPath();
  data.forEach((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 4) - 2;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });

  // Fill
  ctx.save();
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, color + '33');
  grad.addColorStop(1, color + '00');
  ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.restore();

  // Line
  ctx.beginPath();
  data.forEach((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 4) - 2;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

// ── RSI colour ───────────────────────────────────────────────────────────────
function rsiColor(v) {
  if (v >= 70) return '#f85149';
  if (v <= 30) return '#3fb950';
  return '#58a6ff';
}

// ── Render cards ─────────────────────────────────────────────────────────────
function renderGrid(data) {
  const grid = document.getElementById('grid');
  const summary = document.getElementById('summary-bar');

  let buys = 0, sells = 0, holds = 0;

  const cards = data.map(d => {
    if (d.error) return `<div class="card"><div class="ticker">${d.ticker}</div><div style="color:var(--red);font-size:0.8rem;margin-top:8px">${d.error}</div></div>`;

    if (d.signal.includes('BUY'))  buys++;
    else if (d.signal.includes('SELL')) sells++;
    else holds++;

    const chgClass = d.chg_pct >= 0 ? 'pos' : 'neg';
    const chgSign  = d.chg_pct >= 0 ? '+' : '';
    const rsiClass = d.rsi >= 70 ? 'rsi-ob' : d.rsi <= 30 ? 'rsi-os' : '';
    const rsiPct   = Math.min(100, Math.max(0, d.rsi));
    const rsiCol   = rsiColor(d.rsi);
    const macdSign = d.macd_hist >= 0 ? '+' : '';

    return `
    <div class="card ${d.signal}" id="card-${d.ticker}">
      <div class="card-top">
        <div class="ticker">${d.ticker}</div>
        <div class="price-block">
          <div class="price">$${d.price.toFixed(2)}</div>
          <div class="chg ${chgClass}">${chgSign}${d.chg_pct.toFixed(2)}%</div>
        </div>
      </div>

      <div class="signal-row">
        <div class="signal-badge badge-${d.signal}">${d.signal}</div>
        <div class="confidence">Confidence: ${d.confidence}%</div>
      </div>

      <canvas class="spark" id="spark-${d.ticker}"></canvas>

      <div class="rsi-bar-wrap">
        <div class="rsi-bar-label"><span>RSI: ${d.rsi}</span><span>30 ← neutral → 70</span></div>
        <div class="rsi-track">
          <div class="rsi-fill" style="width:${rsiPct}%;background:${rsiCol}"></div>
          <div class="rsi-marker" style="left:${rsiPct}%;border-color:${rsiCol}"></div>
        </div>
      </div>

      <div class="metrics">
        <div class="metric">
          <div class="metric-label">RSI (14)</div>
          <div class="metric-value ${rsiClass}">${d.rsi}</div>
        </div>
        <div class="metric">
          <div class="metric-label">MACD Hist</div>
          <div class="metric-value" style="color:${d.macd_hist>=0?'var(--green)':'var(--red)'}">${macdSign}${d.macd_hist.toFixed(3)}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Vol Ratio</div>
          <div class="metric-value" style="color:${d.vol_ratio>1.5?'var(--yellow)':'white'}">${d.vol_ratio}x</div>
        </div>
        <div class="metric">
          <div class="metric-label">SMA 20</div>
          <div class="metric-value">$${d.sma20}</div>
        </div>
        <div class="metric">
          <div class="metric-label">SMA 50</div>
          <div class="metric-value">$${d.sma50}</div>
        </div>
        <div class="metric">
          <div class="metric-label">BB %B</div>
          <div class="metric-value">${d.bb_pct}%</div>
        </div>
      </div>

      <div class="targets">
        <div class="target-box tp">
          <div class="target-label">🎯 Target</div>
          <div class="target-value">$${d.target}</div>
        </div>
        <div class="target-box sl">
          <div class="target-label">🛑 Stop Loss</div>
          <div class="target-value">$${d.stop_loss}</div>
        </div>
      </div>

      <div class="updated">Updated ${d.updated} &nbsp;|&nbsp; 52W: $${d.wk52_low} – $${d.wk52_high}</div>
    </div>`;
  }).join('');

  grid.innerHTML = cards;

  // Draw sparks
  data.forEach(d => {
    if (!d.spark || !d.spark.length) return;
    const canvas = document.getElementById(`spark-${d.ticker}`);
    if (canvas) {
      requestAnimationFrame(() => drawSpark(canvas, d.spark, d.signal));
    }
  });

  // Summary bar
  summary.innerHTML = `
    <div class="summary-pill pill-buy">▲ BUY / STRONG BUY: ${buys}</div>
    <div class="summary-pill pill-hold">◆ HOLD: ${holds}</div>
    <div class="summary-pill pill-sell">▼ SELL / STRONG SELL: ${sells}</div>
  `;

  document.getElementById('last-update').textContent =
    'Last update: ' + new Date().toLocaleTimeString();
}

// ── Fetch & countdown ────────────────────────────────────────────────────────
let secondsLeft = 5;

function fetchData() {
  fetch('/api/signals')
    .then(r => r.json())
    .then(data => { renderGrid(data); secondsLeft = {{ refresh }}; })
    .catch(e => console.error('Fetch error:', e));
}

function tick() {
  secondsLeft--;
  document.getElementById('countdown').textContent = secondsLeft;
  if (secondsLeft <= 0) fetchData();
}

fetchData();
setInterval(tick, 1000);
</script>
</body>
</html>
""".replace("{{ refresh }}", str(REFRESH_SECONDS))


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/signals")
def api_signals():
    data = list(_cache.values()) if _cache else []
    return app.response_class(
        response=json.dumps(data),
        mimetype="application/json"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  CRYSTAL BALL — Real-Time Signal Dashboard")
    print("=" * 55)
    print(f"  Watchlist: {', '.join(WATCHLIST)}")
    print(f"  Refresh  : every {REFRESH_SECONDS}s")
    print(f"  URL      : http://localhost:5000")
    print("=" * 55)
    print("  Fetching initial data (this takes ~30s)…")

    # Initial fetch before starting server
    refresh_all()

    # Background refresh thread
    t = threading.Thread(target=background_refresh, daemon=True)
    t.start()

import os
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port, debug=False)