"""
投研罗盘 共享配置模块
统一管理 .env 加载和环境变量读取，消除 data.py 和 daily.py 的重复逻辑。
"""

import os
from pathlib import Path


def load_env(env_file: Path = None) -> None:
    """
    加载 .env 配置文件到 os.environ。
    优先使用传入路径，其次自动查找项目根目录。

    Args:
        env_file: .env 文件路径，None 时自动查找
    """
    if env_file is None:
        # 自动查找：scripts/ 的父目录 = 项目根目录
        env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        env_file = Path(".env")
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


# 模块导入时自动加载 .env
load_env()

# ── 配置项 ──
DATA_MODE: str = os.environ.get("DATA_MODE", "websearch")
IS_TT: bool = DATA_MODE == "tt"
TUSHARE_TOKEN: str = os.environ.get("TUSHARE_TOKEN", "")

# 本地数据目录
_raw: str = os.environ.get("STOCK_DATA_DIR", "")
STOCK_DATA_DIR: Path = Path(_raw) if _raw else Path.home() / "stock_data"

# 输出目录
OUTPUT_DIR: Path = Path(os.environ.get("REPORT_OUTPUT_DIR", str(Path(__file__).parent.parent / "outputs")))


# ── B1 选股参数（P0 移植：原硬编码阈值全部可配置化）──
# 通过环境变量覆盖，例如 .env 中写 B1_J_THRESHOLD=-10
def _float_env(key: str, default: float) -> float:
    v = os.environ.get(key, "")
    if v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


B1_PARAMS: dict = {
    # ── 硬过滤四关（一票否决）──
    "j_threshold": _float_env("B1_J_THRESHOLD", 14.0),           # J值上限（v2: -8→14，对齐Z哥完美图）
    "centipede_max": _float_env("B1_CENTIPEDE_MAX", 70.0),       # 蜈蚣图 >= 此值 → 淘汰（v2: 60→70，避免B1窄幅震荡误杀）
    "price_min": _float_env("B1_PRICE_MIN", 3.0),                # 最低股价
    "min_history": _float_env("B1_MIN_HISTORY", 30.0),           # 最少历史天数
    "min_total_score": _float_env("B1_MIN_TOTAL_SCORE", 40.0),   # 综合评分最低门槛（v2新增）
    "require_white_above_yellow": True,                          # 双线白>黄（硬过滤关3）

    # ── 保留：MDC 验证参数 ──
    "rsi6_ceiling": _float_env("B1_RSI6_CEILING", 25.0),
    "adx_floor": _float_env("B1_ADX_FLOOR", 40.0),

    # ── 保留：硬过滤参数 ──
    "sandglass_min": _float_env("B1_SANDGLASS_MIN", 30.0),       # v2: -20→30，沙漏不再是硬过滤

    # ── v1遗留（v2已删除或替代）──
    "j_blunt_floor": -3.0,       # 已删除：被F9连续J评分替代
    "green_brick_limit": 4.0,    # 已在MDC中保留
    "vol_ratio_max": 0.85,       # 已删除：被F11选股缩量比替代
    "dev_ma20_require_below": -3.0,  # 已删除：被F6支撑偏离度替代(P1)
    "drop_10d_min": -25.0,       # 已删除：被F5回调深度比替代(P1)
}

