"""
data/fetcher.py
Fetches historical futures klines for XRPUSDT from Binance Futures API.
"""

import datetime
import os
import time
import pandas as pd
import requests

DEFAULT_SYMBOL = "XRPUSDT"
DEFAULT_INTERVAL = "4h"
DEFAULT_PARQUET_PATH = os.path.join(os.path.dirname(__file__), "xrp_4h_futures.parquet")


def fetch_binance_futures_klines(
    symbol: str = DEFAULT_SYMBOL,
    interval: str = DEFAULT_INTERVAL,
    target_candles: int = 6000,
    save_path: str = DEFAULT_PARQUET_PATH,
) -> pd.DataFrame:
    """
    Fetches up to `target_candles` of historical futures data from Binance.
    Paginates backwards from the current timestamp.
    """
    print(f"Fetching {target_candles} klines for {symbol} ({interval})...")
    all_klines = []
    end_time = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    curr_end = end_time

    while len(all_klines) < target_candles:
        url = (
            f"https://fapi.binance.com/fapi/v1/klines?"
            f"symbol={symbol}&interval={interval}&limit=1000&endTime={curr_end}"
        )
        try:
            r = requests.get(url, timeout=10)
            res = r.json()
        except Exception as e:
            print(f"Request error: {e}")
            break

        if not res or not isinstance(res, list) or len(res) == 0:
            break

        all_klines = res + all_klines
        curr_end = res[0][0] - 1

        # Deduplicate
        seen = set()
        unique = []
        for k in all_klines:
            if k[0] not in seen:
                seen.add(k[0])
                unique.append(k)
        all_klines = unique

        time.sleep(0.1)
        if len(res) < 1000:
            break

    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "count", "taker_buy_volume",
        "taker_buy_quote_volume", "ignore"
    ]
    df = pd.DataFrame(all_klines, columns=columns)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    num_cols = [
        "open", "high", "low", "close", "volume",
        "quote_volume", "taker_buy_volume", "taker_buy_quote_volume"
    ]
    for col in num_cols:
        df[col] = df[col].astype(float)

    df = df.sort_values("open_time").reset_index(drop=True)
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        df.to_parquet(save_path)
        print(f"Saved {len(df)} candles to {save_path}")
        print(f"Date range: {df['open_time'].min()} to {df['open_time'].max()}")

    return df


def load_dataset(path: str = DEFAULT_PARQUET_PATH) -> pd.DataFrame:
    """Loads existing parquet file or downloads if not found."""
    all_path = os.path.join(os.path.dirname(__file__), "xrp_4h_futures_all.parquet")
    target = all_path if os.path.exists(all_path) else path
    if os.path.exists(target):
        df = pd.read_parquet(target)
        df = df.sort_values("open_time").reset_index(drop=True)
        return df
    return fetch_binance_futures_klines(save_path=path)


if __name__ == "__main__":
    df = load_dataset()
    print("Dataset ready. Shape:", df.shape)
