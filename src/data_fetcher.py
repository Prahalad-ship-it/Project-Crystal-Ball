"""
Data fetching module for Yahoo Finance API interactions.
Handles data retrieval with retry mechanisms, caching, and error handling.
"""
import time
import logging
from typing import Dict, List, Optional, Tuple
from functools import lru_cache
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class DataFetcher:
    """Handles fetching stock data from Yahoo Finance with reliability features."""

    def __init__(self, timeout: int = 30, max_retries: int = 3, backoff_factor: float = 1.0):
        """
        Initialize the DataFetcher.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            backoff_factor: Backoff factor for exponential backoff
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.session = None  # Could be enhanced to use requests.Session

    def _fetch_with_retry(self, ticker: str, period: str, interval: str) -> Optional[pd.DataFrame]:
        """
        Fetch data for a single ticker with retry mechanism.

        Args:
            ticker: Stock ticker symbol
            period: Data period (e.g., '6mo', '1y')
            interval: Data interval (e.g., '1d')

        Returns:
            DataFrame with OHLCV data or None if failed
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"Fetching {ticker} ({period}) - attempt {attempt + 1}")
                df = yf.download(
                    ticker,
                    period=period,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                    timeout=self.timeout
                )

                if df is not None and not df.empty and len(df) >= 10:
                    # Clean column names (handle multi-index from yfinance)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [col[0] for col in df.columns]
                    return df
                else:
                    raise ValueError(f"Insufficient data received for {ticker}")

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Attempt {attempt + 1} failed for {ticker} ({period}): {str(e)}"
                )

                if attempt < self.max_retries:
                    # Exponential backoff
                    sleep_time = self.backoff_factor * (2 ** attempt)
                    logger.info(f"Retrying {ticker} in {sleep_time:.1f} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All attempts failed for {ticker} ({period})")

        return None

    def fetch_ticker_data(self, ticker: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """
        Fetch both 6-month and 1-year data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Tuple of (6mo_data, 1y_data) where each is a DataFrame or None
        """
        logger.info(f"Fetching data for {ticker}")

        # Fetch 6-month data for indicators
        data_6mo = self._fetch_with_retry(ticker, "6mo", "1d")

        # Fetch 1-year data for 52-week high/low
        data_1y = self._fetch_with_retry(ticker, "1y", "1d")

        return data_6mo, data_1y

    def fetch_batch_data(self, tickers: List[str]) -> Dict[str, Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]]:
        """
        Fetch data for multiple tickers sequentially.
        Note: yfinance doesn't have a true batch API, but we can optimize by
        reusing connections and adding small delays between requests.

        Args:
            tickers: List of ticker symbols

        Returns:
            Dictionary mapping ticker to (6mo_data, 1y_data) tuples
        """
        results = {}

        for i, ticker in enumerate(tickers):
            try:
                data_6mo, data_1y = self.fetch_ticker_data(ticker)
                results[ticker] = (data_6mo, data_1y)

                # Small delay to be respectful to the API
                if i < len(tickers) - 1:  # Don't sleep after the last request
                    time.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to fetch data for {ticker}: {str(e)}")
                results[ticker] = (None, None)

        return results


# Global instance for backward compatibility
default_fetcher = DataFetcher()


def fetch_ticker_data(ticker: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Convenience function for backward compatibility.
    Fetches both 6-month and 1-year data for a ticker.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Tuple of (6mo_data, 1y_data) where each is a DataFrame or None
    """
    return default_fetcher.fetch_ticker_data(ticker)


def fetch_batch_data(tickers: List[str]) -> Dict[str, Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]]:
    """
    Convenience function for backward compatibility.
    Fetches data for multiple tickers.

    Args:
        tickers: List of ticker symbols

    Returns:
        Dictionary mapping ticker to (6mo_data, 1y_data) tuples
    """
    return default_fetcher.fetch_batch_data(tickers)