"""
第一性原理：从10个完美案例反向工程出能选出全部10个的特征值和门槛

Step 1: 提取10个完美案例在选股日的所有特征值（从Z哥cache中）
Step 2: 找出每个特征的"最小通过值"（即第10名案例的值）
Step 3: 设计评分体系，使10个案例都能通过
Step 4: 全市场排名验证TOP20
"""
import pandas as pd
import numpy as np
import os
import sys

CASES = [
    ("688799.SH", "华纳药厂", "20250512"),
    ("600366.SH", "宁波韵升", "20250806"),
    ("688321.SH", "微芯生物", "20250620"),
    ("600601.SH", "方正科技", "20250723"),
    ("300689.SZ", "澄天伟业", "20250718"),
    ("002074.SZ", "国轩高科", "20250801"),
    ("605378.SH", "野马电池", "20250731"),
    ("600184.SH", "光电股份", "20250710"),
    ("301076.SZ", "新瀚新材", "20250801"),
    ("002940.SZ", "昂利康", "20250711"),
]

CACHE_DIR = "D:/BaiduSyncdisk/Z/B1完美图/cache"
STRATEGIES = ["nadao", "weifeng", "yunsheng", "fangzheng", "saite", "tianshan"]

# ══════════════════════════════════════════════════════════════
# Step 1: 提取10个完美案例的所有特征值
# ══════════════════════════════════════════════════════════════
print("=" * 100)
print("Step 1: 提取10个完美案例在各策略中的特征值")
print("=" * 100)

all_features = []

for code, name, date in CASES:
    best_score = 0
    best_strat = ""
    best_data = None
    
    for strat in STRATEGIES:
        cache_file = os.path.join(CACHE_DIR, strat, f"{code}.parquet")
        if not os.path.exists(cache_file):
            continue
        try:
            df = pd.read_parquet(cache_file)
            df["trade_date"] = df["trade_date"].astype(str)
            row = df[df["trade_date"] == date]
            if row.empty:
                continue
            row = row.iloc[0]
            
            total = row.get("total_score", 0)
            if total > best_score:
                best_score = total
                best_strat = strat
                best_data = row
        except:
            continue
    
    if best_data is not None:
        r = best_data
        features = {
            "股票": name,
            "代码": code,
            "日期": date,
            "策略": best_strat,
            "总分": best_score,
            "F1_放量突破分": r.get("f1_score", 0),
            "F1_放量比值": r.get("f1_volume_ratio", 0),
            "F2_顶部缩量分": r.get("f2_score", 0),
            "F2_缩量比值": r.get("f2_shrink_ratio", 0),
            "F3_金叉天数分": r.get("f3_score", 0),
            "F3_天数": r.get("f3_cross_days", 0),
            "F4_小阴小阳分": r.get("f4_score", 0),
            "F4_偏离值": r.get("f4_max_deviation", 0),
            "F5_选股缩量分": r.get("f5_score", 0),
            "F5_缩量比值": r.get("f5_shrink_ratio", 0),
            "减分": r.get("penalty_score", 0),
            "J值": r.get("j_value", 0),
            "白>黄": r.get("white_above_yellow", False),
            "涨跌幅": r.get("pct_change", 0),
        }
        all_features.append(features)

feat_df = pd.DataFrame(all_features)

print("\n10个完美案例的最佳策略评分：")
print(feat_df[["股票", "策略", "总分", "J值", "F1_放量突破分", "F2_顶部缩量分", 
               "F3_金叉天数分", "F4_小阴小阳分", "F5_选股缩量分", "减分"]].to_string(index=False))

# ══════════════════════════════════════════════════════════════
# Step 2: 分析每个特征的分布和最小通过值
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("Step 2: 各特征值分布分析（找出能让全部10个通过的阈值）")
print("=" * 100)

feature_cols = {
    "F1_放量突破分": ("≥", "越高越好"),
    "F2_顶部缩量分": ("≥", "越高越好"),
    "F3_金叉天数分": ("≥", "越高越好"),
    "F4_小阴小阳分": ("≥", "越高越好"),
    "F5_选股缩量分": ("≥", "越高越好"),
    "J值": ("≤", "越低越好(≤14)"),
    "总分": ("≥", "越高越好"),
}

for col, (direction, desc) in feature_cols.items():
    vals = feat_df[col].values
    print(f"\n  {col} ({desc}):")
    print(f"    范围: {min(vals):.1f} ~ {max(vals):.1f}")
    print(f"    均值: {np.mean(vals):.1f}")
    print(f"    中位数: {np.median(vals):.1f}")
    if direction == "≥":
        threshold = min(vals)
        print(f"    → 全部通过的最小阈值: ≥{threshold:.1f}（最差案例: {feat_df.loc[feat_df[col].idxmin(), '股票']}）")
    else:
        threshold = max(vals)
        print(f"    → 全部通过的最大阈值: ≤{threshold:.1f}（最差案例: {feat_df.loc[feat_df[col].idxmax(), '股票']}）")

# ══════════════════════════════════════════════════════════════
# Step 3: 分析失败案例的具体瓶颈
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("Step 3: 后5个失败案例的瓶颈分析")
print("=" * 100)

for _, row in feat_df.iterrows():
    if row["总分"] < 85:
        print(f"\n  ❌ {row['股票']} ({row['策略']}) 总分={row['总分']}:")
        for col in ["F1_放量突破分", "F2_顶部缩量分", "F3_金叉天数分", "F4_小阴小阳分", "F5_选股缩量分"]:
            if row[col] < 16:
                print(f"    → {col}={row[col]} (<16，瓶颈)")
        if row["减分"] < 0:
            print(f"    → 减分={row['减分']} (触发减分项)")

# ══════════════════════════════════════════════════════════════
# Step 4: 重新设计评分体系
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("Step 4: 重新设计评分体系（确保10个案例都能≥门槛）")
print("=" * 100)

# 原Z哥评分: F1-F5各20分=100分，满分线较严
# 新方案: 放宽F1和F4的评分区间，让"不够完美但可接受"的案例也能得分

def new_score_f1(ratio):
    """放量突破：原≥3x→20分，新≥1.5x→20分"""
    if ratio >= 1.5: return 20
    if ratio >= 1.2: return 16
    if ratio >= 1.0: return 12
    return 8

def new_score_f2(ratio):
    """顶部缩量：原≤0.45→20分，保持"""
    if ratio <= 0.45: return 20
    if ratio <= 0.65: return 16
    if ratio <= 0.85: return 12
    if ratio <= 1.00: return 8
    return 4

def new_score_f3(days):
    """金叉后天数：多窗口兼容（8/13/21/34/55±5）"""
    for center in [8, 13, 21, 34, 55]:
        if abs(days - center) <= 3:
            return 20
    for center in [8, 13, 21, 34, 55]:
        if abs(days - center) <= 6:
            return 16
    if days > 70: return 12
    return 8

def new_score_f4(deviation):
    """小阴小阳：原<2%→20分，放宽到<3%→20分"""
    if deviation < 3: return 20
    if deviation < 4: return 16
    if deviation < 5: return 12
    return 6

def new_score_f5(ratio):
    """选股缩量：原≤0.28→20分，放宽到≤0.35→20分"""
    if ratio <= 0.35: return 20
    if ratio <= 0.45: return 16
    if ratio <= 0.60: return 12
    if ratio <= 0.80: return 8
    return 4

print("\n新评分体系（放宽F1/F4/F5门槛）：")
print("  F1放量突破: ≥1.5x→20分(原≥3x), ≥1.2→16, ≥1.0→12")
print("  F2顶部缩量: ≤0.45→20分(不变)")
print("  F3金叉天数: 8/13/21/34/55±3→20分(多窗口兼容)")
print("  F4小阴小阳: <3%→20分(原<2%), <4%→16, <5%→12")
print("  F5选股缩量: ≤0.35→20分(原≤0.28), ≤0.45→16")

# 用新评分体系重新打分
print("\n新评分体系下的10个完美案例评分：")
print(f"{'股票':<10} {'F1':>4} {'F2':>4} {'F3':>4} {'F4':>4} {'F5':>4} {'减分':>5} {'总分':>5} {'通过':>4}")

new_scores = []
for _, row in feat_df.iterrows():
    f1 = new_score_f1(row["F1_放量比值"])
    f2 = new_score_f2(row["F2_缩量比值"])
    f3 = new_score_f3(row["F3_天数"])
    f4 = new_score_f4(row["F4_偏离值"])
    f5 = new_score_f5(row["F5_缩量比值"])
    penalty = row["减分"]
    total = f1 + f2 + f3 + f4 + f5 + penalty
    passed = "✅" if total >= 80 else "❌"
    print(f"{row['股票']:<10} {f1:>4} {f2:>4} {f3:>4} {f4:>4} {f5:>4} {penalty:>5.0f} {total:>5.0f} {passed:>4}")
    new_scores.append((row["股票"], row["代码"], row["日期"], total))

print(f"\n新体系通过率: {sum(1 for _,_,_,s in new_scores if s >= 80)}/10")

# ══════════════════════════════════════════════════════════════
# Step 5: 全市场排名验证
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("Step 5: 全市场排名验证 — 10个完美案例在选股日的全市场排名")
print("=" * 100)

# 对每个选股日，从所有策略cache中取每只股票的最高分，排名
dates_map = {}
for _, row in feat_df.iterrows():
    dates_map[row["日期"]] = (row["代码"], row["股票"])

for date, (target_code, target_name) in dates_map.items():
    print(f"\n{'─' * 70}")
    print(f"选股日 {date[:4]}-{date[4:6]}-{date[6:]} — 目标: {target_name} ({target_code})")
    print(f"{'─' * 70}")
    
    # 收集该日期所有股票的最高分
    stock_best = {}  # {ts_code: (best_score, best_strat)}
    
    for strat in STRATEGIES:
        cache_dir = os.path.join(CACHE_DIR, strat)
        if not os.path.exists(cache_dir):
            continue
        files = [f for f in os.listdir(cache_dir) if f.endswith(".parquet")]
        for fname in files:
            ts_code = fname.replace(".parquet", "")
            try:
                df = pd.read_parquet(os.path.join(cache_dir, fname))
                df["trade_date"] = df["trade_date"].astype(str)
                row = df[df["trade_date"] == date]
                if row.empty:
                    continue
                row = row.iloc[0]
                total = row.get("total_score", 0)
                j_val = row.get("j_value", 50)
                white_above = row.get("white_above_yellow", False)
                
                # 选股条件：J≤14 + 白>黄
                if j_val > 14 or not white_above:
                    continue
                
                if ts_code not in stock_best or total > stock_best[ts_code][0]:
                    stock_best[ts_code] = (total, strat)
            except:
                continue
    
    if not stock_best:
        print("  无数据")
        continue
    
    # 排序
    ranked = sorted(stock_best.items(), key=lambda x: -x[1][0])
    
    # 找目标股票的排名
    target_rank = None
    for i, (code, (score, strat)) in enumerate(ranked, 1):
        if code == target_code:
            target_rank = i
            break
    
    total_stocks = len(ranked)
    
    # 打印TOP20
    print(f"  通过J≤14+白>黄的股票: {total_stocks}只")
    print(f"  TOP 20:")
    for i, (code, (score, strat)) in enumerate(ranked[:20], 1):
        marker = " ← 🎯" if code == target_code else ""
        print(f"    #{i:2d} {code} 评分={score:.0f} ({strat}){marker}")
    
    if target_rank:
        if target_rank <= 20:
            print(f"\n  ✅ {target_name} 排名 #{target_rank}/{total_stocks} — 在TOP20内！")
        else:
            print(f"\n  ❌ {target_name} 排名 #{target_rank}/{total_stocks} — 不在TOP20")
    else:
        print(f"\n  ❌ {target_name} 未通过J≤14+白>黄门槛")

print("\n" + "=" * 100)
print("总结")
print("=" * 100)
