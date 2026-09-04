"""
core/leverage_math.py
Precise mathematical modeling of crypto futures leverage, liquidation distances,
and target/stop-loss price conversions for XRP/USDT.
"""

from typing import Dict, Tuple

# Binance Futures MMR (Maintenance Margin Ratio) Tiers for XRP/USDT
DEFAULT_MMR = 0.0040  # 0.40% for retail position brackets (< $50,000 notional)


def get_long_liquidation_price(entry_price: float, leverage: float, mmr: float = DEFAULT_MMR) -> float:
    """
    Calculates the exact liquidation price for an isolated long position.
    P_liq = P_entry * (1 - (1 / leverage) + mmr)
    """
    if leverage <= 1.0:
        return 0.0
    return entry_price * (1.0 - (1.0 / leverage) + mmr)


def get_short_liquidation_price(entry_price: float, leverage: float, mmr: float = DEFAULT_MMR) -> float:
    """
    Calculates the exact liquidation price for an isolated short position.
    P_liq = P_entry * (1 + (1 / leverage) - mmr)
    """
    if leverage <= 1.0:
        return entry_price * 2.0
    return entry_price * (1.0 + (1.0 / leverage) - mmr)


def get_leverage_distance_pct(leverage: float, side: str = "long", mmr: float = DEFAULT_MMR) -> float:
    """
    Returns the absolute percentage price distance required to trigger liquidation
    for a given leverage tier.
    """
    if side.lower() == "long":
        # Price must drop by: (1 / leverage) - mmr
        return max(0.001, (1.0 / leverage) - mmr)
    else:
        # Price must rise by: (1 / leverage) - mmr
        return max(0.001, (1.0 / leverage) - mmr)


def get_all_leverage_tiers(anchor_price: float, mmr: float = DEFAULT_MMR) -> Dict[str, Dict[str, float]]:
    """
    Generates the upper (short) and lower (long) liquidation price bands
    for standard retail leverage tiers: 100x, 50x, 25x, 10x.
    """
    tiers = [100.0, 50.0, 25.0, 10.0]
    result = {}
    for lev in tiers:
        long_liq = get_long_liquidation_price(anchor_price, lev, mmr)
        short_liq = get_short_liquidation_price(anchor_price, lev, mmr)
        dist_pct = get_leverage_distance_pct(lev, "long", mmr) * 100.0
        result[f"{int(lev)}x"] = {
            "leverage": lev,
            "distance_pct": round(dist_pct, 3),
            "lower_band_long_liq": round(long_liq, 5),
            "upper_band_short_liq": round(short_liq, 5),
        }
    return result


def calc_tp_sl_prices(
    entry_price: float,
    side: str,
    leverage: float,
    target_roi_pct: float = 25.0,
    sl_roi_pct: float = 25.0,
) -> Tuple[float, float]:
    """
    Converts target ROI % on margin (e.g. 25% profit) and max SL ROI %
    into exact trigger prices given leverage.
    
    ROI % = (Price Delta % ) * Leverage
    Price Delta % = ROI % / Leverage
    """
    target_price_pct = (target_roi_pct / leverage) / 100.0
    sl_price_pct = (sl_roi_pct / leverage) / 100.0

    if side.lower() == "long":
        tp_price = entry_price * (1.0 + target_price_pct)
        sl_price = entry_price * (1.0 - sl_price_pct)
    elif side.lower() == "short":
        tp_price = entry_price * (1.0 - target_price_pct)
        sl_price = entry_price * (1.0 + sl_price_pct)
    else:
        raise ValueError(f"Unknown side: {side}")

    return tp_price, sl_price


def calc_realized_pnl_pct(
    entry_price: float,
    exit_price: float,
    side: str,
    leverage: float,
    maker_fee_pct: float = 0.02,
    taker_fee_pct: float = 0.05,
    is_tp: bool = False,
) -> float:
    """
    Calculates the realized percentage return ON MARGIN after exchange fees.
    Maker fee applied on limit entry; maker fee on limit TP; taker fee on SL/market close.
    """
    if side.lower() == "long":
        price_ret = (exit_price - entry_price) / entry_price
    else:
        price_ret = (entry_price - exit_price) / entry_price

    gross_roi_pct = price_ret * leverage * 100.0

    # Total fees as % of margin = (entry_fee + exit_fee) * leverage * 100.0
    entry_fee = maker_fee_pct  # limit entry
    exit_fee = maker_fee_pct if is_tp else taker_fee_pct
    total_fee_on_margin = (entry_fee + exit_fee) * leverage * 100.0

    net_roi_pct = gross_roi_pct - total_fee_on_margin
    return net_roi_pct
