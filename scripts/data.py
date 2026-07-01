"""
投研罗盘数据层 - Tushare API 直连 + 本地数据回退
三级降级链: Tushare API -> 本地 Parquet -> 外部数据接口
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any, Dict

from config import TUSHARE_TOKEN, STOCK_DATA_DIR, DATA_MODE, IS_TT


def _get_pro_api():
    """获取 Tushare pro_api 实例"""
    try:
        import tushare as ts
        if TUSHARE_TOKEN:
            return ts.pro_api(TUSHARE_TOKEN)
    except ImportError:
        pass
    return None


def fetch_daily(ts_code: str, days: int = 60) -> Optional[list]:
    """
    获取个股日线数据
    降级链: Tushare API -> 本地 Parquet -> None
    """
    if TUSHARE_TOKEN:
        pro = _get_pro_api()
        if pro:
            try:
                import pandas as pd
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
                df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    return df.sort_values("trade_date").to_dict("records")
            except Exception:
                pass

    # 回退: 本地 Parquet
    parquet_dir = STOCK_DATA_DIR / "daily_raw"
    if parquet_dir.exists():
        try:
            import pandas as pd
            for f in parquet_dir.glob("*.parquet"):
                df = pd.read_parquet(f)
                if "ts_code" in df.columns:
                    subset = df[df["ts_code"] == ts_code]
                    if not subset.empty:
                        return subset.tail(days).to_dict("records")
        except Exception:
            pass

    return None


def fetch_index_daily(index_code: str, days: int = 60) -> Optional[list]:
    """获取指数日线数据"""
    if TUSHARE_TOKEN:
        pro = _get_pro_api()
        if pro:
            try:
                import pandas as pd
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
                df = pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    return df.sort_values("trade_date").tail(days).to_dict("records")
            except Exception:
                pass
    return None


def get_data_status() -> Dict[str, Any]:
    """返回当前数据可用性状态"""
    tushare_ok = False
    try:
        import tushare
        tushare_ok = bool(TUSHARE_TOKEN)
    except ImportError:
        pass

    return {
        "mode": DATA_MODE,
        "tushare_available": tushare_ok,
        "local_data_available": STOCK_DATA_DIR.exists(),
        "fallback": "外部金融数据接口 / 网络搜索",
        "tt_mode": IS_TT,
    }


def get_stock_name(ts_code: str) -> str:
    """
    获取股票最新名称，优先使用 namechange 表
    解决 stock_basic.name 不随更名自动更新的问题
    """
    # 1. Try Tushare namechange first
    pro = _get_pro_api()
    if pro:
        try:
            nc = pro.namechange(ts_code=ts_code, fields='ts_code,name,start_date')
            if nc is not None and not nc.empty:
                nc = nc.sort_values('start_date', ascending=False)
                return str(nc.iloc[0]['name'])
        except Exception:
            pass

        # 2. Fallback: stock_basic
        try:
            basic = pro.stock_basic(ts_code=ts_code)
            if basic is not None and not basic.empty:
                return str(basic.iloc[0]['name'])
        except Exception:
            pass

    # 3. Local parquet fallback
    try:
        import pandas as pd
        basic = pd.read_parquet(STOCK_DATA_DIR / "stock_basic" / "stock_list.parquet")
        row = basic[basic['ts_code'] == ts_code]
        if not row.empty:
            return str(row.iloc[0]['name'])
    except Exception:
        pass

    return ts_code


# ═══════════════════════════════════════════════
# CLI: python scripts/data.py → 打印数据状态
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    status = get_data_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
