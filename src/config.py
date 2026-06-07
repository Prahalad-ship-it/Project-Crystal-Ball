"""
Configuration management for the stock signal dashboard.
Handles environment variables and default settings.
"""
import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration class."""

    # Watchlist of stocks to monitor
    WATCHLIST: List[str] = os.getenv(
        "WATCHLIST", "AAPL,TSLA,NVDA,MSFT,AMZN,META,GOOGL,SPY"
    ).split(",")

    # Refresh interval in seconds
    REFRESH_SECONDS: int = int(os.getenv("REFRESH_SECONDS", "60"))

    # Yahoo Finance API settings
    YFINANCE_TIMEOUT: int = int(os.getenv("YFINANCE_TIMEOUT", "30"))
    YFINANCE_RETRIES: int = int(os.getenv("YFINANCE_RETRIES", "3"))
    YFINANCE_BACKOFF_FACTOR: float = float(os.getenv("YFINANCE_BACKOFF_FACTOR", "1.0"))

    # Signal calculation thresholds
    RSI_OVERBOUGHT: int = int(os.getenv("RSI_OVERBOUGHT", "70"))
    RSI_OVERSOLD: int = int(os.getenv("RSI_OVERSOLD", "30"))
    RSI_STRONG_OVERBOUGHT: int = int(os.getenv("RSI_STRONG_OVERBOUGHT", "65"))
    RSI_STRONG_OVERSOLD: int = int(os.getenv("RSI_STRONG_OVERSOLD", "35"))
    RSI_SELL: int = int(os.getenv("RSI_SELL", "55"))

    # Volume ratio threshold for confidence adjustment
    VOLUME_RATIO_THRESHOLD: float = float(os.getenv("VOLUME_RATIO_THRESHOLD", "1.5"))

    # Host and port for Flask app
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "5000"))

    # Debug mode
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def validate(cls) -> None:
        """Validate configuration values."""
        if cls.REFRESH_SECONDS < 10:
            raise ValueError("REFRESH_SECONDS must be at least 10 seconds")
        if cls.YFINANCE_TIMEOUT < 5:
            raise ValueError("YFINANCE_TIMEOUT must be at least 5 seconds")
        if cls.YFINANCE_RETRIES < 0:
            raise ValueError("YFINANCE_RETRIES must be non-negative")