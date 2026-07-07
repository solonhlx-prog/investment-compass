# -*- coding: utf-8 -*-
"""逐日期全市场排名验证 — 避免内存问题"""
import sys, os, traceback
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
import pandas as pd

CACHE_DIR = 'D:/BaiduSyncdisk/Z/B1完美图/cache'
STRATEGIES = ['nadao', 'weifeng', 'yunsheng', 'fangzheng', 'saite', 'tianshan']

CASES = [
    ('688799.SH', '华纳药厂', '20250512'),
    ('600366.SH', '宁波韵升', '20250806'),
    ('688321.SH', '微芯生物', '20250620'),
    ('600601.SH', '方正科技', '20250723'),
    ('300689.SZ', '澄天伟业', '20250718'),
    ('002074.SZ', '国轩高科', '20250801'),
    ('605378.SH', '野马电池', '20250731'),
    ('600184.SH', '光电股份', '20250710'),
    ('301076.SZ', '新瀚新材', '20250801'),
    ('002940.SZ', '昂利康', '20250711'),
]

def new_f1(ratio):
    if ratio >= 1.5: return 20
    if ratio >= 1.0: return 16
    return 12

def new_f2(ratio):
    if ratio <= 0.50: return 20
    if ratio <= 0.70: return 16
    if ratio <= 0.90: return 12
    return 8

def new_f3(days):
    if days == 999: return 8
    for c in [8,13,21,34,55]:
        if abs(days - c) <= 5: return 20
    if days > 5: return 12
    return 8

def new_f4(dev):
    if dev < 2: return 20
    if dev < 3: return 18
    if dev < 4: return 16
    if dev < 5: return 12
    return 8

def new_f5(ratio):
    if ratio <= 0.35: return 20
    if ratio <= 0.50: return 16
    if ratio <= 0.70: return 12
    return 8

def new_total(r):
    return (new_f1(r.get('f1_volume_ratio', 0)) +
            new_f2(r.get('f2_shrink_ratio', 0)) +
            new_f3(r.get('f3_cross_days', 999)) +
            new_f4(r.get('f4_max_deviation', 0)) +
            new_f5(r.get('f5_shrink_ratio', 0)) +
            r.get('penalty_score', 0))

# 只处理第一个日期做测试
target_code, target_name, date = CASES[0]
print(f'Testing: {target_name} {date}', flush=True)

stock_scores = {}
errors = 0
for strat in STRATEGIES:
    cdir = os.path.join(CACHE_DIR, strat)
    if not os.path.exists(cdir):
        continue
    files = [f for f in os.listdir(cdir) if f.endswith('.parquet')]
    print(f'  [{strat}] {len(files)} files...', flush=True)
    for fname in files:
        ts_code = fname.replace('.parquet', '')
        try:
            df = pd.read_parquet(os.path.join(cdir, fname))
            df['trade_date'] = df['trade_date'].astype(str)
            r = df[df['trade_date'] == date]
            if r.empty:
                continue
            r = r.iloc[0]
            j_val = r.get('j_value', 50)
            white_above = r.get('white_above_yellow', False)
            if j_val > 14 or not white_above:
                continue
            score = new_total(r)
            if ts_code not in stock_scores or score > stock_scores[ts_code]:
                stock_scores[ts_code] = score
        except Exception as e:
            errors += 1

print(f'  Total stocks passing J<=14+white>yellow: {len(stock_scores)}', flush=True)
print(f'  Errors: {errors}', flush=True)

if stock_scores:
    ranked = sorted(stock_scores.items(), key=lambda x: -x[1])
    for i, (code, score) in enumerate(ranked[:20], 1):
        m = ' <<< TARGET' if code == target_code else ''
        print(f'    #{i:2d} {code:12s} {score:5.0f}{m}', flush=True)
    
    target_rank = 0
    for i, (code, score) in enumerate(ranked, 1):
        if code == target_code:
            target_rank = i
            break
    print(f'\n  {target_name} rank: #{target_rank}/{len(ranked)}', flush=True)
