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

import json, time, threading, logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from flask import Flask, render_template

# Import our new modules
import sys
sys.path.append(str(Path(__file__).parent / "src"))
from config import Config
from data_fetcher import DataFetcher
from signal_engine import compute_signals

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load configuration
config = Config()
config.validate()

# Initialize data fetcher with config values
data_fetcher = DataFetcher(
    timeout=config.YFINANCE_TIMEOUT,
    max_retries=config.YFINANCE_RETRIES,
    backoff_factor=config.YFINANCE_BACKOFF_FACTOR
)

# In-memory store: ticker → signal dict
_cache = {}
_cache_lock = threading.RLock()  # Thread-safe cache access


def refresh_all():
    """Fetch signals for all tickers and update cache."""
    logger.info("Starting signal refresh for all tickers")

    try:
        # Fetch data for all tickers
        batch_results = data_fetcher.fetch_batch_data(config.WATCHLIST)

        # Process results and update cache
        with _cache_lock:
            for ticker in config.WATCHLIST:
                data_6mo, data_1y = batch_results.get(ticker, (None, None))

                if data_6mo is not None and not data_6mo.empty:
                    signal_data = compute_signals(ticker, data_6mo, data_1y, config)
                    _cache[ticker] = signal_data
                    logger.debug(f"Updated signal for {ticker}: {signal_data['signal']}")
                else:
                    # Handle failed ticker
                    error_msg = "Failed to fetch data"
                    _cache[ticker] = {
                        "ticker": ticker,
                        "error": error_msg,
                        "signal": "N/A",
                        "confidence": 0,
                        "updated": datetime.now().strftime("%H:%M:%S")
                    }
                    logger.warning(f"Failed to update {ticker}: {error_msg}")

        logger.info(f"Signal refresh completed. Updated {len([k for k, v in _cache.items() if not v.get('error')])}/{len(config.WATCHLIST)} tickers")

    except Exception as e:
        logger.error(f"Error during signal refresh: {str(e)}")
        # Don't update cache on general failure to avoid corrupting good data


def background_refresh():
    """Background thread: refresh every REFRESH_SECONDS."""
    logger.info(f"Starting background refresh thread (interval: {config.REFRESH_SECONDS}s)")

    while True:
        start_time = time.time()
        refresh_all()
        elapsed = time.time() - start_time

        # Sleep for the remaining time in the interval
        sleep_time = max(0, config.REFRESH_SECONDS - elapsed)
        logger.debug(f"Background refresh took {elapsed:.2f}s, sleeping for {sleep_time:.2f}s")
        time.sleep(sleep_time)


# ─────────────────────────────────────────────────────────────────────────────
# HTML DASHBOARD (using proper template)
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("dashboard.html", refresh=config.REFRESH_SECONDS)


@app.route("/api/signals")
def api_signals():
    with _cache_lock:
        data = list(_cache.values()) if _cache else []
    return app.response_class(
        response=json.dumps(data),
        mimetype="application/json"
    )


@app.route("/health")
def health_check():
    """Health check endpoint for monitoring."""
    with _cache_lock:
        cached_count = len([v for v in _cache.values() if not v.get('error')])
        total_count = len(_cache)

    status = "healthy" if cached_count > 0 else "degraded"
    return {
        "status": status,
        "cached_tickers": cached_count,
        "total_tickers": total_count,
        "timestamp": datetime.now().isoformat()
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("=" * 55)
    logger.info("  CRYSTAL BALL — Real-Time Signal Dashboard")
    logger.info("=" * 55)
    logger.info(f"  Watchlist: {', '.join(config.WATCHLIST)}")
    logger.info(f"  Refresh  : every {config.REFRESH_SECONDS}s")
    logger.info(f"  URL      : http://{config.HOST}:{config.PORT}")
    logger.info("=" * 55)
    logger.info("  Fetching initial data (this may take a moment)…")

    # Initial fetch before starting server
    refresh_all()

    # Background refresh thread
    t = threading.Thread(target=background_refresh, daemon=True)
    t.start()

    logger.info("  Starting web server...")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)