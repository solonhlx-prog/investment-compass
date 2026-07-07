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
    """B1 全市场选股（P0 移植：六维筛选 + 双线过滤 + MDC验证 + 蜈蚣图/沙漏硬过滤）"""
    if REPORT.get("strategy") == "防守":
        REPORT["top5"] = []
        return

    try:
        # 延迟导入，避免无 pandas/numpy 环境下模块加载即报错
        from screening import screen_universe
        from config import B1_PARAMS

        # Stock names
        names: Dict[str, str] = {}
        try:
            basic = pd.read_parquet(STOCK_BASIC_PATH)
            for _, r in basic.iterrows():
                names[str(r["ts_code"])] = str(r["name"])
        except Exception:
            pass

        files = list(DATA_DIR.glob("*.parquet"))
        if not files:
            # 无本地数据（websearch 模式或未下载）：优雅降级为框架说明
            REPORT["top5"] = []
            REPORT["errors"].append(
                "选股跳过：本地无日线数据（DATA_MODE=websearch 或未配置 STOCK_DATA_DIR）。"
                "TT 模式下提供本地 Parquet 后自动启用 B1 P0 全管线。"
            )
            return

        candidates = screen_universe(files, names, B1_PARAMS, top_n=10)
        REPORT["top5"] = candidates

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
        "version": "投研罗盘 v1.7.0",
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

    print("Step 3/4: B1全市场选股（四关硬过滤 + 连续型评分 + 区分特征层）...", flush=True)
    step_screening()
    print(f"  候选: {len(REPORT['top5'])} 只", flush=True)
    for i, c in enumerate(REPORT["top5"][:5]):
        base = c.get("base_score", 0)
        dist = c.get("dist_score", 0)
        brk = c.get("break_type", "N/A")
        sand = c.get("sandglass_score", 0)
        print(f"  #{i+1} {c['ts_code']} {c['name']} J={c['j']} "
              f"突破={brk}({c.get('break_vol_ratio','-')}) "
              f"评分={c['score']}(基础{base}+区分{dist}) "
              f"金叉={c.get('cross_days','-')}天 "
              f"沙漏={sand}", flush=True)

    print("Step 4/4: 输出TOP5日报...", flush=True)
    step_report()
