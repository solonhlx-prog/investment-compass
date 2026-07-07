# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np

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
        if abs(days-c) <= 5: return 20
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
    return (new_f1(r.get('f1_volume_ratio',0)) +
            new_f2(r.get('f2_shrink_ratio',0)) +
            new_f3(r.get('f3_cross_days',999)) +
            new_f4(r.get('f4_max_deviation',0)) +
            new_f5(r.get('f5_shrink_ratio',0)) +
            r.get('penalty_score',0))

print('Step 5: 全市场排名验证（新评分体系）')
print('=' * 90)

results = []
for target_code, target_name, date in CASES:
    stock_scores = {}
    for strat in STRATEGIES:
        cdir = os.path.join(CACHE_DIR, strat)
        if not os.path.exists(cdir):
            continue
        for fname in os.listdir(cdir):
            if not fname.endswith('.parquet'):
                continue
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
            except:
                continue

    if not stock_scores:
        print(f'  {target_name}: 无数据')
        results.append((target_name, 0, 0, False, 0))
        continue

    ranked = sorted(stock_scores.items(), key=lambda x: -x[1])
    total_stocks = len(ranked)

    target_rank = 0
    target_score = 0
    for i, (code, score) in enumerate(ranked, 1):
        if code == target_code:
            target_rank = i
            target_score = score
            break

    in_top20 = target_rank <= 20 and target_rank > 0
    results.append((target_name, target_rank, total_stocks, in_top20, target_score))

    print(f'\n{target_name} ({date[:4]}-{date[4:6]}-{date[6:]})')
    print(f'  通过J<=14+白>黄的股票: {total_stocks}只')
    print(f'  TOP 10:')
    for i, (code, score) in enumerate(ranked[:10], 1):
        m = ' <<< TARGET' if code == target_code else ''
        print(f'    #{i:2d} {code:12s} {score:5.0f}{m}')
    if target_rank > 10:
        print(f'    ...')
        print(f'    #{target_rank:2d} {target_code:12s} {target_score:5.0f} <<< TARGET')

    status = '[OK] TOP20' if in_top20 else '[FAIL] not in TOP20'
    print(f'  -> {target_name} rank #{target_rank}/{total_stocks} {status}')

print(f'\n{"=" * 90}')
print('SUMMARY')
print(f'{"=" * 90}')
top20_count = sum(1 for _, _, _, ok, _ in results if ok)
print(f'\n10个完美案例进入TOP20: {top20_count}/10')
print(f'{"Stock":<12}{"Rank":>6}{"Total":>8}{"Score":>8}{"Top20":>6}')
for name, rank, total, ok, score in results:
    print(f'{name:<12}{rank:>6}{total:>8}{score:>8.0f}{"OK" if ok else "FAIL":>6}')
