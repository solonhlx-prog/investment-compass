# -*- coding: utf-8 -*-
"""用新的 screening_v2 验证10个完美案例"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
from screening import screen_stock, compute_kdj, _inject_precomputed_dual_line
from config import B1_PARAMS

CASES = [
    ("688799.SH", "华纳药厂", "2025-05-12"),
    ("600366.SH", "宁波韵升", "2025-08-06"),
    ("688321.SH", "微芯生物", "2025-06-20"),
    ("600601.SH", "方正科技", "2025-07-23"),
    ("300689.SZ", "澄天伟业", "2025-07-18"),
    ("002074.SZ", "国轩高科", "2025-08-01"),
    ("605378.SH", "野马电池", "2025-07-31"),
    ("600184.SH", "光电股份", "2025-07-10"),
    ("301076.SZ", "新瀚新材", "2025-08-01"),
    ("002940.SZ", "昂利康", "2025-07-11"),
]

DATA_DIR = "D:/stock_data/daily_raw"
WINDOW = 150

print("="*95)
print("投研罗盘 B1 v2.0 — 10个完美案例验证")
print(f"B1_PARAMS: J阈值={B1_PARAMS['j_threshold']}, 蜈蚣上限={B1_PARAMS['centipede_max']}, 最低分={B1_PARAMS['min_total_score']}")
print("="*95)
print()

pass_count = 0
for i, (code, name, date) in enumerate(CASES, 1):
    f = os.path.join(DATA_DIR, f"{code}.parquet")
    df = pd.read_parquet(f)
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["trade_date"] = df["trade_date"].astype(str)
    target = date.replace("-", "")
    mask = df["trade_date"] == target
    if mask.sum() == 0:
        print(f"#{i} {name}: 无数据")
        continue
    idx = mask.idxmax()
    start = max(0, idx - WINDOW + 1)
    sub = df.iloc[start:idx+1]
    klines = [{
        "open": float(r["open"]), "high": float(r["high"]),
        "low": float(r["low"]), "close": float(r["close"]),
        "vol": float(r["vol"]),
        "pct_chg": float(r.get("pct_chg", 0)),
        "large_inflow": float(r.get("large_inflow", 0) or 0),
        "large_outflow": float(r.get("large_outflow", 0) or 0),
    } for _, r in sub.iterrows()]
    if klines:
        klines[-1]["ts_code"] = code
        klines[-1]["trade_date"] = target

    result = screen_stock(code, name, klines, B1_PARAMS)

    if result:
        pass_count += 1
        print(f"#{i} {name:6s} ✅ J={result['j']:6.1f} \u7a81\u7834={result['break_type']}({result['break_vol_ratio']:.1f}x) \u8bc4\u5206={result['score']:.1f}(\u57fa\u7840{result['base_score']}+区分{result['dist_score']}) \u91d1\u53c9={result['cross_days']}\u5929 F1={result['f1_breakthrough']:.0f} F4={result['f4_top_shrink']:.0f} F10={result['f10_small_candle']:.0f} F11={result['f11_sel_shrink']:.0f} F12={result['f12_cross_days_score']:.0f}")
    else:
        k, d, j = compute_kdj(klines)
        print(f"#{i} {name:6s} ❌ J={j:.1f} \u672a\u901a\u8fc7\u786c\u8fc7\u6ee4")

print(f"\n通过: {pass_count}/10")
