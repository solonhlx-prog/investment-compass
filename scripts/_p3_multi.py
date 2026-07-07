# -*- coding: utf-8 -*-
"""P3: Multi-date full market ranking verification"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
from screening import screen_stock
from config import B1_PARAMS

CASES = [
    ("688799.SH", "华纳药厂", "2025-05-12"),
    ("600366.SH", "宁波韵升", "2025-08-06"),
    ("688321.SH", "微芯生物", "2025-06-20"),
    ("600601.SH", "方正科技", "2025-07-23"),
    ("300689.SZ", "澄天伟业", "2025-07-18"),
    ("002074.SZ", "国轩高科", "2025-08-01"),
    ("600184.SH", "光电股份", "2025-07-10"),
    ("002940.SZ", "昂利康", "2025-07-11"),
]

DATA_DIR = "D:/stock_data/daily_raw"
WINDOW = 150

print("P3: Full Market Ranking Verification (8 cases)")
print("="*80)

for target_code, target_name, target_date in CASES:
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.parquet')]
    results = {}
    for fname in files:
        ts_code = fname.replace('.parquet', '')
        if ts_code.startswith('000') and ts_code.endswith('.SH'): continue
        if ts_code.startswith('399'): continue
        try:
            df = pd.read_parquet(os.path.join(DATA_DIR, fname))
            df = df.sort_values('trade_date').reset_index(drop=True)
            df['trade_date'] = df['trade_date'].astype(str)
            target = target_date.replace('-', '')
            mask = df['trade_date'] == target
            if mask.sum() == 0: continue
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
            result = screen_stock(ts_code, '', klines, B1_PARAMS)
            if result:
                results[ts_code] = result['score']
        except:
            pass
    
    ranked = sorted(results.items(), key=lambda x: -x[1])
    total = len(ranked)
    target_rank = 0
    target_score = 0
    for i, (code, score) in enumerate(ranked, 1):
        if code == target_code:
            target_rank = i
            target_score = score
            break
    
    top20 = target_rank <= 20
    print(f"\n{target_name} ({target_date}): rank=#{target_rank}/{total} score={target_score:.0f} TOP20={'Y' if top20 else 'N'}")
    if target_rank <= 5:
        # Show top 5
        for i, (code, score) in enumerate(ranked[:5], 1):
            m = ' <<<' if code == target_code else ''
            print(f"  #{i} {code} {score:.0f}{m}")

print(f"\n{'='*80}")
print("Done")
