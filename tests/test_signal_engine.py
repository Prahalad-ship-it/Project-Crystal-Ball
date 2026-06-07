"""
Unit tests for signal engine functionality.
"""
import unittest
import sys
import os
from unittest.mock import Mock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from signal_engine import compute_signals_from_data
from config import Config


class TestSignalEngine(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        self.config = Config()

        # Mock indicators for testing
        self.base_indicators = {
            "price": 100.0,
            "chg_pct": 1.0,
            "rsi": 50.0,
            "macd_hist": 0.0,
            "sma20": 95.0,  # Price above SMA20
            "sma50": 90.0,  # Price above SMA50
            "vol_ratio": 1.0,
            "atr": 2.0,
            "wk52_high": 120.0,
            "wk52_low": 80.0,
            "spark": [95, 96, 97, 98, 99, 100],
            "volume": 1000
        }

    def test_sell_signal_at_rsi_56(self):
        """Test SELL signal triggers at RSI > 55."""
        indicators = self.base_indicators.copy()
        indicators["rsi"] = 56.0  # Just above SELL threshold
        indicators["sma20"] = 105.0  # Price below SMA20

        result = compute_signals_from_data("TEST", indicators, self.config)

        self.assertEqual(result["signal"], "SELL")
        self.assertEqual(result["confidence"], 65)

    def test_sell_signal_at_rsi_55(self):
        """Test SELL signal does NOT trigger at RSI = 55 (should be HOLD or other)."""
        indicators = self.base_indicators.copy()
        indicators["rsi"] = 55.0  # Exactly at SELL threshold
        indicators["sma20"] = 105.0  # Price below SMA20

        result = compute_signals_from_data("TEST", indicators, self.config)

        # At RSI=55, it should not trigger SELL (needs > 55)
        # With RSI=55, price < SMA20, RSI < 50? No (55 >= 50)
        # So it should fall through to HOLD
        self.assertEqual(result["signal"], "HOLD")

    def test_sell_signal_at_rsi_54(self):
        """Test SELL signal does NOT trigger at RSI < 55."""
        indicators = self.base_indicators.copy()
        indicators["rsi"] = 54.0  # Below SELL threshold
        indicators["sma20"] = 105.0  # Price below SMA20

        result = compute_signals_from_data("TEST", indicators, self.config)

        # At RSI=54, price < SMA20, but RSI >= 50, so should be HOLD
        self.assertEqual(result["signal"], "HOLD")

    def test_strong_sell_still_works(self):
        """Test STRONG SELL signal still uses RSI_STRONG_OVERBOUGHT (65)."""
        indicators = self.base_indicators.copy()
        indicators["rsi"] = 66.0  # Above STRONG SELL threshold
        indicators["macd_hist"] = -0.1  # Negative MACD histogram
        indicators["sma20"] = 105.0  # Price below SMA20

        result = compute_signals_from_data("TEST", indicators, self.config)

        self.assertEqual(result["signal"], "STRONG SELL")
        self.assertEqual(result["confidence"], 88)

    def test_buy_signal_logic_unchanged(self):
        """Test BUY signal logic remains unchanged."""
        indicators = self.base_indicators.copy()
        indicators["rsi"] = 40.0  # Below RSI_OVERSOLD (45)
        indicators["sma20"] = 95.0  # Price above SMA20

        result = compute_signals_from_data("TEST", indicators, self.config)

        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(result["confidence"], 70)


if __name__ == '__main__':
    unittest.main()