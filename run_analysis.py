"""
run_analysis.py
Main entry point for running the XRP/USDT 4H Leverage, Liquidity, and Volume backtest
and generating the interactive PnL dashboard.
"""

import os
import sys

from data.fetcher import load_dataset
from dashboard.generate_dashboard import run_and_save

def main():
    print("="*80)
    print("  XRP/USDT 4H LEVERAGE, LIQUIDITY & VOLUME QUANTITATIVE SYSTEM")
    print("  Binance Futures • 2.75 Years Backtest (Dec 2023 - Sep 2026)")
    print("="*80)

    run_and_save()
    print("\nBacktest execution completed successfully.")
    print("Dashboard artifacts generated:")
    print("  1. Workspace: file://" + os.path.abspath("dashboard/dashboard.html"))
    print("  2. Artifact:  file:///Users/mayankkumar/.gemini/antigravity/brain/9ccdb430-ab76-4153-a600-c40daf770e8c/xrp_pnl_dashboard.html")

if __name__ == "__main__":
    main()
