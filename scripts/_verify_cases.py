"""
验证投研罗盘 B1 能否在10个完美案例的选股日当天选出这10只股票
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

import pandas as pd
from datetime import datetime
from screening import screen_stock, compute_kdj
from config import B1_PARAMS

# 10个完美案例
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

def load_klines(ts_code, target_date, window=150):
    """加载目标日期及之前的K线数据"""
    f = os.path.join(DATA_DIR, f"{ts_code}.parquet")
    df = pd.read_parquet(f)
    df = df.sort_values("trade_date").reset_index(drop=True)
    # 转换日期格式
    df["trade_date"] = df["trade_date"].astype(str)
    # 找到目标日期的行
    target = target_date.replace("-", "")
    mask = df["trade_date"] == target
    if mask.sum() == 0:
        return None, f"目标日期 {target_date} 无数据"
    idx = mask.idxmax()
    # 取目标日期及之前 window 行
    start = max(0, idx - window + 1)
    sub = df.iloc[start:idx+1].copy()
    
    # 构造 klines 格式
    klines = []
    for _, r in sub.iterrows():
        klines.append({
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "vol": float(r["vol"]),
            "pct_chg": float(r.get("pct_chg", 0.0)),
            "large_inflow": float(r.get("large_inflow", 0) or 0),
            "large_outflow": float(r.get("large_outflow", 0) or 0),
        })
    return klines, None

def check_conditions(klines, params):
    """逐条件检查，返回每个条件的通过状态"""
    results = {}
    n = len(klines)
    closes = [k["close"] for k in klines]
    
    # 1. 数据长度
    min_hist = int(params.get("min_history", 30))
    results["数据长度"] = f"{n}天 (需≥{min_hist}) {'✅' if n >= min_hist else '❌'}"
    
    # 2. 股价
    price = closes[-1]
    price_min = params.get("price_min", 3.0)
    results["股价"] = f"{price:.2f} (需>{price_min}) {'✅' if price > price_min else '❌'}"
    
    # 3. J值
    k, d, j = compute_kdj(klines)
    j_thresh = params.get("j_threshold", -8)
    results["J值"] = f"{j:.1f} (需≤{j_thresh}) {'✅' if j <= j_thresh else '❌'}"
    
    # 4. J钝化排除
    if n >= 10:
        recent_j = []
        for i in range(2, 12):
            if len(klines) >= i:
                _, _, jj = compute_kdj(klines[:-i+1] if i > 1 else klines)
                recent_j.append(jj)
        j_blunt_floor = params.get("j_blunt_floor", -3)
        min_j = min(recent_j) if recent_j else 0
        blunt_excluded = min_j < j_blunt_floor
        results["J钝化"] = f"近10日min(J)={min_j:.1f} (<{j_blunt_floor}则排除) {'❌排除' if blunt_excluded else '✅'}"
    else:
        results["J钝化"] = "数据不足"
        blunt_excluded = False
    
    # 5. 量比
    vols = [k["vol"] for k in klines]
    if len(vols) >= 6:
        recent_avg = sum(vols[-6:-1]) / 5
        vol_ratio = vols[-1] / recent_avg if recent_avg > 0 else 1.0
    else:
        vol_ratio = 1.0
    vr_max = params.get("vol_ratio_max", 0.85)
    results["量比"] = f"{vol_ratio:.2f} (需<{vr_max}) {'✅' if vol_ratio < vr_max else '❌'}"
    
    # 6. 乖离MA20
    if n >= 20:
        ma20 = sum(closes[-20:]) / 20
        dev = (closes[-1] - ma20) / ma20 * 100
    else:
        dev = 0
    dev_req = params.get("dev_ma20_require_below", -3.0)
    results["乖离MA20"] = f"{dev:.1f}% (需≤{dev_req}%) {'✅' if dev <= dev_req else '❌'}"
    
    # 7. 10日跌幅
    if n >= 11:
        pct_10d = (closes[-1] / closes[-11] - 1) * 100
    else:
        pct_10d = 0
    drop_min = params.get("drop_10d_min", -25.0)
    results["10日跌幅"] = f"{pct_10d:.1f}% (需≥{drop_min}%) {'✅' if pct_10d >= drop_min else '❌'}"
    
    # 8. 双线
    from screening import compute_dual_line
    _, _, dual_status = compute_dual_line(klines)
    require_way = params.get("require_white_above_yellow", True)
    results["双线"] = f"{dual_status} (需白>黄) {'✅' if dual_status == '白>黄' else '❌'}"
    
    # 9. 绿砖
    recent_4 = klines[-4:] if n >= 4 else klines
    yin_count = sum(1 for k in recent_4 if k["close"] < k["open"])
    green_limit = int(params.get("green_brick_limit", 4))
    results["绿砖"] = f"近4日阴线{yin_count}根 (≥{green_limit}排除) {'✅' if yin_count < green_limit else '❌'}"
    
    return results, j, vol_ratio, dev, dual_status

print("=" * 80)
print("投研罗盘 B1 完美案例验证")
print("=" * 80)
print(f"\nB1_PARAMS 配置:")
print(f"  J阈值: {B1_PARAMS['j_threshold']}")
print(f"  量比上限: {B1_PARAMS['vol_ratio_max']}")
print(f"  乖离MA20: {B1_PARAMS['dev_ma20_require_below']}%")
print(f"  10日跌幅下限: {B1_PARAMS['drop_10d_min']}%")
print(f"  股价下限: {B1_PARAMS['price_min']}")
print()

pass_count = 0
fail_details = []

for i, (code, name, date) in enumerate(CASES, 1):
    print(f"\n{'─' * 60}")
    print(f"案例 #{i}: {name} ({code}) 选股日 {date}")
    print(f"{'─' * 60}")
    
    klines, err = load_klines(code, date)
    if err:
        print(f"  ❌ {err}")
        fail_details.append((name, "数据错误", err))
        continue
    
    conds, j_val, vr_val, dev_val, dual_val = check_conditions(klines, B1_PARAMS)
    for k, v in conds.items():
        print(f"  {k}: {v}")
    
    # 完整管线
    result = screen_stock(code, name, klines, B1_PARAMS)
    
    if result:
        print(f"\n  ✅✅✅ screen_stock 通过！评分={result['score']} MDC={result['mdc_confidence']}")
        pass_count += 1
    else:
        # 找出第一个失败的原因
        reasons = []
        if j_val > B1_PARAMS['j_threshold']:
            reasons.append(f"J={j_val:.1f}>{B1_PARAMS['j_threshold']}")
        if vr_val >= B1_PARAMS['vol_ratio_max']:
            reasons.append(f"量比={vr_val:.2f}≥{B1_PARAMS['vol_ratio_max']}")
        if dev_val > B1_PARAMS['dev_ma20_require_below']:
            reasons.append(f"乖离={dev_val:.1f}%>{B1_PARAMS['dev_ma20_require_below']}%")
        if dual_val != "白>黄":
            reasons.append(f"双线={dual_val}")
        if not reasons:
            reasons.append("蜈蚣图/沙漏/MDC/绿砖/J钝化 某项未通过")
        print(f"\n  ❌ screen_stock 未通过 — 首要原因: {', '.join(reasons)}")
        fail_details.append((name, reasons[0] if len(reasons)==1 else reasons))

print(f"\n{'=' * 80}")
print(f"验证结果汇总")
print(f"{'=' * 80}")
print(f"\n投研罗盘 B1 通过: {pass_count}/10")
print(f"投研罗盘 B1 失败: {10-pass_count}/10")
print(f"\n失败详情:")
for name, reason in fail_details:
    print(f"  ❌ {name}: {reason}")
