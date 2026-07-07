"""
验证 Z哥 B1完美图 能否在10个完美案例的选股日当天选出这10只股票
通过读取各策略的评分缓存 parquet 来验证
"""
import pandas as pd
import os

CASES = [
    ("688799.SH", "华纳药厂", "20250512", "纳刀式(8天)"),
    ("600366.SH", "宁波韵升", "20250806", "韵升式(55天)"),
    ("688321.SH", "微芯生物", "20250620", "微风式(13天)"),
    ("600601.SH", "方正科技", "20250723", "方正式(24天)"),
    ("300689.SZ", "澄天伟业", "20250718", "?"),
    ("002074.SZ", "国轩高科", "20250801", "?"),
    ("605378.SH", "野马电池", "20250731", "?"),
    ("600184.SH", "光电股份", "20250710", "?"),
    ("301076.SZ", "新瀚新材", "20250801", "?"),
    ("002940.SZ", "昂利康", "20250711", "?"),
]

CACHE_DIR = "D:/BaiduSyncdisk/Z/B1完美图/cache"
STRATEGIES = ["nadao", "weifeng", "yunsheng", "fangzheng", "saite", "tianshan"]

print("=" * 90)
print("Z哥 B1完美图 — 10个完美案例评分验证")
print("=" * 90)

# 选股条件
J_THRESHOLD = 14
SCORE_THRESHOLD = 85  # 选股门槛(回测用95，选股用85)

for i, (code, name, date, expected_strat) in enumerate(CASES, 1):
    print(f"\n{'─' * 70}")
    print(f"案例 #{i}: {name} ({code}) 选股日 {date[:4]}-{date[4:6]}-{date[6:]} 预期策略: {expected_strat}")
    print(f"{'─' * 70}")
    
    found_in = []
    
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
            
            # 获取评分和J值
            total_score = row.get("total_score", row.get("base_score", None))
            base_score = row.get("base_score", None)
            j_value = row.get("j_value", row.get("J", None))
            white_above = row.get("white_above_yellow", None)
            pct_change = row.get("pct_change", row.get("change_pct", None))
            
            # 各特征分
            f1 = row.get("f1_score", row.get("feature1_score", None))
            f2 = row.get("f2_score", row.get("feature4_score", None))
            f3 = row.get("f3_score", row.get("feature3_score", None))
            f4 = row.get("f4_score", row.get("feature8_score", None))
            f5 = row.get("f5_score", row.get("feature9_score", None))
            
            penalty = row.get("penalty_score", 0)
            
            print(f"  [{strat}] 总分={total_score} 基础分={base_score} J={j_value} "
                  f"白>黄={white_above} 涨跌幅={pct_change}")
            if f1 is not None:
                print(f"    F1(放量突破)={f1} F2(顶部缩量)={f2} F3(金叉天数)={f3} "
                      f"F4(小阴小阳)={f4} F5(选股缩量)={f5} 减分={penalty}")
            
            # 检查选股条件
            j_pass = j_value is not None and j_value <= J_THRESHOLD
            score_pass = total_score is not None and total_score >= SCORE_THRESHOLD
            white_pass = white_above is not None and bool(white_above)
            
            all_pass = j_pass and score_pass and white_pass
            
            if all_pass:
                found_in.append((strat, total_score, j_value))
                print(f"    ✅✅✅ 通过选股条件！(J≤{J_THRESHOLD} 评分≥{SCORE_THRESHOLD} 白>黄)")
            else:
                reasons = []
                if not j_pass: reasons.append(f"J={j_value}>{J_THRESHOLD}")
                if not score_pass: reasons.append(f"评分={total_score}<{SCORE_THRESHOLD}")
                if not white_pass: reasons.append(f"白>黄={white_above}")
                print(f"    ❌ 未通过 — {', '.join(reasons)}")
                
        except Exception as e:
            print(f"  [{strat}] 读取错误: {e}")
    
    if found_in:
        best = max(found_in, key=lambda x: x[1])
        print(f"\n  ✅ 在 {len(found_in)} 个策略中通过，最高评分: {best[1]} ({best[0]})")
    else:
        print(f"\n  ❌ 未在任何策略中通过选股条件")

print(f"\n{'=' * 90}")
print("说明: Z哥各策略按斐波那契数列分窗(8/13/21/34/55)，每个案例只在对应策略有有效评分")
print(f"{'=' * 90}")
