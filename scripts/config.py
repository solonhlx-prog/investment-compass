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
