"""
Signal computation engine for calculating technical indicators and trading signals.
"""
import numpy as np
import pandas as pd
import pandas_ta as ta
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def calculate_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate technical indicators from OHLCV data.

    Args:
        df: DataFrame with OHLCV data (must have Close, High, Low, Volume columns)

    Returns:
        Dictionary of calculated indicators
    """
    if df is None or df.empty:
        return {}

    try:
        # Ensure we have the required columns
        required_cols = ['Close', 'High', 'Low', 'Volume']
        if not all(col in df.columns for col in required_cols):
            logger.warning("Missing required columns for indicator calculation")
            return {}

        close = df["Close"].squeeze()
        high = df["High"].squeeze()
        low = df["Low"].squeeze()
        vol = df["Volume"].squeeze()

        # Calculate indicators
        rsi = ta.rsi(close, length=14)
        macd_r = ta.macd(close, fast=12, slow=26, signal=9)
        sma20 = ta.sma(close, length=20)
        sma50 = ta.sma(close, length=50)
        bb = ta.bbands(close, length=20, std=2)

        # Handle Bollinger Bands column names
        bb_cols = bb.columns.tolist()
        bb_upper = bb[[c for c in bb_cols if c.startswith("BBU")][0]]
        bb_lower = bb[[c for c in bb_cols if c.startswith("BBL")][0]]

        # Latest values
        price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2]) if len(close) > 1 else price
        chg_pct = (price - prev_price) / prev_price * 100 if prev_price != 0 else 0

        rsi_val = float(rsi.iloc[-1]) if not rsi.empty else 50.0
        macd_hist = float(macd_r.iloc[-1, 2]) if not macd_r.empty else 0.0  # MACDh column
        sma20_val = float(sma20.iloc[-1]) if not sma20.empty else price
        sma50_val = float(sma50.iloc[-1]) if not sma50.empty else price
        bb_u = float(bb_upper.iloc[-1]) if not bb_upper.empty else price
        bb_l = float(bb_lower.iloc[-1]) if not bb_lower.empty else price
        bb_pct = (price - bb_l) / (bb_u - bb_l + 1e-9) if bb_u != bb_l else 0.5

        # 52-week high/low (if we have enough data)
        if len(close) >= 252:  # Approximately 1 year of trading days
            wk52_high = float(close.rolling(252).max().iloc[-1])
            wk52_low = float(close.rolling(252).min().iloc[-1])
        else:
            wk52_high = float(close.max()) if not close.empty else price
            wk52_low = float(close.min()) if not close.empty else price

        # Volume ratio
        avg_vol = float(vol.rolling(10).mean().iloc[-1]) if len(vol) >= 10 else float(vol.mean())
        curr_vol = float(vol.iloc[-1]) if not vol.empty else 0.0
        vol_ratio = curr_vol / (avg_vol + 1) if avg_vol > 0 else 1.0

        # ATR for price targets
        atr = float((high - low).rolling(14).mean().iloc[-1]) if len(high) >= 14 else 0.0

        # Spark data (last 30 closes)
        spark = close.iloc[-30:].tolist() if len(close) >= 30 else close.tolist()

        return {
            "price": price,
            "chg_pct": chg_pct,
            "rsi": rsi_val,
            "macd_hist": macd_hist,
            "sma20": sma20_val,
            "sma50": sma50_val,
            "bb_pct": bb_pct * 100,  # Convert to percentage
            "vol_ratio": vol_ratio,
            "atr": atr,
            "wk52_high": wk52_high,
            "wk52_low": wk52_low,
            "spark": [round(x, 2) for x in spark],
            "volume": curr_vol
        }

    except Exception as e:
        logger.error(f"Error calculating indicators: {str(e)}")
        return {}


def compute_signals_from_data(ticker: str, indicators: Dict[str, Any], config) -> Dict[str, Any]:
    """
    Compute trading signals from pre-calculated indicators.

    Args:
        ticker: Stock ticker symbol
        indicators: Dictionary of pre-calculated indicators
        config: Configuration object

    Returns:
        Dictionary containing signal information
    """
    if not indicators:
        return {
            "ticker": ticker,
            "error": "No indicator data available",
            "signal": "N/A",
            "confidence": 0
        }

    try:
        # Extract values
        price = indicators.get("price", 0)
        rsi_val = indicators.get("rsi", 50)
        macd_hist = indicators.get("macd_hist", 0)
        sma20_val = indicators.get("sma20", price)
        sma50_val = indicators.get("sma50", price)
        vol_ratio = indicators.get("vol_ratio", 1.0)
        atr = indicators.get("atr", 0)
        wk52_high = indicators.get("wk52_high", price)
        wk52_low = indicators.get("wk52_low", price)
        spark = indicators.get("spark", [])
        chg_pct = indicators.get("chg_pct", 0)

        # Signal logic
        above_sma20 = price > sma20_val
        above_sma50 = price > sma50_val

        # Determine signal based on configuration thresholds
        if (rsi_val < config.RSI_STRONG_OVERSOLD and
            above_sma20 and
            macd_hist > 0):
            signal = "STRONG BUY"
            confidence = 90
        elif rsi_val < config.RSI_OVERSOLD and above_sma20:
            signal = "BUY"
            confidence = 70
        elif (rsi_val > config.RSI_STRONG_OVERBOUGHT and
              not above_sma20 and
              macd_hist < 0):
            signal = "STRONG SELL"
            confidence = 88
        elif rsi_val > config.RSI_SELL and not above_sma20:
            signal = "SELL"
            confidence = 65
        elif rsi_val < 50 and above_sma20 and above_sma50:
            signal = "BUY"
            confidence = 60
        else:
            signal = "HOLD"
            confidence = 50

        # Adjust confidence by volume
        if vol_ratio > config.VOLUME_RATIO_THRESHOLD:
            confidence = min(95, confidence + 5)

        # Price targets (ATR-based)
        if "BUY" in signal:
            target = round(price + 2 * atr, 2) if atr > 0 else round(price * 1.02, 2)
            stop_loss = round(price - 1.5 * atr, 2) if atr > 0 else round(price * 0.98, 2)
        elif "SELL" in signal:
            target = round(price - 2 * atr, 2) if atr > 0 else round(price * 0.98, 2)
            stop_loss = round(price + 1.5 * atr, 2) if atr > 0 else round(price * 1.02, 2)
        else:
            target = round(price + atr, 2) if atr > 0 else round(price * 1.01, 2)
            stop_loss = round(price - atr, 2) if atr > 0 else round(price * 0.99, 2)

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "chg_pct": round(chg_pct, 2),
            "signal": signal,
            "confidence": confidence,
            "rsi": round(rsi_val, 1),
            "macd_hist": round(macd_hist, 4),
            "sma20": round(sma20_val, 2),
            "sma50": round(sma50_val, 2),
            "bb_pct": round(indicators.get("bb_pct", 0), 1),
            "vol_ratio": round(vol_ratio, 2),
            "target": target,
            "stop_loss": stop_loss,
            "wk52_high": round(wk52_high, 2),
            "wk52_low": round(wk52_low, 2),
            "spark": spark,
            "updated": None,  # Will be set by caller
            "error": None,
        }

    except Exception as e:
        logger.error(f"Error computing signals for {ticker}: {str(e)}")
        return {
            "ticker": ticker,
            "error": str(e),
            "signal": "N/A",
            "confidence": 0
        }


def compute_signals(ticker: str, df_6mo: pd.DataFrame, df_1y: pd.DataFrame, config) -> Dict[str, Any]:
    """
    Main function to compute signals for a ticker.

    Args:
        ticker: Stock ticker symbol
        df_6mo: 6-month OHLCV data
        df_1y: 1-year OHLCV data (for 52-week high/low if needed)
        config: Configuration object

    Returns:
        Signal dictionary
    """
    try:
        # Calculate indicators from 6-month data
        indicators = calculate_indicators(df_6mo)

        # Override 52-week high/low with 1-year data if available and more reliable
        if df_1y is not None and not df_1y.empty:
            close_1y = df_1y["Close"].squeeze()
            if len(close_1y) > 0:
                indicators["wk52_high"] = float(close_1y.max())
                indicators["wk52_low"] = float(close_1y.min())

        # Compute signals
        signal_data = compute_signals_from_data(ticker, indicators, config)
        signal_data["updated"] = pd.Timestamp.now().strftime("%H:%M:%S")

        return signal_data

    except Exception as e:
        logger.error(f"Error in compute_signals for {ticker}: {str(e)}")
        return {
            "ticker": ticker,
            "error": str(e),
            "signal": "N/A",
            "confidence": 0,
            "updated": pd.Timestamp.now().strftime("%H:%M:%S")
        }


# Legacy function for backward compatibility
def legacy_compute_signals(ticker: str) -> Dict[str, Any]:
    """
    Legacy function that replicates the original compute_signals behavior.
    Kept for backward compatibility during transition.
    """
    import yfinance as yf
    import warnings
    warnings.filterwarnings("ignore")

    try:
        df = yf.download(ticker, period="6mo", interval="1d",
                         auto_adjust=True, progress=False)
        if df.empty or len(df) < 30:
            return {"ticker": ticker, "error": "No data"}

        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        close = df["Close"].squeeze()
        high = df["High"].squeeze()
        low = df["Low"].squeeze()
        vol = df["Volume"].squeeze()

        # Indicators
        rsi = ta.rsi(close, length=14)
        macd_r = ta.macd(close, fast=12, slow=26, signal=9)
        sma20 = ta.sma(close, length=20)
        sma50 = ta.sma(close, length=50)
        bb = ta.bbands(close, length=20, std=2)
        bb_cols = bb.columns.tolist()
        bb_upper = bb[[c for c in bb_cols if c.startswith("BBU")][0]]
        bb_lower = bb[[c for c in bb_cols if c.startswith("BBL")][0]]

        # Latest values
        price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2])
        chg_pct = (price - prev_price) / prev_price * 100

        rsi_val = float(rsi.iloc[-1])
        macd_hist = float(macd_r.iloc[-1, 2])   # MACDh column
        sma20_val = float(sma20.iloc[-1])
        sma50_val = float(sma50.iloc[-1])
        bb_u = float(bb_upper.iloc[-1])
        bb_l = float(bb_lower.iloc[-1])
        bb_pct = (price - bb_l) / (bb_u - bb_l + 1e-9)

        # 52-week high/low
        df_1y = yf.download(ticker, period="1y", interval="1d",
                            auto_adjust=True, progress=False)
        c1y = df_1y["Close"].squeeze() if not df_1y.empty else close
        wk52_high = float(c1y.max())
        wk52_low = float(c1y.min())

        # Volume ratio
        avg_vol = float(vol.rolling(10).mean().iloc[-1])
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
            target = round(price + 2 * atr, 2)
            stop_loss = round(price - 1.5 * atr, 2)
        elif "SELL" in signal:
            target = round(price - 2 * atr, 2)
            stop_loss = round(price + 1.5 * atr, 2)
        else:
            target = round(price + atr, 2)
            stop_loss = round(price - atr, 2)

        # Spark data (last 30 closes normalised)
        spark = close.iloc[-30:].tolist()

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "chg_pct": round(chg_pct, 2),
            "signal": signal,
            "confidence": confidence,
            "rsi": round(rsi_val, 1),
            "macd_hist": round(macd_hist, 4),
            "sma20": round(sma20_val, 2),
            "sma50": round(sma50_val, 2),
            "bb_pct": round(bb_pct * 100, 1),
            "vol_ratio": round(vol_ratio, 2),
            "target": target,
            "stop_loss": stop_loss,
            "wk52_high": round(wk52_high, 2),
            "wk52_low": round(wk52_low, 2),
            "spark": [round(x, 2) for x in spark],
            "updated": None,
            "error": None,
        }

    except Exception as e:
        return {"ticker": ticker, "error": str(e), "signal": "N/A"}