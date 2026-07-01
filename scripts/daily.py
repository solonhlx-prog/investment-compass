"""
投研罗盘 每日工作流 - 一条龙
Step 1: 择时判定 → Step 2: 策略制定 → Step 3: B1选股 → Step 4: 输出TOP5日报
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import warnings
warnings.filterwarnings("ignore")

from config import TUSHARE_TOKEN, DATA_MODE, IS_TT, STOCK_DATA_DIR, OUTPUT_DIR

import numpy as np
import pandas as pd
try:
    import tushare as ts
except ImportError:
    ts = None

# 数据路径
DATA_DIR = STOCK_DATA_DIR / "daily_raw"
STOCK_BASIC_PATH = STOCK_DATA_DIR / "stock_basic" / "stock_list.parquet"
TODAY = datetime.now().strftime("%Y%m%d")
REPORT: Dict[str, Any] = {"date": TODAY, "timing": {}, "strategy": "", "top5": [], "errors": []}


# ═══════════════════════════════════════════════
# Step 1: 择时判定
# ═══════════════════════════════════════════════
def step_timing() -> None:
    """获取指数数据判断市场方向"""
    try:
        token = os.environ.get("TUSHARE_TOKEN", "")
        if ts and token:
            pro = ts.pro_api(token)
            for idx_code, idx_name in [
                ("000001.SH", "上证指数"), ("399001.SZ", "深证成指"),
                ("399006.SZ", "创业板指"),
            ]:
                # 动态起始日：取近 90 个自然日，足够覆盖 BBI(24日) 与 5日趋势计算
                start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
                df = pro.index_daily(ts_code=idx_code, start_date=start_date, end_date=TODAY)
                if df is not None and not df.empty:
                    df = df.sort_values("trade_date")
                    close = df["close"].astype(float)
                    # BBI
                    bbi = (close.rolling(3).mean() + close.rolling(6).mean() +
                           close.rolling(12).mean() + close.rolling(24).mean()) / 4
                    latest_close = float(close.iloc[-1])
                    latest_bbi = float(bbi.iloc[-1])

                    # 5-day trend
                    pct_5d = round((close.iloc[-1] / close.iloc[-6] - 1) * 100, 1) if len(close) >= 6 else None

                    direction = "多头" if latest_close > latest_bbi else "空头"

                    REPORT["timing"][idx_name] = {
                        "close": round(latest_close, 2),
                        "bbi": round(latest_bbi, 2),
                        "pct_5d": pct_5d,
                        "direction": direction,
                    }

            # 市场阶段判定
            directions = [v["direction"] for v in REPORT["timing"].values()]
            long_count = sum(1 for d in directions if d == "多头")

            if long_count >= 2:
                stage, position_pct, strategy = "多头", 80, "主攻"
            elif long_count == 1:
                stage, position_pct, strategy = "震荡分化", 50, "防守反击"
            else:
                stage, position_pct, strategy = "空头", 30, "防守"

            REPORT["strategy"] = strategy
            REPORT["timing"]["_summary"] = {
                "stage": stage, "position_pct": position_pct, "strategy": strategy,
            }
    except Exception as e:
        REPORT["errors"].append(f"择时判定失败: {e}")


# ═══════════════════════════════════════════════
# Step 3: B1 全市场选股
# ═══════════════════════════════════════════════
def step_screening() -> None:
    """六维筛选 B1 候选"""
    if REPORT.get("strategy") == "防守":
        REPORT["top5"] = []
        return

    try:
        # Stock names
        names: Dict[str, str] = {}
        try:
            basic = pd.read_parquet(STOCK_BASIC_PATH)
            for _, r in basic.iterrows():
                names[str(r["ts_code"])] = str(r["name"])
        except Exception:
            pass

        candidates: List[Dict[str, Any]] = []
        files = list(DATA_DIR.glob("*.parquet"))

        for f in files:
            ts_code = f.stem
            # Skip indices
            if ts_code.startswith("000") and ts_code.endswith(".SH"):
                continue
            if ts_code.startswith("399"):
                continue

            try:
                df = pd.read_parquet(f)
                if len(df) < 30:
                    continue
                df = df.sort_values("trade_date").reset_index(drop=True).tail(40)

                close = df["close"].astype(float).values
                low = df["low"].astype(float).values
                high = df["high"].astype(float).values
                vol = df["vol"].astype(float).values

                # ── 股价 > 3元 ──
                if close[-1] <= 3:
                    continue

                # ── KDJ(9,3,3) ──
                low9 = pd.Series(low).rolling(9).min().values
                high9 = pd.Series(high).rolling(9).max().values
                rsv = np.where(high9 - low9 > 0, (close - low9) / (high9 - low9) * 100, 50)

                k = np.zeros(len(close))
                d = np.zeros(len(close))
                k[:8] = 50; d[:8] = 50
                for i in range(8, len(close)):
                    k[i] = 2/3 * k[i-1] + 1/3 * rsv[i]
                    d[i] = 2/3 * d[i-1] + 1/3 * k[i]
                j = 3 * k - 2 * d

                j_latest = j[-1]
                if j_latest > -8:
                    continue

                # ── J 钝化排除 ──
                if max(j[-10:]) < -3:
                    continue

                # ── 量比 < 0.85 ──
                vol_ma5 = np.mean(vol[-6:-1])
                vol_ratio = vol[-1] / vol_ma5 if vol_ma5 > 0 else 1
                if vol_ratio >= 0.85:
                    continue

                # ── 乖离 MA20 < -3% ──
                ma20 = np.mean(close[-20:])
                dev_ma20 = (close[-1] - ma20) / ma20 * 100
                if dev_ma20 > -3:
                    continue

                # ── 10日跌幅 > -25% ──
                if len(close) >= 10:
                    pct_10d = (close[-1] / close[-11] - 1) * 100
                    if pct_10d < -25:
                        continue  # 排除崩盘

                # ── BBI ──
                ma3 = np.mean(close[-3:]); ma6 = np.mean(close[-6:])
                ma12 = np.mean(close[-12:]); ma24 = np.mean(close[-24:])
                bbi = (ma3 + ma6 + ma12 + ma24) / 4
                bbi_dist = (close[-1] - bbi) / bbi * 100

                # ── 双线系统 (白线/黄线) ──
                ema10 = pd.Series(close).ewm(span=10, adjust=False).mean().values
                white = pd.Series(ema10).ewm(span=10, adjust=False).mean().values
                yellow = (
                    pd.Series(close).rolling(14).mean().values +
                    pd.Series(close).rolling(28).mean().values +
                    pd.Series(close).rolling(57).mean().values +
                    pd.Series(close).rolling(114).mean().values
                ) / 4

                white_latest = white[-1]
                yellow_latest = yellow[-1]
                dual_status = "白>黄" if white_latest > yellow_latest else "白<黄"

                # ── Double-line filter: skip 白<黄 ──
                if dual_status == "白<黄":
                    continue

                # ── N-type ──
                n_type = min(low[-5:]) >= min(low[-10:-5])

                # ── Score ──
                score = 0
                if j_latest <= -12: score += 3
                elif j_latest <= -10: score += 2
                elif j_latest <= -8: score += 1
                if vol_ratio < 0.6: score += 2
                elif vol_ratio < 0.75: score += 1
                if n_type: score += 1
                if bbi_dist > -10: score += 1

                candidates.append({
                    "ts_code": ts_code,
                    "name": names.get(ts_code, ""),
                    "close": round(float(close[-1]), 2),
                    "j": round(float(j_latest), 1),
                    "vol_ratio": round(float(vol_ratio), 2),
                    "dev_ma20": round(float(dev_ma20), 1),
                    "bbi": round(float(bbi), 2),
                    "bbi_dist": round(float(bbi_dist), 1),
                    "dual": dual_status,
                    "n_type": n_type,
                    "score": score,
                })
            except Exception:
                continue

        candidates.sort(key=lambda x: (-x["score"], x["j"]))
        REPORT["top5"] = candidates[:10]

    except Exception as e:
        REPORT["errors"].append(f"选股失败: {e}")


# ═══════════════════════════════════════════════
# Step 4: 输出日报
# ═══════════════════════════════════════════════
def step_report() -> None:
    """生成结构化日报 JSON"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"daily_report_{datetime.now().strftime('%Y%m%d')}.json"

    output = {
        "version": "投研罗盘 v1.6.0",
        "date": REPORT["date"],
        "timing": REPORT["timing"].get("_summary", {}),
        "indices": {k: v for k, v in REPORT["timing"].items() if not k.startswith("_")},
        "strategy": REPORT["strategy"],
        "top5": REPORT["top5"][:5],
        "all_candidates": len(REPORT["top5"]),
        "errors": REPORT["errors"],
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[OK] 日报已保存: {report_path}")
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    print(f"投研罗盘 每日工作流 开始 ({TODAY})", flush=True)
    print(f"{'='*50}", flush=True)

    print("Step 1/4: 择时判定...", flush=True)
    step_timing()
    s = REPORT['timing'].get('_summary', {})
    print(f"  市场阶段: {s.get('stage', 'N/A')}", flush=True)
    print(f"  仓位上限: {s.get('position_pct', 'N/A')}%", flush=True)
    print(f"  操作策略: {REPORT['strategy']}", flush=True)

    print("Step 2/4: 策略制定...", flush=True)
    if REPORT["strategy"] == "防守":
        print("  空头市场，跳过选股。等待活跃市值+4%信号。", flush=True)
        step_report()
        sys.exit(0)
    print(f"  {REPORT['strategy']}策略，执行B1选股", flush=True)

    print("Step 3/4: B1全市场选股（六维筛选+双线过滤）...", flush=True)
    step_screening()
    print(f"  候选: {len(REPORT['top5'])} 只", flush=True)
    for i, c in enumerate(REPORT["top5"][:5]):
        print(f"  #{i+1} {c['ts_code']} {c['name']} J={c['j']} 量比={c['vol_ratio']} 双线={c['dual']} 评分={c['score']}", flush=True)

    print("Step 4/4: 输出TOP5日报...", flush=True)
    step_report()
