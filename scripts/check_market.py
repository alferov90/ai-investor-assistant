#!/usr/bin/env python3
"""Quick market data check: python scripts/check_market.py AAPL"""
import sys

from app.services.stock_service import fetch_market_data


def main() -> None:
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
    info, _ = fetch_market_data(ticker)
    print(f"source={info.get('_source')} price={info.get('regularMarketPrice')} ticker={ticker}")


if __name__ == "__main__":
    main()
