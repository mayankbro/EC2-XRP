"""
engine/metrics.py
Computes comprehensive quantitative performance analytics, risk metrics,
and breakdown statistics for trading strategies.
"""

from typing import Any, Dict, List
import numpy as np
import pandas as pd


def compute_performance_metrics(trades: List[Dict[str, Any]], initial_capital: float = 10000.0) -> Dict[str, Any]:
    """
    Computes all standard institutional risk and return metrics from a list of trade dictionaries.
    Each trade dict must have: 'date', 'pnl_pct', 'side', 'candle_num', 'exit_reason'.
    """
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "net_roi_pct": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown_pct": 0.0,
        }

    df_trades = pd.DataFrame(trades)
    df_trades["pnl_pct"] = df_trades["pnl_pct"].astype(float)

    total_trades = len(df_trades)
    wins = df_trades[df_trades["pnl_pct"] > 0]
    losses = df_trades[df_trades["pnl_pct"] < 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

    total_win_pnl = wins["pnl_pct"].sum()
    total_loss_pnl = abs(losses["pnl_pct"].sum())
    net_roi_pct = df_trades["pnl_pct"].sum()
    profit_factor = (total_win_pnl / total_loss_pnl) if total_loss_pnl > 0 else (99.0 if total_win_pnl > 0 else 0.0)

    avg_win_pct = wins["pnl_pct"].mean() if win_count > 0 else 0.0
    avg_loss_pct = losses["pnl_pct"].mean() if loss_count > 0 else 0.0
    avg_trade_pct = df_trades["pnl_pct"].mean()
    expectancy_pct = (win_rate / 100.0 * avg_win_pct) + ((1.0 - win_rate / 100.0) * avg_loss_pct)

    # Compute Equity Curve and Drawdown
    # Assuming fixed risk/margin allocation per trade, cumulative PnL %:
    df_trades["cum_roi_pct"] = df_trades["pnl_pct"].cumsum()
    # Simulating account equity starting from initial_capital with fixed 10% margin risk per trade:
    margin_fraction = 0.10  # 10% of equity per trade
    equity = [initial_capital]
    for pnl in df_trades["pnl_pct"]:
        change = equity[-1] * margin_fraction * (pnl / 100.0)
        equity.append(max(1.0, equity[-1] + change))
    
    equity_series = pd.Series(equity[1:], index=df_trades.index)
    peak = equity_series.cummax()
    drawdown_pct = (equity_series - peak) / peak * 100.0
    max_drawdown_pct = abs(drawdown_pct.min())

    # Daily Returns for Sharpe / Sortino
    daily_pnl = df_trades.groupby("date")["pnl_pct"].sum()
    mean_daily = daily_pnl.mean()
    std_daily = daily_pnl.std()
    sharpe_ratio = (mean_daily / std_daily * np.sqrt(252)) if (std_daily and std_daily > 0) else 0.0

    negative_daily = daily_pnl[daily_pnl < 0]
    downside_std = negative_daily.std()
    sortino_ratio = (mean_daily / downside_std * np.sqrt(252)) if (downside_std and downside_std > 0) else 0.0

    # Long vs Short
    long_trades = df_trades[df_trades["side"] == "long"]
    short_trades = df_trades[df_trades["side"] == "short"]
    long_wr = (long_trades["pnl_pct"] > 0).mean() * 100.0 if len(long_trades) > 0 else 0.0
    short_wr = (short_trades["pnl_pct"] > 0).mean() * 100.0 if len(short_trades) > 0 else 0.0

    # By Candle Number
    candle_stats = {}
    for c_num in range(1, 7):
        c_trades = df_trades[df_trades["candle_num"] == c_num]
        if len(c_trades) > 0:
            c_wr = (c_trades["pnl_pct"] > 0).mean() * 100.0
            c_net = c_trades["pnl_pct"].sum()
            candle_stats[c_num] = {
                "trades": len(c_trades),
                "win_rate": round(c_wr, 1),
                "net_pnl": round(c_net, 1),
            }

    return {
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "net_roi_pct": round(net_roi_pct, 2),
        "avg_trade_pct": round(avg_trade_pct, 2),
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "expectancy_pct": round(expectancy_pct, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "sortino_ratio": round(sortino_ratio, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "long_trades": len(long_trades),
        "long_win_rate": round(long_wr, 1),
        "short_trades": len(short_trades),
        "short_win_rate": round(short_wr, 1),
        "candle_breakdown": candle_stats,
        "final_equity": round(equity[-1], 2),
    }
