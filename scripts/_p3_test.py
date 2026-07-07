# -*- coding: utf-8 -*-
"""P3: 全市场排名验证 — testing single date first"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
from screening import screen_stock
from config import B1_PARAMS

DATA_DIR = "D:/stock_data/daily_raw"
WINDOW = 150
target_code = "688799.SH"
target_name = "华纳药厂"
target_date = "2025-05-12"

print(f"Scanning: {target_date} for {target_name} ({target_code})")
print(f"Loading stocks...", flush=True)

files = [f for f in os.listdir(DATA_DIR) if f.endswith('.parquet')]
results = {}
n = 0
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
    n += 1
    if n % 500 == 0:
        print(f"  {n}/{len(files)} candidates: {len(results)}", flush=True)

print(f"Done. Total candidates: {len(results)}", flush=True)

ranked = sorted(results.items(), key=lambda x: -x[1])
print(f"\nTop 20:")
for i, (code, score) in enumerate(ranked[:20], 1):
    m = ' <--- TARGET' if code == target_code else ''
    print(f"  #{i:2d} {code} {score:.1f}{m}")

# Find target rank
for i, (code, score) in enumerate(ranked, 1):
    if code == target_code:
        print(f"\n{target_name} rank: #{i}/{len(ranked)}")
        break
