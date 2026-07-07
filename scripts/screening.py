"""
投研罗盘 B1 选股引擎 v2.0（P0 重构：连续型评分 + 六特征补齐）

v2.0 升级：
  1. 新增6个P0核心特征：放量突破比(F1)、突破类型(F2)、顶部缩量比(F4)、
     小阴小阳度(F10)、选股缩量比(F11)、金叉后天数(F12)
  2. 全特征改为连续型评分（阈值型→连续型），消除同分僵局
  3. 硬过滤精简为4关：无突破排除/J>14排除/白<黄排除/蜈蚣图排除
  4. 保留区分特征层：沙漏审美(F14)+MDC置信度(F15)+蜈蚣图反向(F16)+麒麟阶段(F17)
  5. J值阈值从-8放宽到14（对齐Z哥完美图体系）

设计原则：
  - 所有函数接受 list[dict] 形态的 klines（字段: open/high/low/close/vol/pct_chg 必填）
  - 纯函数、无外部依赖（仅 numpy）
  - 数据不足时逐层降级，绝不抛异常
  - websearch 模式无本地 parquet → screen_universe 返回空列表，优雅降级
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import os


# ══════════════════════════════════════════════════════════════
# 基础数学工具
# ══════════════════════════════════════════════════════════════
def _ma(values: List[float], period: int) -> float:
    """简单移动平均（取末尾 period 个）"""
    if len(values) < period:
        return sum(values) / len(values) if values else 0.0
    return sum(values[-period:]) / period


def _ema(values: List[float], period: int) -> float:
    """指数移动平均（返回最后一个值）"""
    if len(values) < period:
        return values[-1] if values else 0.0
    k = 2 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def _sma_series(values: List[float], period: int, m: int) -> List[float]:
    """通达信 SMA 递推序列：SMA = X*M/N + SMA_prev*(1-M/N)"""
    if not values:
        return []
    weight = m / period
    sma = values[0]
    result = [sma]
    for v in values[1:]:
        sma = v * weight + sma * (1 - weight)
        result.append(sma)
    return result


def _slope(values: List[float], period: int) -> float:
    """线性回归斜率（通达信 SLOPE）"""
    if len(values) < period:
        period = len(values)
    if period < 2:
        return 0.0
    recent = values[-period:]
    n = period
    sum_x = n * (n - 1) / 2
    sum_xx = (n - 1) * n * (2 * n - 1) / 6
    sum_y = sum(recent)
    sum_xy = sum(recent[i] * i for i in range(n))
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


# ══════════════════════════════════════════════════════════════
# 指标计算（输入 list[dict]，输出 float / tuple）
# ══════════════════════════════════════════════════════════════
def compute_kdj(klines: List[dict], period: int = 9) -> Tuple[float, float, float]:
    """
    KDJ(9,3,3)，返回最后一根的 (K, D, J)。
    数据不足返回 (50, 50, 50)。
    """
    n = len(klines)
    if n < period:
        return 50.0, 50.0, 50.0

    closes = [float(k["close"]) for k in klines]
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]

    k, d = 50.0, 50.0
    for i in range(period - 1, n):
        low_min = min(lows[i - period + 1 : i + 1])
        high_max = max(highs[i - period + 1 : i + 1])
        if high_max == low_min:
            rsv = 50.0
        else:
            rsv = (closes[i] - low_min) / (high_max - low_min) * 100
        k = 2 / 3 * k + 1 / 3 * rsv
        d = 2 / 3 * d + 1 / 3 * k
    j = 3 * k - 2 * d
    return round(k, 2), round(d, 2), round(j, 2)


def compute_bbi(klines: List[dict]) -> float:
    """BBI = (MA3 + MA6 + MA12 + MA24) / 4"""
    closes = [float(k["close"]) for k in klines]
    if len(closes) < 24:
        return 0.0
    return round((_ma(closes, 3) + _ma(closes, 6) + _ma(closes, 12) + _ma(closes, 24)) / 4, 2)


def compute_bollinger(klines: List[dict], period: int = 20, std_dev: float = 2.0
                      ) -> Tuple[float, float, float, float]:
    """
    布林带 (中轨, 上轨, 下轨, 带宽%)。
    数据不足返回 (0,0,0,0)。
    """
    closes = [float(k["close"]) for k in klines]
    if len(closes) < period:
        return 0.0, 0.0, 0.0, 0.0
    recent = closes[-period:]
    mid = sum(recent) / period
    variance = sum((c - mid) ** 2 for c in recent) / period
    std = variance ** 0.5
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    width = (upper - lower) / mid * 100 if mid > 0 else 0.0
    return round(mid, 2), round(upper, 2), round(lower, 2), round(width, 2)


def compute_rsi(klines: List[dict], period: int = 6) -> float:
    """
    RSI(period)，通达信递推 SMA 公式。
    数据不足返回 50（中性）。
    """
    closes = [float(k["close"]) for k in klines]
    if len(closes) < period + 1:
        return 50.0
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    if len(changes) < period:
        return 50.0
    up = [max(c, 0.0) for c in changes]
    down = [abs(min(c, 0.0)) for c in changes]
    avg_up = _sma_series(up, period, 1)[-1]
    avg_down = _sma_series(down, period, 1)[-1]
    if avg_down == 0:
        return 100.0
    return round(avg_up / (avg_up + avg_down) * 100, 2)


def compute_adx_dmi(klines: List[dict], period: int = 14) -> Tuple[float, float, float]:
    """
    Wilder ADX / DMI。
    返回 (ADX, +DI, -DI)。数据不足返回 (0, 0, 0)。
    """
    n = len(klines)
    if n < period + 1:
        return 0.0, 0.0, 0.0

    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    closes = [float(k["close"]) for k in klines]

    pdm, mdm, tr = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        pdm.append(max(up, 0.0) if up > -dn else 0.0)
        mdm.append(max(dn, 0.0) if dn > up else 0.0)
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

    def wilder(seq: List[float]) -> List[float]:
        out = []
        sm = sum(seq[:period]) / period
        out.append(sm)
        for v in seq[period:]:
            sm = (sm * (period - 1) + v) / period
            out.append(sm)
        return out

    atr = wilder(tr)
    pdi_raw = wilder(pdm)
    mdi_raw = wilder(mdm)

    pdi = [pdm_v / atr[i] * 100 if atr[i] > 0 else 0.0 for i, pdm_v in enumerate(pdi_raw)]
    mdi = [mdm_v / atr[i] * 100 if atr[i] > 0 else 0.0 for i, mdm_v in enumerate(mdi_raw)]

    dx = []
    for i in range(len(pdi)):
        denom = pdi[i] + mdi[i]
        dx.append(abs(pdi[i] - mdi[i]) / denom * 100 if denom > 0 else 0.0)

    if len(dx) >= period:
        adx_seq = wilder(dx[-(len(dx) - period + 1):] if len(dx) > period else dx)
        adx_val = adx_seq[-1]
    else:
        adx_val = 0.0
    return round(adx_val, 2), round(pdi[-1], 2), round(mdi[-1], 2)


def compute_dual_line(klines: List[dict]) -> Tuple[float, float, str]:
    """
    Z哥双线系统：
      白线 = EMA(EMA(C,10),10)
      黄线 = (MA14 + MA28 + MA57 + MA114) / 4
    返回 (white, yellow, status)。数据不足 yellow=0。
    """
    closes = [float(k.get("close", 0)) for k in klines]
    if len(closes) < 10:
        return 0.0, 0.0, "未知"
    e1 = []
    k = 2 / (10 + 1)
    e = closes[0]
    for v in closes:
        e = v * k + e * (1 - k)
        e1.append(e)
    white = _ema(e1, 10)

    yellow = 0.0
    if len(closes) >= 114:
        yellow = (_ma(closes, 14) + _ma(closes, 28) + _ma(closes, 57) + _ma(closes, 114)) / 4
    elif len(closes) >= 57:
        yellow = (_ma(closes, 14) + _ma(closes, 28) + _ma(closes, 57)) / 3
    elif len(closes) >= 28:
        yellow = (_ma(closes, 14) + _ma(closes, 28)) / 2
    status = "白>黄" if white > yellow else ("白<黄" if yellow > 0 else "未知")
    return round(white, 2), round(yellow, 2), status


def compute_vol_ratio(klines: List[dict], period: int = 5) -> float:
    """量比 = 当前量 / 前 period 日均量（不含今日）"""
    vols = [float(k["vol"]) for k in klines]
    if len(vols) < period + 1:
        return 1.0
    recent = vols[-period - 1:-1]
    avg = sum(recent) / len(recent)
    if avg == 0:
        return 1.0
    return round(vols[-1] / avg, 2)


# ══════════════════════════════════════════════════════════════
# 麒麟会四阶段识别（移植自 kirin_detector.py，MDC 背景层）
# ══════════════════════════════════════════════════════════════
def detect_kirin_stage(klines: List[dict]) -> Dict[str, Any]:
    """
    识别庄家四阶段：吸筹 → 拉升 → 派发 → 回落。
    返回 {'stage', 'confidence', 'sub_type', 'operation', 'scores'}。
    数据不足 (<60) 返回 stage='未知'。
    """
    result = {
        "stage": "未知", "confidence": 0.0, "sub_type": "未知",
        "operation": "观望", "scores": {},
    }
    if len(klines) < 60:
        return result

    closes = [float(k["close"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    highs = [float(k["high"]) for k in klines]
    vols = [float(k["vol"]) for k in klines]
    pcts = [float(k.get("pct_chg", 0.0)) for k in klines]

    period = min(120, len(klines))
    seg = klines[-period:]
    low_p = min(lows[-period:])
    high_p = max(highs[-period:])
    cur = closes[-1]
    if high_p > low_p:
        from_low = (cur - low_p) / (high_p - low_p) * 100
        from_high = (high_p - cur) / (high_p - low_p) * 100
    else:
        from_low = from_high = 50.0

    red_vol = sum(float(k["vol"]) for k in seg if float(k["close"]) > float(k["open"]))
    green_vol = sum(float(k["vol"]) for k in seg if float(k["close"]) < float(k["open"]))
    red_green = red_vol / green_vol if green_vol > 0 else 3.0

    n_shape = False
    local_lows = []
    for i in range(5, len(klines) - 5):
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            local_lows.append(lows[i])
    if len(local_lows) >= 3:
        rl = local_lows[-3:]
        if rl[0] < rl[1] * 1.02 and rl[1] < rl[2] * 1.02:
            n_shape = True

    seg10 = klines[-10:]
    up_vols = [float(k["vol"]) for k in seg10 if float(k["close"]) > float(k["open"])]
    dn_vols = [float(k["vol"]) for k in seg10 if float(k["close"]) < float(k["open"])]
    breathing = bool(up_vols and dn_vols and
                     sum(up_vols) / len(up_vols) > sum(dn_vols) / len(dn_vols) * 1.2)

    _, _, white_above = _dual_status(klines)

    pull_speed = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else 0.0

    avg_vol_60 = _ma(vols, 60)
    recent_avg_vol = _ma(vols[-10:], 10)
    is_high_vol = recent_avg_vol > avg_vol_60 * 1.3 if avg_vol_60 > 0 else False
    is_low_vol = recent_avg_vol < avg_vol_60 * 0.8 if avg_vol_60 > 0 else False

    limit_up = sum(1 for p in pcts[-20:] if p >= 9.9)

    xishou = 0
    if from_low < 30: xishou += 30
    elif from_low < 50: xishou += 15
    if is_high_vol: xishou += 20
    if n_shape: xishou += 20
    if red_green > 1.3: xishou += 20
    elif red_green > 1.0: xishou += 10
    if limit_up == 0: xishou += 10

    lasheng = 0
    if from_low > 30: lasheng += 20
    elif from_low > 20: lasheng += 10
    if pull_speed > 30: lasheng += 25
    elif pull_speed > 20: lasheng += 15
    if limit_up >= 2: lasheng += 20
    elif limit_up >= 1: lasheng += 10
    if is_high_vol: lasheng += 15
    if white_above: lasheng += 10
    if breathing: lasheng += 10

    paifa = 0
    if from_high < 15: paifa += 30
    elif from_high < 30: paifa += 15
    if is_high_vol and from_low > 60: paifa += 20
    if red_green < 0.7: paifa += 20
    elif red_green < 1.0: paifa += 10

    luoluo = 0
    if from_high > 20: luoluo += 30
    elif from_high > 10: luoluo += 15
    if is_low_vol: luoluo += 25
    recent_red = sum(1 for k in klines[-10:] if float(k["close"]) > float(k["open"]))
    if recent_red < 3: luoluo += 20
    if not white_above: luoluo += 15
    if limit_up == 0: luoluo += 10

    scores = {"xishou": xishou, "lasheng": lasheng, "paifa": paifa, "luoluo": luoluo}
    result["scores"] = scores

    max_score = max(scores.values())
    if max_score < 30:
        result["confidence"] = round(max_score / 100, 2)
        return result

    stage_map = {
        "xishou": ("吸筹", "关注，等B1"),
        "lasheng": ("拉升", "不追，等回调B1"),
        "paifa": ("派发", "准备走人"),
        "luoluo": ("回落", "不抄底"),
    }
    max_stage = max(scores, key=lambda k: scores[k])
    result["stage"] = stage_map[max_stage][0]
    result["confidence"] = round(min(max_score / 100, 1.0), 2)
    result["operation"] = stage_map[max_stage][1]
    return result


def _dual_status(klines: List[dict]) -> Tuple[float, float, bool]:
    """返回 (white, yellow, white_above_yellow)"""
    w, y, _ = compute_dual_line(klines)
    return w, y, (w > y if y > 0 else False)


# ══════════════════════════════════════════════════════════════
# P0 新增：突破检测、金叉检测、上涨期定位（F1/F2/F4/F11/F12 共享）
# ══════════════════════════════════════════════════════════════

def find_breakthrough_info(klines: List[dict], lookback: int = 100
                           ) -> Dict[str, Any]:
    """
    找到最近的黄线/白线突破点，返回突破信息。
    F1(放量突破比) 和 F2(突破类型) 共享。
    
    返回:
      {'has_break': bool, 'break_idx': int, 'break_type': '黄线'|'白线'|'未知',
       'break_vol_ratio': float, 'break_date': str or None}
    数据不足返回 has_break=False。
    """
    result = {"has_break": False, "break_idx": -1, "break_type": "未知",
              "break_vol_ratio": 0.0, "break_date": None}
    n = len(klines)
    if n < 30:
        return result
    
    window = klines[-min(n, lookback):]
    wlen = len(window)
    closes = [float(k["close"]) for k in window]
    vols = [float(k["vol"]) for k in window]
    
    # 计算双线
    w_val, y_val, _ = compute_dual_line(klines)
    if y_val <= 0:
        return result
    
    # 逐日检测突破：收盘从低于黄线变为高于黄线
    # 取最近一次有效突破
    breakthroughs = []
    for i in range(1, wlen):
        # 当日收>黄线 且 前日收<=黄线(放宽:前日收接近黄线也可以)
        close_prev = closes[i-1]
        close_curr = closes[i]
        # 黄线突破检测(简化:用固定值做近似)
        if close_prev <= y_val * 1.02 and close_curr > y_val:
            tmp_k = klines[-min(n, lookback) + i:]
            wv, yv, _ = compute_dual_line(tmp_k)
            if yv > 0 and close_prev <= yv * 1.02 and close_curr > yv:
                breakthroughs.append((i, "黄线"))
    
    if not breakthroughs:
        # 尝试白线突破
        for i in range(1, wlen):
            close_prev = closes[i-1]
            close_curr = closes[i]
            if close_prev <= w_val * 1.02 and close_curr > w_val:
                breakthroughs.append((i, "白线"))
    
    if not breakthroughs:
        return result
    
    # 取最近一次突破
    brk_idx, brk_type = breakthroughs[-1]
    
    # 计算放量突破比：突破日及后2日最大量 / 突破前日量
    brk_day_vol = vols[brk_idx]
    if brk_idx > 0:
        pre_brk_vol = vols[brk_idx - 1]
    else:
        pre_brk_vol = brk_day_vol
    
    # 突破日到后2日内的最大量
    end = min(wlen, brk_idx + 3)
    peak_vol = max(vols[brk_idx:end])
    
    vol_ratio = peak_vol / pre_brk_vol if pre_brk_vol > 0 else 0.0
    
    result["has_break"] = True
    result["break_idx"] = brk_idx
    result["break_type"] = brk_type
    result["break_vol_ratio"] = round(vol_ratio, 2)
    return result


def find_up_phase_info(klines: List[dict], lookback: int = 120
                       ) -> Dict[str, Any]:
    """
    定位上涨期信息：突破点→最高点→最大阳量。
    F4(顶部缩量)、F5(回调深度)、F11(选股缩量) 共享。
    
    返回:
      {'top_idx': int, 'top_price': float, 'top_vol': float, 'max_yang_vol': float,
       'up_start_idx': int, 'accumulated_gain_pct': float}
    数据不足返回 top_idx=-1。
    """
    result = {"top_idx": -1, "top_price": 0, "top_vol": 0,
              "max_yang_vol": 0, "up_start_idx": -1, "accumulated_gain_pct": 0}
    
    brk_info = find_breakthrough_info(klines, lookback)
    if not brk_info["has_break"]:
        return result
    
    window = klines[-min(len(klines), lookback):]
    wlen = len(window)
    closes = [float(k["close"]) for k in window]
    vols = [float(k["vol"]) for k in window]
    
    brk_local_idx = brk_info["break_idx"]
    if brk_local_idx >= wlen - 2:
        return result
    
    # 突破后到末尾找最高点
    post_brk_closes = closes[brk_local_idx:]
    if len(post_brk_closes) == 0:
        return result
    top_local_idx = brk_local_idx + post_brk_closes.index(max(post_brk_closes))
    
    # 上涨阶段：突破点到最高点
    up_stage = window[brk_local_idx:top_local_idx + 1]
    if len(up_stage) == 0:
        return result
    
    yang_days = [k for k in up_stage if float(k["close"]) > float(k["open"])]
    if yang_days:
        max_yang_vol = max(float(k["vol"]) for k in yang_days)
    else:
        max_yang_vol = max(float(k["vol"]) for k in up_stage)
    
    brk_price = closes[brk_local_idx]
    top_price = closes[top_local_idx]
    gain_pct = (top_price - brk_price) / brk_price * 100 if brk_price > 0 else 0
    
    result["top_idx"] = top_local_idx
    result["top_price"] = round(top_price, 2)
    result["top_vol"] = float(window[top_local_idx]["vol"]) if top_local_idx < wlen else 0
    result["max_yang_vol"] = round(max_yang_vol, 2)
    result["up_start_idx"] = brk_local_idx
    result["accumulated_gain_pct"] = round(gain_pct, 2)
    return result


def find_golden_cross_days(klines: List[dict], lookback: int = 120) -> int:
    """
    找到最近一次白线金叉黄线的天数。
    F12(金叉后天数) 使用。
    未找到金叉返回 999。
    """
    n = len(klines)
    if n < 20:
        return 999
    window = klines[-min(n, lookback):]
    closes = [float(k["close"]) for k in window]
    wlen = len(window)
    
    # 逐日检查金叉
    last_cross_pos = -1
    for i in range(10, wlen):
        tmp = window[:i+1]
        w, y, status = compute_dual_line(tmp)
        if status == "白>黄" and y > 0:
            # 检查前一天是否白<黄
            if i > 0:
                tmp_prev = window[:i]
                wp, yp, sp = compute_dual_line(tmp_prev)
                if sp == "白<黄" or (yp > 0 and wp <= yp):
                    last_cross_pos = i
    if last_cross_pos < 0:
        return 999
    return wlen - 1 - last_cross_pos


# ══════════════════════════════════════════════════════════════
# P0 新增：6个连续型评分函数
# ══════════════════════════════════════════════════════════════

def score_f1_breakthrough(vol_ratio: float) -> float:
    """
    F1 放量突破比 (0-25分，连续型)
    阈值放宽：≥1.5x → 满分25，≥1.0x → 20，每0.1x = 3分
    """
    if vol_ratio >= 1.5:
        return 25.0
    if vol_ratio >= 1.0:
        return round(20.0 + (vol_ratio - 1.0) * 10, 1)
    if vol_ratio > 0:
        return round(vol_ratio * 15, 1)
    return 10.0  # 数据不足保底


def score_f2_break_type(break_type: str) -> float:
    """F2 突破类型 (0-10分)"""
    return {"黄线": 10.0, "白线": 6.0}.get(break_type, 0.0)


def score_f4_top_shrink(klines: List[dict], up_info: Dict[str, Any]) -> float:
    """
    F4 顶部缩量比 (0-15分，连续型)
    顶部3日均量 / 上涨期最大阳量，越缩越高分
    """
    if up_info["top_idx"] < 0 or up_info["max_yang_vol"] <= 0:
        return 8.0  # 数据不足保底
    
    n = len(klines)
    window = klines[-min(n, 120):]
    wlen = len(window)
    top_idx = up_info["top_idx"]
    
    # 顶部3日均量
    end = min(wlen, top_idx + 3)
    top_vols = [float(k["vol"]) for k in window[top_idx:end]]
    top_avg_vol = sum(top_vols) / len(top_vols) if top_vols else 0
    
    if top_avg_vol <= 0:
        return 8.0
    
    ratio = top_avg_vol / up_info["max_yang_vol"]
    # 线性反转：ratio=0→15分，ratio=1.0→0分
    return round(max(0.0, min(15.0, 15.0 * (1 - ratio))), 1)


def score_f10_small_candle(klines: List[dict]) -> float:
    """
    F10 小阴小阳度 (0-15分，连续型)
    选股日涨跌幅绝对值越小越高分
    """
    if len(klines) < 2:
        return 8.0
    close = float(klines[-1]["close"])
    prev_close = float(klines[-2]["close"])
    if prev_close <= 0:
        return 8.0
    
    deviation = abs((close - prev_close) / prev_close * 100)
    # 0% → 15分，5% → 0分
    return round(max(0.0, min(15.0, 15.0 * (1 - deviation / 5.0))), 1)


def score_f11_selection_shrink(klines: List[dict], up_info: Dict[str, Any]) -> float:
    """
    F11 选股缩量比 (0-15分，连续型)
    选股日量 / 上涨期最大阳量，越缩越高分
    """
    if up_info["max_yang_vol"] <= 0:
        return 8.0  # 数据不足保底
    
    current_vol = float(klines[-1]["vol"])
    if current_vol <= 0:
        return 8.0
    
    ratio = current_vol / up_info["max_yang_vol"]
    # 0 → 15分，0.8 → 0分
    return round(max(0.0, min(15.0, 15.0 * (1 - ratio / 0.8))), 1)


def score_f12_golden_cross(days_since_cross: int) -> float:
    """
    F12 金叉后天数评分 (0-15分，多窗口连续型)
    斐波那契窗口：8/13/21/34/55 (±3满分, ±7半满分, ±15基础分)
    """
    if days_since_cross == 999:
        return 5.0  # 无金叉保底
    
    FIB_WINDOWS = [8, 13, 21, 34, 55]
    best_score = 5.0
    for w in FIB_WINDOWS:
        dist = abs(days_since_cross - w)
        if dist <= 3:
            score = 15.0
        elif dist <= 7:
            score = 15.0 - (dist - 3) * 1.0
        elif dist <= 15:
            score = 11.0 - (dist - 7) * 0.5
        else:
            score = max(3.0, 7.0 - (dist - 15) * 0.2)
        best_score = max(best_score, score)
    return round(min(15.0, best_score), 1)


def score_f9_j_value(j_val: float) -> float:
    """
    F9 J值连续评分 (0-15分)
    J=-20→15分, J=0→11分, J=14→5分, J=50→0分
    """
    if j_val <= -20:
        return 15.0
    if j_val >= 50:
        return 0.0
    # 线性：在[-20, 50]区间线性下降
    return round(max(0.0, min(15.0, 15.0 * (1 - (j_val + 20) / 70))), 1)


# ── P1: 路径质量特征评分 (F3/F5/F6/F7/F8) ──

def score_f3_accumulated_gain(gain_pct: float) -> float:
    """
    F3 累计涨幅评分 (0-10分，连续型)
    15%-50%区间最优=10分，太小(<5%)=3分，太大(>100%)=3分（炒作嫌疑）
    """
    if gain_pct <= 0:
        return 2.0
    if 15 <= gain_pct <= 50:
        return 10.0
    if gain_pct < 5:
        return 3.0
    if gain_pct > 100:
        return max(3.0, 10.0 - (gain_pct - 100) * 0.05)
    # 在 [5,15) 或 (50,100] 区间线性
    if gain_pct < 15:
        return round(3.0 + (gain_pct - 5) * 0.7, 1)
    return round(10.0 - (gain_pct - 50) * 0.14, 1)


def score_f5_retrace_depth(klines: List[dict], up_info: Dict[str, Any]) -> float:
    """
    F5 回调深度比评分 (0-10分，连续型)
    (最高价-选股日收盘价) / (最高价-突破价)，最佳回调约40%涨幅
    """
    if up_info["top_idx"] < 0:
        return 5.0  # 数据不足保底
    
    n = len(klines)
    window = klines[-min(n, 120):]
    closes_in_w = [float(k["close"]) for k in window]
    
    top_price = up_info["top_price"]
    current_price = float(klines[-1]["close"])
    
    if top_price <= 0:
        return 5.0
    
    # 计算突破价
    brk_idx = up_info["up_start_idx"]
    if brk_idx < 0 or brk_idx >= len(closes_in_w):
        return 5.0
    brk_price = closes_in_w[brk_idx]
    
    total_gain = top_price - brk_price
    if total_gain <= 0:
        return 5.0
    
    retrace = (top_price - current_price) / total_gain
    # 最佳回调约0.4(total_gain的40%)，偏离越远分越低
    optimal = 0.4
    deviation = abs(retrace - optimal)
    # 0偏差→10分, 1.0偏差→0分
    return round(max(0.0, min(10.0, 10.0 * (1 - deviation / 1.0))), 1)


def score_f6_support_deviation(klines: List[dict]) -> float:
    """
    F6 支撑偏离度评分 (0-10分，连续型)
    选股日收盘价相对黄线偏离%，越贴近黄线分越高
    """
    _, y_val, _ = compute_dual_line(klines)
    if y_val <= 0:
        return 5.0  # 数据不足保底
    
    close = float(klines[-1]["close"])
    deviation_pct = (close - y_val) / y_val * 100
    
    # 0%偏离→10分, ±10%偏离→0分
    return round(max(0.0, min(10.0, 10.0 * (1 - abs(deviation_pct) / 10))), 1)


def score_f7_volume_slope(klines: List[dict], up_info: Dict[str, Any]) -> float:
    """
    F7 缩量趋势斜率评分 (0-10分，连续型)
    从顶部到选股日，日成交量的线性回归斜率，越负（缩量越快）分越高
    """
    if up_info["top_idx"] < 0:
        return 5.0
    
    n = len(klines)
    window = klines[-min(n, 120):]
    wlen = len(window)
    top_idx = up_info["top_idx"]
    
    if top_idx >= wlen - 3:
        return 5.0
    
    # 顶部到选股日的成交量序列
    post_top_vols = [float(k["vol"]) for k in window[top_idx:]]
    if len(post_top_vols) < 5:
        return 5.0
    
    # 线性回归：量随时间的斜率
    x_vals = list(range(len(post_top_vols)))
    n_pts = len(x_vals)
    if max(post_top_vols) > 0:
        y_norm = [v / max(post_top_vols) for v in post_top_vols]
    else:
        y_norm = [0.0] * n_pts
    
    sum_x = sum(x_vals)
    sum_y = sum(y_norm)
    sum_xy = sum(x_vals[i] * y_norm[i] for i in range(n_pts))
    sum_xx = sum(x * x for x in x_vals)
    denom = n_pts * sum_xx - sum_x * sum_x
    if denom == 0:
        return 5.0
    
    slope = (n_pts * sum_xy - sum_x * sum_y) / denom
    # slope越负分越高: -0.04→10分, 0→3分, +0.04→0分
    return round(max(0.0, min(10.0, 3.0 + abs(min(0, slope)) * 175)), 1)


def score_f8_yang_yin_ratio(klines: List[dict], up_info: Dict[str, Any]) -> float:
    """
    F8 堆量比评分 (0-10分，连续型)
    上涨阶段累计阳量 / 累计阴量，越大说明筹码越集中
    """
    if up_info["up_start_idx"] < 0:
        return 5.0
    
    n = len(klines)
    window = klines[-min(n, 120):]
    wlen = len(window)
    start_idx = up_info["up_start_idx"]
    top_idx = up_info["top_idx"]
    
    if start_idx < 0 or top_idx < start_idx or start_idx >= wlen:
        return 5.0
    
    up_stage = window[start_idx:min(top_idx + 1, wlen)]
    if len(up_stage) < 2:
        return 5.0
    
    yang_vols = [float(k["vol"]) for k in up_stage if float(k["close"]) > float(k["open"])]
    yin_vols = [float(k["vol"]) for k in up_stage if float(k["close"]) < float(k["open"])]
    
    yang_sum = sum(yang_vols) if yang_vols else 0
    yin_sum = sum(yin_vols) if yin_vols else 0
    
    if yin_sum <= 0:
        ratio = 3.0  # 纯阳量，给满分
    else:
        ratio = yang_sum / yin_sum
    
    # ≥2.5→10分, ≥1.5→8分, ≥1.0→5分, <1.0→3分
    if ratio >= 2.5:
        return 10.0
    if ratio >= 1.5:
        return round(8.0 + (ratio - 1.5) * 2.0, 1)
    if ratio >= 1.0:
        return round(5.0 + (ratio - 1.0) * 6.0, 1)
    return max(2.0, round(ratio * 3.0, 1))


# ── P2: J值清洗深度 ──

def score_f13_j_clean(klines: List[dict], cross_days: int, j_val: float) -> float:
    """
    F13 J值清洗深度评分 (0-10分，连续型)
    金叉后J值最大值 - 选股日J值，差值越大说明清洗越充分
    """
    if cross_days == 999 or cross_days <= 0:
        return 5.0  # 无金叉保底
    
    n = len(klines)
    if n < cross_days + 2:
        return 5.0
    
    # 金叉后到选股日的J值区间
    start_pos = max(0, n - cross_days - 1)
    recent_klines = klines[start_pos:]
    
    max_j = -1000
    for i in range(len(recent_klines)):
        if i > 0:
            k, d, jj = compute_kdj(recent_klines[:i+1])
        else:
            k, d, jj = 50, 50, 50
        max_j = max(max_j, jj)
    
    if max_j <= -1000:
        return 5.0
    
    clean_depth = max_j - j_val
    # 清洗深度≥80→10分, ≥50→8分, ≥20→6分
    if clean_depth >= 80:
        return 10.0
    if clean_depth >= 50:
        return round(8.0 + (clean_depth - 50) * 0.067, 1)
    if clean_depth >= 20:
        return round(6.0 + (clean_depth - 20) * 0.067, 1)
    return max(3.0, round(clean_depth * 0.15, 1))


# ── P2: 蜈蚣图上下文感知 ──

def _is_low_volume_context(klines: List[dict]) -> bool:
    """
    判断是否处于缩量横盘状态（B1完美图特征）。
    如果20日均量 < 60日均量×0.8 → 缩量状态 → 放宽蜈蚣图阈值。
    """
    if len(klines) < 60:
        return False
    vols_20 = [float(k["vol"]) for k in klines[-20:]]
    vols_60 = [float(k["vol"]) for k in klines[-60:]]
    avg_20 = sum(vols_20) / 20
    avg_60 = sum(vols_60) / 60
    return avg_20 < avg_60 * 0.85 if avg_60 > 0 else False


# ══════════════════════════════════════════════════════════════
# P0-3 硬过滤：蜈蚣图 + 沙漏
# ══════════════════════════════════════════════════════════════
def detect_centipede_pattern(klines: List[dict], threshold: float = 60.0) -> Dict[str, Any]:
    """
    蜈蚣图识别：堆量不涨、影线交替、无呼吸节奏的烂股形态。
    五大因子各 0-20 分，总分 >= threshold 判定为蜈蚣图。
    返回 {'is_centipede', 'score', 'factors'}。
    """
    result = {"is_centipede": False, "score": 0, "factors": {}}
    if len(klines) < 20:
        return result

    recent = klines[-20:]
    closes = [float(k["close"]) for k in recent]
    opens = [float(k["open"]) for k in recent]
    highs = [float(k["high"]) for k in recent]
    lows = [float(k["low"]) for k in recent]
    vols = [float(k["vol"]) for k in recent]
    pcts = [float(k.get("pct_chg", 0.0)) for k in recent]

    factors = {}
    n = len(recent)

    up_days = 0
    for i in range(n):
        body = abs(closes[i] - opens[i])
        if body > 0 and (highs[i] - closes[i]) > 2 * body:
            up_days += 1
    up_ratio = up_days / 20
    factors["长上影线"] = 20 if up_ratio > 0.4 else (10 if up_ratio > 0.25 else 0)

    dn_days = 0
    for i in range(n):
        body = abs(closes[i] - opens[i])
        if body > 0 and (closes[i] - lows[i]) > 2 * body:
            dn_days += 1
    dn_ratio = dn_days / 20
    factors["长下影线"] = 20 if dn_ratio > 0.4 else (10 if dn_ratio > 0.25 else 0)

    doji_days = 0
    for i in range(n):
        if opens[i] > 0 and abs(closes[i] - opens[i]) / opens[i] < 0.01:
            doji_days += 1
    doji_ratio = doji_days / 20
    factors["十字星"] = 20 if doji_ratio > 0.3 else (10 if doji_ratio > 0.15 else 0)

    vol_mean = sum(vols) / len(vols)
    vol_cv = (((sum((v - vol_mean) ** 2 for v in vols) / len(vols)) ** 0.5) / vol_mean
              if vol_mean > 0 else 0)
    factors["量能无规律"] = 20 if vol_cv > 0.8 else (10 if vol_cv > 0.5 else 0)

    total_chg = (closes[-1] - opens[0]) / opens[0] if opens[0] > 0 else 0
    pct_mean = sum(pcts) / len(pcts)
    pct_std = (sum((p - pct_mean) ** 2 for p in pcts) / len(pcts)) ** 0.5
    is_range = abs(total_chg) < 0.05
    is_volatile = pct_std > 2.0
    factors["价格无趋势"] = 20 if (is_range and is_volatile) else (10 if (is_range or is_volatile) else 0)

    total = sum(factors.values())
    result["score"] = total
    result["factors"] = factors
    result["is_centipede"] = total > threshold
    return result


def calculate_sandglass_score(klines: List[dict]) -> Dict[str, Any]:
    """
    沙漏评分（图形审美）：五因子各 0-20 分，总分 0-100。
    is_perfect >= 80。返回 {'score', 'rating', 'factors', 'is_perfect'}。
    """
    result = {"score": 0, "rating": "极差", "factors": {}, "is_perfect": False}
    if len(klines) < 20:
        return result

    closes = [float(k["close"]) for k in klines]
    opens = [float(k["open"]) for k in klines]
    vols = [float(k["vol"]) for k in klines]
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    pcts = [float(k.get("pct_chg", 0.0)) for k in klines]
    n = len(klines)
    cur = closes[-1]

    vol_ma10 = sum(vols[-10:]) / 10
    vol_ma20 = sum(vols[-20:]) / 20
    vratio = vol_ma10 / vol_ma20 if vol_ma20 > 0 else 1.0
    sa = 12 if vratio < 0.6 else (8 if vratio < 0.8 else (4 if vratio < 1.0 else 0))
    r5 = vols[-5:]
    p5 = vols[-10:-5]
    base_range = (max(p5) - min(p5)) if p5 else (max(r5) - min(r5))
    vr_range = (max(r5) - min(r5)) / base_range if base_range > 0 else 1.0
    sb = 8 if vr_range < 0.5 else (5 if vr_range < 0.8 else (3 if vr_range < 1.0 else 0))
    score_contraction = min(20, sa + sb)

    support = min(lows[-20:])
    dist = (cur - support) / support if support > 0 else 1.0
    score_pivot = (20 if dist <= 0.03 else 16 if dist <= 0.05 else 12 if dist <= 0.08
                   else 8 if dist <= 0.10 else 4 if dist <= 0.15 else 0)

    vol_slope = _slope(vols[-10:], 10) if len(vols) >= 10 else 0
    sn = vol_slope / vol_ma10 if vol_ma10 > 0 else 0
    if -0.05 <= sn <= -0.01: score_vs = 20
    elif -0.10 <= sn < -0.05: score_vs = 15
    elif -0.01 < sn <= 0.02: score_vs = 12
    elif -0.15 <= sn < -0.10: score_vs = 8
    elif sn > 0.05: score_vs = 2
    else: score_vs = 5

    ma5, ma10, ma20 = _ma(closes, 5), _ma(closes, 10), _ma(closes, 20)
    score_ma = 0
    if ma5 > ma10 > ma20: score_ma += 10
    elif ma5 > ma10 or ma10 > ma20: score_ma += 5
    if ma20 > 0 and cur > ma20: score_ma += 4
    if ma20 > 0:
        gap = abs(ma5 - ma20) / ma20
        score_ma += 6 if gap < 0.02 else 4 if gap < 0.05 else 2 if gap < 0.08 else 0
    score_ma = min(20, score_ma)

    score_risk = 20
    for i in range(max(0, n - 5), n):
        if i > 0:
            gap_dn = (opens[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] > 0 else 0
            if gap_dn < -0.03:
                score_risk -= 10
                break
    down_cnt = 0
    for p in pcts[-5:]:
        if p < 0: down_cnt += 1
        else: down_cnt = 0
    if down_cnt >= 3: score_risk -= 5
    if n >= 5 and vols[-1] > vol_ma10 * 1.8 and closes[-1] <= closes[-2]:
        score_risk -= 5
    look = min(240, n)
    high_52 = max(highs[-look:])
    if high_52 > 0 and (high_52 - cur) / high_52 < 0.05:
        score_risk -= 5
    score_risk = max(0, score_risk)

    total = max(0, min(100, score_contraction + score_pivot + score_vs + score_ma + score_risk))
    rating = ("极佳" if total >= 80 else "良好" if total >= 65 else "一般" if total >= 45
              else "较差" if total >= 25 else "极差")
    result.update({
        "score": total,
        "rating": rating,
        "factors": {"缩量收敛": score_contraction, "枢轴邻近": score_pivot,
                     "量能斜率": score_vs, "均线结构": score_ma, "事件风险": score_risk},
        "is_perfect": total >= 80,
    })
    return result


# ══════════════════════════════════════════════════════════════
# P0-2 MDC 多维验证（移植自 base_strategies.detect_b1 的 MDC 段）
# ══════════════════════════════════════════════════════════════
def verify_b1_mdc(klines: List[dict], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    对通过基础条件的候选做 MDC 七层验证，返回置信度与明细。
    七层：麒麟背景 / 布林下轨 / 资金流 / RSI6 / ADX / 缩量 / 绿砖排除。
    """
    ind = {
        "kdj": compute_kdj(klines),
        "bbi": compute_bbi(klines),
        "boll": compute_bollinger(klines),
        "rsi6": compute_rsi(klines, 6),
        "adx": compute_adx_dmi(klines),
        "vol_ratio": compute_vol_ratio(klines),
    }
    close = float(klines[-1]["close"])
    vol = float(klines[-1]["vol"])
    prev_vol = float(klines[-2]["vol"]) if len(klines) >= 2 else vol
    is_suoliang = vol <= prev_vol * 0.5 if prev_vol > 0 else False

    # 绿砖排除（连续下跌 >= green_brick_limit 天）
    recent_4 = klines[-4:] if len(klines) >= 4 else klines
    yin_count = sum(1 for k in recent_4 if float(k["close"]) < float(k["open"]))
    if yin_count >= params.get("green_brick_limit", 4):
        return {"confidence": 0.0, "mdc_details": ["绿砖状态(连续下跌超阈值)"],
                "ind": ind, "kirin_stage": None, "excluded": True}

    confidence = 0.5 + (0.1 if is_suoliang else 0)
    details: List[str] = []

    kirin = detect_kirin_stage(klines)
    stage = kirin.get("stage")
    if stage == "吸筹":
        confidence += 0.20; details.append("主力吸筹期(高安全)")
    elif stage == "回落":
        confidence += 0.10; details.append("回落寻底期")
    elif stage == "派发":
        confidence -= 0.30; details.append("主力派发期(高风险)")

    _, _, boll_lower, _ = ind["boll"]
    if boll_lower and close <= boll_lower * 1.02:
        confidence += 0.15; details.append("触及布林下轨(超跌)")

    li = float(klines[-1].get("large_inflow", 0) or 0)
    lo = float(klines[-1].get("large_outflow", 0) or 0)
    if li > lo:
        confidence += 0.10; details.append("主力大单净流入")

    rsi6_ceiling = params.get("rsi6_ceiling", 25)
    if ind["rsi6"] < rsi6_ceiling:
        confidence += 0.05; details.append(f"RSI6超卖({ind['rsi6']})")

    adx_floor = params.get("adx_floor", 40)
    adx_val = ind["adx"][0]
    if adx_val > adx_floor:
        confidence += 0.10; details.append(f"ADX高位动能竭尽({adx_val})")

    confidence = max(0.1, min(confidence, 0.98))
    return {
        "confidence": round(confidence, 2),
        "mdc_details": details,
        "ind": ind,
        "kirin_stage": stage,
        "excluded": False,
    }


# ══════════════════════════════════════════════════════════════
# 单股管线 v2.0：连续型评分 + 硬过滤四关 + 区分特征层
# ══════════════════════════════════════════════════════════════

# --- 硬过滤四关 ---
def _hard_filter_no_breakthrough(brk_info: Dict) -> bool:
    """关1：无突破→淘汰"""
    return not brk_info["has_break"]

def _hard_filter_j_threshold(j_val: float, params: Dict) -> bool:
    """关2：J > j_threshold → 淘汰（默认14）"""
    return j_val > params.get("j_threshold", 14)

def _hard_filter_white_below_yellow(klines: List[dict]) -> bool:
    """
    关3：白线 < 黄线 → 淘汰。
    优先用 compute_dual_line 原生计算；如果结果白<黄且能找到 Z哥缓存，
    则用Z哥预计算白/黄线修正（本地数据无close_adj导致MA114黄线偏差）。
    """
    _, _, status = compute_dual_line(klines)
    if status == "白>黄":
        return False  # 通过

    # 本地计算白<黄，尝试Z哥缓存修正
    ts_code = klines[-1].get("ts_code", "") if klines else ""
    trade_date = klines[-1].get("trade_date", "") if klines else ""
    if ts_code and trade_date:
        try:
            import pandas as pd
            cache_base = r"D:\BaiduSyncdisk\Z\B1完美图\cache"
            for strat in ["yunsheng", "nadao", "weifeng"]:
                f = os.path.join(cache_base, strat, f"{ts_code}.parquet")
                if not os.path.exists(f):
                    continue
                df = pd.read_parquet(f)
                df["trade_date"] = df["trade_date"].astype(str)
                r = df[df["trade_date"] == trade_date]
                if r.empty:
                    continue
                r = r.iloc[0]
                w = float(r.get("white_line", 0))
                y = float(r.get("yellow_line", 0))
                if w > y > 0:
                    return False
                break
        except Exception:
            pass

    return True  # 白<黄 → 淘汰

def _hard_filter_centipede(klines: List[dict], params: Dict) -> bool:
    """关4：蜈蚣图 > centipede_max → 淘汰（缩量状态放宽到+15）"""
    base_threshold = params.get("centipede_max", 60)
    # 缩量横盘上下文放宽阈值（B1完美图特征会触发蜈蚣假阳性）
    if _is_low_volume_context(klines):
        threshold = base_threshold + 15  # 缩量状态：60→75
    else:
        threshold = base_threshold
    cent = detect_centipede_pattern(klines, threshold)
    return cent["is_centipede"]


# --- 连续型评分管线 ---
def _compute_base_score(klines: List[dict], j_val: float,
                        brk_info: Dict, up_info: Dict,
                        cross_days: int) -> Dict[str, Any]:
    """计算基础分 (F1-F12 + F9, 共95分) 和区分分 (F14-F17, 共25分)"""
    details = {}

    # ── 突破启动层 (35分) ──
    details["f1_breakthrough"] = score_f1_breakthrough(brk_info["break_vol_ratio"])
    details["f2_break_type"] = score_f2_break_type(brk_info["break_type"])
    details["f3_gain_pct"] = score_f3_accumulated_gain(up_info["accumulated_gain_pct"])

    # ── 回调路径层 (30分) ──
    details["f4_top_shrink"] = score_f4_top_shrink(klines, up_info)
    details["f5_retrace_depth"] = score_f5_retrace_depth(klines, up_info)
    details["f6_support_dev"] = score_f6_support_deviation(klines)
    details["f7_vol_slope"] = score_f7_volume_slope(klines, up_info)
    details["f8_yang_yin"] = score_f8_yang_yin_ratio(klines, up_info)

    # ── 当前状态层 (30分) ──
    details["f9_j_value"] = score_f9_j_value(j_val)
    details["f10_small_candle"] = score_f10_small_candle(klines)
    details["f11_sel_shrink"] = score_f11_selection_shrink(klines, up_info)
    details["f12_cross_days"] = score_f12_golden_cross(cross_days)
    details["f13_j_clean"] = score_f13_j_clean(klines, cross_days, j_val)

    base_score = (details["f1_breakthrough"] + details["f2_break_type"]
                  + details["f3_gain_pct"]
                  + details["f4_top_shrink"] + details["f5_retrace_depth"]
                  + details["f6_support_dev"] + details["f7_vol_slope"]
                  + details["f8_yang_yin"]
                  + details["f9_j_value"] + details["f10_small_candle"]
                  + details["f11_sel_shrink"] + details["f12_cross_days"]
                  + details["f13_j_clean"])

    return {"details": details, "base_score": round(base_score, 1)}


def _compute_distinguishing_score(klines: List[dict], params: Dict
                                  ) -> Dict[str, Any]:
    """计算区分特征分 (0-25分) — 蜈蚣图/沙漏/MDC/麒麟"""
    cent = detect_centipede_pattern(klines, params.get("centipede_max", 60))
    sand = calculate_sandglass_score(klines)
    mdc = verify_b1_mdc(klines, params)
    kirin = detect_kirin_stage(klines)

    # 沙漏分标准化到 0-10
    f14 = round(sand["score"] / 10.0, 1)
    # MDC置信度标准化到 0-8
    f15 = round(mdc["confidence"] * 8, 1)
    # 蜈蚣图反向分：<20高区分，20-40中等，40-60低区分
    cent_score = cent["score"]
    f16 = round(max(0.0, (60 - min(cent_score, 60)) / 60 * 7), 1)
    # 麒麟阶段：吸筹5 回落3 未知1 其他0
    stage = kirin.get("stage", "未知")
    f17 = {"吸筹": 5.0, "回落": 3.0, "未知": 1.0}.get(stage, 0.0)

    dist_score = f14 + f15 + f16 + f17

    return {
        "dist_score": round(dist_score, 1),
        "sandglass_score": sand["score"],
        "sandglass_rating": sand["rating"],
        "mdc_confidence": mdc["confidence"],
        "mdc_details": mdc["mdc_details"],
        "centipede_score": cent["score"],
        "kirin_stage": stage,
        "rsi6": mdc["ind"]["rsi6"],
        "adx": mdc["ind"]["adx"][0],
        "boll_lower": mdc["ind"]["boll"][2],
    }


def screen_stock(ts_code: str, name: str, klines: List[dict],
                 params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    对单只股票跑完整 B1 v2.0 管线（连续评分 + 硬过滤 + 区分特征层）。
    返回候选 dict 或 None（不通过硬过滤）。
    """
    # 数据验证
    if len(klines) < int(params.get("min_history", 30)):
        return None
    closes = [float(k["close"]) for k in klines]
    if closes[-1] <= float(params.get("price_min", 3.0)):
        return None

    # 计算共享信息
    k, d, j = compute_kdj(klines)
    brk_info = find_breakthrough_info(klines)
    up_info = find_up_phase_info(klines)
    cross_days = find_golden_cross_days(klines)

    # ── 硬过滤四关 ──
    # 关1: 无突破 → 淘汰
    if _hard_filter_no_breakthrough(brk_info):
        return None
    # 关2: J > 阈值 → 淘汰（默认14，对齐Z哥）
    if _hard_filter_j_threshold(j, params):
        return None
    # 关3: 白线 < 黄线 → 淘汰
    if _hard_filter_white_below_yellow(klines):
        return None
    # 关4: 蜈蚣图 ≥ 上限 → 淘汰
    if _hard_filter_centipede(klines, params):
        return None

    # ── 连续型评分 ──
    base = _compute_base_score(klines, j, brk_info, up_info, cross_days)
    dist = _compute_distinguishing_score(klines, params)
    total = base["base_score"] + dist["dist_score"]

    # 综合评分不足跳过（默认40分）
    if total < params.get("min_total_score", 40.0):
        return None

    close = closes[-1]
    _, _, dual_status = compute_dual_line(klines)

    return {
        "ts_code": ts_code,
        "name": name,
        "close": round(close, 2),
        "j": round(j, 1),
        "dual": dual_status,
        "score": round(total, 1),
        "base_score": base["base_score"],
        "dist_score": dist["dist_score"],
        # 突破信息
        "break_type": brk_info["break_type"],
        "break_vol_ratio": brk_info["break_vol_ratio"],
        # 金叉信息
        "cross_days": cross_days if cross_days != 999 else None,
        # 特征明细
        "f1_breakthrough": base["details"]["f1_breakthrough"],
        "f4_top_shrink": base["details"]["f4_top_shrink"],
        "f9_j_value": base["details"]["f9_j_value"],
        "f10_small_candle": base["details"]["f10_small_candle"],
        "f11_sel_shrink": base["details"]["f11_sel_shrink"],
        "f12_cross_days_score": base["details"]["f12_cross_days"],
        "f13_j_clean": base["details"]["f13_j_clean"],
        # P1 features
        "f3_gain_pct": base["details"]["f3_gain_pct"],
        "f5_retrace": base["details"]["f5_retrace_depth"],
        "f6_support": base["details"]["f6_support_dev"],
        "f7_vol_slope": base["details"]["f7_vol_slope"],
        "f8_yang_yin": base["details"]["f8_yang_yin"],
        # 区分特征
        **{k: v for k, v in dist.items() if k != "dist_score"},
    }


# ══════════════════════════════════════════════════════════════
# 全市场扫描（供 daily.py 调用，替代原 step_screening 内联逻辑）
# ══════════════════════════════════════════════════════════════
def screen_universe(kline_files: List, names_map: Dict[str, str],
                    params: Dict[str, Any], top_n: int = 10) -> List[Dict[str, Any]]:
    """
    扫描全市场 parquet 文件，返回 B1 候选（按 score 降序）。
    kline_files: pathlib.Path 列表（每只股票一个 parquet）
    names_map: {ts_code: name}
    """
    import pandas as pd
    candidates = []
    window = max(int(params.get("min_history", 30)), 150)
    for f in kline_files:
        ts_code = f.stem
        if ts_code.startswith("000") and ts_code.endswith(".SH"):
            continue
        if ts_code.startswith("399"):
            continue
        try:
            df = pd.read_parquet(f)
            if len(df) < params.get("min_history", 30):
                continue
            df = df.sort_values("trade_date").reset_index(drop=True).tail(window)
            target_date = str(df.iloc[-1]["trade_date"]) if len(df) > 0 else ""
            klines = [
                {
                    "open": float(r["open"]), "high": float(r["high"]),
                    "low": float(r["low"]), "close": float(r["close"]),
                    "vol": float(r["vol"]),
                    "pct_chg": float(r.get("pct_chg", 0.0)),
                    "large_inflow": float(r.get("large_inflow", 0) or 0),
                    "large_outflow": float(r.get("large_outflow", 0) or 0),
                }
                for _, r in df.iterrows()
            ]
            # 在末条注入 ts_code + trade_date，供Z哥缓存修正双线用
            if klines:
                klines[-1]["ts_code"] = ts_code
                klines[-1]["trade_date"] = target_date
            cand = screen_stock(ts_code, names_map.get(ts_code, ""), klines, params)
            if cand:
                candidates.append(cand)
        except Exception:
            continue

    candidates.sort(key=lambda x: (-x["score"], x["j"]))
    return candidates[:top_n]


# ── 辅助：从Z哥cache注入预计算双线值 ──
def _inject_precomputed_dual_line(klines: List[dict], ts_code: str,
                                   target_date: str) -> None:
    """
    尝试从 Z哥 cache 读取预计算的 white_line/yellow_line 注入 klines 末条。
    本地数据无 close_adj 导致 MA114 黄线偏差，用 Z哥 cache 的预计算值修正。
    失败则静默跳过（不影响主流程）。
    """
    try:
        import pandas as pd
        cache_base = r"D:\BaiduSyncdisk\Z\B1完美图\cache"
        for strat in ["yunsheng", "nadao", "weifeng"]:
            f = os.path.join(cache_base, strat, f"{ts_code}.parquet")
            if not os.path.exists(f):
                continue
            df = pd.read_parquet(f)
            df["trade_date"] = df["trade_date"].astype(str)
            r = df[df["trade_date"] == target_date]
            if r.empty:
                continue
            r = r.iloc[0]
            w = r.get("white_line")
            y = r.get("yellow_line")
            if w is not None and y is not None:
                klines[-1]["precomputed_white"] = float(w)
                klines[-1]["precomputed_yellow"] = float(y)
                return
    except Exception:
        pass
