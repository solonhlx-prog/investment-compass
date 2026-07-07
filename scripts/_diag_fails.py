# -*- coding: utf-8 -*-
"""诊断失败的完美案例"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
from screening import (
    screen_stock, compute_kdj, compute_dual_line,
    find_breakthrough_info, find_golden_cross_days,
    detect_centipede_pattern, _hard_filter_no_breakthrough,
    _hard_filter_j_threshold, _hard_filter_white_below_yellow,
    _hard_filter_centipede
)
from config import B1_PARAMS

CASES = [
    ("605378.SH", "野马电池", "2025-07-31"),
    ("301076.SZ", "新瀚新材", "2025-08-01"),
]
DATA_DIR = "D:/stock_data/daily_raw"
WINDOW = 150

for code, name, date in CASES:
    f = os.path.join(DATA_DIR, f"{code}.parquet")
    df = pd.read_parquet(f)
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["trade_date"] = df["trade_date"].astype(str)
    target = date.replace("-", "")
    mask = df["trade_date"] == target
    idx = mask.idxmax()
    start = max(0, idx - WINDOW + 1)
    sub = df.iloc[start:idx+1]
    klines = [{
        "open": float(r["open"]), "high": float(r["high"]),
        "low": float(r["low"]), "close": float(r["close"]),
        "vol": float(r["vol"]),
        "pct_chg": float(r.get("pct_chg", 0)),
    } for _, r in sub.iterrows()]

    k, d, j = compute_kdj(klines)
    _, _, dual = compute_dual_line(klines)
    brk = find_breakthrough_info(klines)
    cent = detect_centipede_pattern(klines, 60)
    
    print(f"\n{name} ({code}) {date}")
    print(f"  J={j:.1f} (阈值≤{B1_PARAMS['j_threshold']}) → {'PASS' if j <= B1_PARAMS['j_threshold'] else 'FAIL'} 关2")
    print(f"  双线={dual} (需白>黄) → {'PASS' if dual == '白>黄' else 'FAIL'} 关3")
    print(f"  突破: has_break={brk['has_break']} type={brk['break_type']} vol_ratio={brk['break_vol_ratio']:.1f}x → {'PASS' if brk['has_break'] else 'FAIL'} 关1")
    print(f"  蜈蚣图: score={cent['score']} is_centipede={cent['is_centipede']} → {'PASS' if not cent['is_centipede'] else 'FAIL'} 关4")
    
    result = screen_stock(code, name, klines, B1_PARAMS)
    if result:
        print(f"  → ✅ 通过！评分={result['score']:.1f}")
    else:
        print(f"  → ❌ 未通过硬过滤")
