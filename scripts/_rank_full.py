# -*- coding: utf-8 -*-
"""逐日期全市场排名验证 — 完整10个日期"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

CACHE_DIR = 'D:/BaiduSyncdisk/Z/B1完美图/cache'
STRATEGIES = ['nadao', 'weifeng', 'yunsheng', 'saite', 'tianshan']

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

# 原始Z哥评分（对比用）
def orig_total(r):
    return r.get('total_score', 0)

print('Full Market Ranking Verification')
print('=' * 100)
print(f'{"Stock":<12}{"Date":<12}{"NewScore":>9}{"NewRank":>8}{"Total":>7}{"Top20":>6}{"OrigScore":>10}{"OrigRank":>9}{"OrigTop20":>10}')
print('-' * 100)

all_results = []

for target_code, target_name, date in CASES:
    stock_new = {}  # 新评分
    stock_orig = {}  # 原始评分
    
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
                ns = new_total(r)
                os_score = orig_total(r)
                if ts_code not in stock_new or ns > stock_new[ts_code]:
                    stock_new[ts_code] = ns
                if ts_code not in stock_orig or os_score > stock_orig[ts_code]:
                    stock_orig[ts_code] = os_score
            except:
                continue
    
    total_stocks = len(stock_new)
    
    # 新评分排名
    ranked_new = sorted(stock_new.items(), key=lambda x: -x[1])
    new_rank = 0
    new_score = 0
    for i, (code, score) in enumerate(ranked_new, 1):
        if code == target_code:
            new_rank = i
            new_score = score
            break
    
    # 原始评分排名
    ranked_orig = sorted(stock_orig.items(), key=lambda x: -x[1])
    orig_rank = 0
    orig_score = 0
    for i, (code, score) in enumerate(ranked_orig, 1):
        if code == target_code:
            orig_rank = i
            orig_score = score
            break
    
    new_top20 = new_rank <= 20 if new_rank > 0 else False
    orig_top20 = orig_rank <= 20 if orig_rank > 0 else False
    
    # 统计满分数量
    perfect_count = sum(1 for _, s in ranked_new if s >= 100)
    
    all_results.append((target_name, date, new_score, new_rank, total_stocks, new_top20, 
                        orig_score, orig_rank, orig_top20, perfect_count))
    
    n_status = 'YES' if new_top20 else 'NO'
    o_status = 'YES' if orig_top20 else 'NO'
    print(f'{target_name:<12}{date:<12}{new_score:>9.0f}{new_rank:>8}{total_stocks:>7}{n_status:>6}{orig_score:>10.0f}{orig_rank:>9}{o_status:>10}')

print(f'\n{"=" * 100}')
print('SUMMARY')
print(f'{"=" * 100}')

new_top20_count = sum(1 for r in all_results if r[5])
orig_top20_count = sum(1 for r in all_results if r[8])
print(f'\nNew scoring system - TOP20: {new_top20_count}/10')
print(f'Original Z scoring  - TOP20: {orig_top20_count}/10')

print(f'\n{"Stock":<12}{"NewRank":>8}{"Perfect100":>12}{"OrigRank":>9}')
for name, date, ns, nr, total, nt, os_, or_, ot, pc in all_results:
    print(f'{name:<12}{nr:>8}{pc:>12}{or_:>9}')

print(f'\nKey insight: When thresholds are relaxed to pass all 10 cases,')
print(f'too many non-perfect stocks also score 100, drowning out the targets.')
