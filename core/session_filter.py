"""
core/session_filter.py
Handles 4H candle indexing (1 to 6 in UTC 24h cycle), session naming,
and trading calendar filters (e.g. weekdays only).
"""

import pandas as pd

# Mapping of UTC hour of candle open to 1-based candle number
CANDLE_HOUR_MAP = {
    0: 1,   # 00:00 - 04:00 UTC (Asia Open)
    4: 2,   # 04:00 - 08:00 UTC (Asia Late / London Pre)
    8: 3,   # 08:00 - 12:00 UTC (London Session)
    12: 4,  # 12:00 - 16:00 UTC (NY Open / Peak Volume)
    16: 5,  # 16:00 - 20:00 UTC (NY Afternoon)
    20: 6,  # 20:00 - 00:00 UTC (US Close / Asia Pre)
}

SESSION_NAMES = {
    1: "Asia Early (00-04 UTC)",
    2: "Asia Late (04-08 UTC)",
    3: "London Open (08-12 UTC)",
    4: "NY Open / Peak (12-16 UTC)",
    5: "NY PM (16-20 UTC)",
    6: "US Close (20-00 UTC)",
}


def enrich_session_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Enriches dataframe with UTC hour, candle number, day of week, and weekend flags."""
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["open_time"]):
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)

    df["hour"] = df["open_time"].dt.hour
    df["candle_num"] = df["hour"].map(CANDLE_HOUR_MAP).fillna(0).astype(int)
    df["session_name"] = df["candle_num"].map(SESSION_NAMES).fillna("Unknown")
    df["day_of_week"] = df["open_time"].dt.dayofweek  # 0 = Monday, 6 = Sunday
    df["day_name"] = df["open_time"].dt.day_name()
    df["is_weekend"] = df["day_of_week"].isin([5, 6])
    df["date"] = df["open_time"].dt.date
    return df


def filter_weekdays_only(df: pd.DataFrame) -> pd.DataFrame:
    """Filters out Saturday and Sunday candles."""
    if "is_weekend" not in df.columns:
        df = enrich_session_columns(df)
    return df[~df["is_weekend"]].reset_index(drop=True)
