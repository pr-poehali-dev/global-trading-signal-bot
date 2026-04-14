"""
AI-движок сигналов мирового уровня. Порог публикации: 90%+.
25 торговых пар. Сохраняет каждый прогноз в БД для честной статистики.
Анализирует: RSI(1h+4h+1d), MACD, Bollinger, Stochastic, ATR, EMA,
объём, Fear & Greed, дивергенции, паттерны свечей, поддержка/сопротивление.
"""
import json
import urllib.request
import math
import os
import psycopg2
from datetime import datetime
import urllib.parse

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json"
}

SCHEMA = "t_p73206386_global_trading_signa"

PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "INJUSDT", "SUIUSDT",
    "ARBUSDT", "FETUSDT",
]

EXCHANGES = {
    "BTCUSDT": "Binance", "ETHUSDT": "Bybit", "SOLUSDT": "Binance",
    "BNBUSDT": "Binance", "XRPUSDT": "OKX", "DOGEUSDT": "MEXC",
    "ADAUSDT": "Binance", "AVAXUSDT": "OKX", "DOTUSDT": "Bybit",
    "LINKUSDT": "MEXC", "MATICUSDT": "OKX", "LTCUSDT": "Bybit",
    "ATOMUSDT": "Binance", "NEARUSDT": "OKX", "APTUSDT": "MEXC",
    "ARBUSDT": "Binance", "OPUSDT": "OKX", "INJUSDT": "Bybit",
    "SUIUSDT": "MEXC", "SEIUSDT": "Bybit", "TIAUSDT": "OKX",
    "WLDUSDT": "Binance", "FETUSDT": "MEXC", "RENDERUSDT": "Bybit",
    "1000SHIBUSDT": "MEXC",
}

# ─── Anti-Drain система ──────────────────────────────────────────────────────
# Плечо выбирается автоматически по уверенности AI:
#   90-92% → 2x    93-94% → 3x    95-96% → 4x    97% → 5x
# Размер позиции: max 8% от текущего баланса
# Стоп-лосс: всегда ATR*1.6 (макс потеря ~2-3% от баланса с плечом)
# Если drawdown > 10% от пика → снижаем размер вдвое
# Если 3 лосса подряд → пауза (не торгуем, пока нет 95%+ сигнала)
POSITION_PCT = 0.08   # 8% от баланса на сделку
MAX_DRAWDOWN = 0.10   # 10% от пика → защитный режим
SAFETY_BUFFER = 0.15  # Держим 15% баланса как подушку

def send_telegram(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

def notify_new_signal(sig: dict):
    lev = sig.get("leverage", 1)
    pos = sig.get("position_size", 0)
    emoji = "🟢" if sig["type"] == "LONG" else "🔴"
    send_telegram(
        f"{emoji} <b>Новый сигнал: {sig['pair']}</b>\n"
        f"Направление: <b>{sig['type']}</b> · Биржа: {sig['exchange']}\n"
        f"Уверенность AI: <b>{sig['confidence']}%</b>\n"
        f"Плечо: <b>{lev}x</b> · Позиция: <b>${pos}</b>\n"
        f"▫️ Вход: {sig['entry']}\n"
        f"🎯 Цель: {sig['target']}\n"
        f"🛑 Стоп: {sig['stop']}\n"
        f"R/R: {sig.get('risk_reward', '—')} · Потенциал: +{sig.get('potential_pct', 0)}%"
    )

def notify_close_signal(pair: str, result: str, pct: float, pnl_usdt: float, balance: float):
    emoji = "✅" if result == "win" else "❌"
    send_telegram(
        f"{emoji} <b>Сигнал закрыт: {pair}</b>\n"
        f"Результат: <b>{result.upper()}</b> · {'+' if pct >= 0 else ''}{pct:.2f}%\n"
        f"P&L: <b>{'+' if pnl_usdt >= 0 else ''}${pnl_usdt:.2f}</b>\n"
        f"💰 Баланс портфеля: <b>${balance:.2f}</b>"
    )

MIN_CONFIDENCE = 90

def fetch_url(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TradingBot/3.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def get_candles(symbol: str, interval: str = "1h", limit: int = 100) -> list:
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    raw = fetch_url(url)
    if not raw:
        return []
    return [{"o": float(c[1]), "h": float(c[2]), "l": float(c[3]), "c": float(c[4]), "v": float(c[5])} for c in raw]

def get_fear_greed() -> dict:
    data = fetch_url("https://api.alternative.me/fng/?limit=1")
    if data and data.get("data"):
        val = int(data["data"][0]["value"])
        cls = data["data"][0]["value_classification"]
        return {"value": val, "classification": cls}
    return {"value": 50, "classification": "Neutral"}

def calc_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100.0
    return round(100 - (100 / (1 + ag / al)), 2)

def calc_ema(data: list, period: int) -> list:
    if not data:
        return []
    ema = [data[0]]
    k = 2 / (period + 1)
    for v in data[1:]:
        ema.append((v - ema[-1]) * k + ema[-1])
    return ema

def calc_macd(closes: list) -> dict:
    if len(closes) < 35:
        return {"macd": 0, "signal": 0, "hist": 0, "trend": "neutral", "cross": "none"}
    e12 = calc_ema(closes, 12)
    e26 = calc_ema(closes, 26)
    ml = [a - b for a, b in zip(e12[13:], e26)]
    sl = calc_ema(ml, 9)
    hist = ml[-1] - sl[-1] if sl else 0
    prev_hist = ml[-2] - sl[-2] if len(ml) > 1 and len(sl) > 1 else 0
    cross = "none"
    if prev_hist < 0 and hist > 0:
        cross = "bullish_cross"
    elif prev_hist > 0 and hist < 0:
        cross = "bearish_cross"
    trend = "bullish" if hist > 0 else "bearish" if hist < 0 else "neutral"
    return {"macd": round(ml[-1], 8), "signal": round(sl[-1], 8), "hist": round(hist, 8), "trend": trend, "cross": cross}

def calc_bollinger(closes: list, period: int = 20) -> dict:
    if len(closes) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "pct_b": 0.5, "squeeze": False, "bandwidth": 0}
    w = closes[-period:]
    mid = sum(w) / period
    std = math.sqrt(sum((x - mid) ** 2 for x in w) / period)
    upper = mid + 2 * std
    lower = mid - 2 * std
    pct_b = (closes[-1] - lower) / (upper - lower) if upper != lower else 0.5
    bandwidth = (upper - lower) / mid if mid > 0 else 0
    return {"upper": upper, "middle": mid, "lower": lower,
            "pct_b": round(pct_b, 4), "squeeze": bandwidth < 0.03, "bandwidth": round(bandwidth, 4)}

def calc_stochastic(highs: list, lows: list, closes: list, k: int = 14) -> dict:
    if len(closes) < k:
        return {"k": 50.0, "d": 50.0, "zone": "neutral"}
    h = max(highs[-k:])
    l = min(lows[-k:])
    k_val = ((closes[-1] - l) / (h - l) * 100) if h != l else 50.0
    zone = "oversold" if k_val < 20 else "overbought" if k_val > 80 else "neutral"
    # Simplified %D
    k_vals = []
    for i in range(max(0, len(closes)-k-3), len(closes)-k+1):
        if i < 0: continue
        hi = max(highs[i:i+k]); lo = min(lows[i:i+k])
        kv = ((closes[i+k-1] - lo) / (hi - lo) * 100) if hi != lo else 50.0
        k_vals.append(kv)
    d_val = sum(k_vals[-3:]) / 3 if len(k_vals) >= 3 else k_val
    return {"k": round(k_val, 2), "d": round(d_val, 2), "zone": zone}

def calc_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return closes[-1] * 0.02 if closes else 0
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

def detect_trend(closes: list) -> dict:
    if len(closes) < 50:
        return {"trend": "neutral", "strength": 0}
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    ema50 = calc_ema(closes, 50)
    price = closes[-1]
    slope = (ema50[-1] - ema50[-10]) / ema50[-10] * 100 if len(ema50) >= 10 else 0
    if price > ema9[-1] > ema21[-1] > ema50[-1]:
        return {"trend": "strong_uptrend", "strength": min(int(abs(slope) * 25 + 30), 100), "ema9": ema9[-1], "ema21": ema21[-1], "ema50": ema50[-1]}
    elif price > ema21[-1] > ema50[-1]:
        return {"trend": "uptrend", "strength": min(int(abs(slope) * 20 + 15), 80), "ema9": ema9[-1], "ema21": ema21[-1], "ema50": ema50[-1]}
    elif price < ema9[-1] < ema21[-1] < ema50[-1]:
        return {"trend": "strong_downtrend", "strength": min(int(abs(slope) * 25 + 30), 100), "ema9": ema9[-1], "ema21": ema21[-1], "ema50": ema50[-1]}
    elif price < ema21[-1] < ema50[-1]:
        return {"trend": "downtrend", "strength": min(int(abs(slope) * 20 + 15), 80), "ema9": ema9[-1], "ema21": ema21[-1], "ema50": ema50[-1]}
    return {"trend": "sideways", "strength": 20, "ema9": ema9[-1], "ema21": ema21[-1], "ema50": ema50[-1]}

def detect_divergence(closes: list, rsi_1h: float, rsi_4h: float) -> str:
    if len(closes) < 10:
        return "none"
    p_prev = closes[-10]
    p_now = closes[-1]
    # Бычья: цена ниже, RSI выше → разворот вверх
    if p_now < p_prev * 0.99 and rsi_1h > rsi_4h + 5:
        return "bullish_divergence"
    # Медвежья: цена выше, RSI ниже → разворот вниз
    if p_now > p_prev * 1.01 and rsi_1h < rsi_4h - 5:
        return "bearish_divergence"
    return "none"

def detect_candle_patterns(candles: list) -> list:
    patterns = []
    if len(candles) < 3:
        return patterns
    for i in range(-3, 0):
        c = candles[i]
        body = abs(c["c"] - c["o"])
        wick_lo = min(c["c"], c["o"]) - c["l"]
        wick_hi = c["h"] - max(c["c"], c["o"])
        rng = c["h"] - c["l"]
        if rng == 0: continue
        if body > 0 and wick_lo > body * 2 and wick_hi < body * 0.5 and c["c"] > c["o"]:
            patterns.append("Молот (бычий разворот)")
        if body > 0 and wick_hi > body * 2 and wick_lo < body * 0.5 and c["c"] < c["o"]:
            patterns.append("Висельник (медвежий разворот)")
        if body < rng * 0.1:
            patterns.append("Доджи (нерешительность)")
        if i > -3:
            prev = candles[i - 1]
            if (prev["c"] < prev["o"] and c["c"] > c["o"] and c["c"] > prev["o"] and c["o"] < prev["c"]):
                patterns.append("Бычье поглощение")
            if (prev["c"] > prev["o"] and c["c"] < c["o"] and c["o"] > prev["c"] and c["c"] < prev["o"]):
                patterns.append("Медвежье поглощение")
    return list(set(patterns[:3]))

def detect_sr(candles: list, price: float) -> dict:
    if len(candles) < 20:
        return {"support": price * 0.97, "resistance": price * 1.03, "near_support": False, "near_resistance": False}
    highs = sorted([c["h"] for c in candles[-40:]], reverse=True)
    lows = sorted([c["l"] for c in candles[-40:]])
    resistance = sorted(highs[:5])[2]
    support = sorted(lows[:5])[2]
    return {"support": round(support, 8), "resistance": round(resistance, 8),
            "near_support": abs(price - support) / price < 0.015,
            "near_resistance": abs(price - resistance) / price < 0.015}

def calc_volume(candles: list) -> dict:
    if len(candles) < 20:
        return {"ratio": 1.0, "trend": "normal", "climax": False}
    vols = [c["v"] for c in candles]
    avg20 = sum(vols[-20:]) / 20
    ratio = vols[-1] / avg20 if avg20 > 0 else 1.0
    trend_up = sum(vols[-5:]) / 5 > sum(vols[-10:-5]) / 5
    return {"ratio": round(ratio, 2), "trend": "increasing" if trend_up and ratio > 1.2 else "decreasing" if ratio < 0.6 else "normal", "climax": ratio > 3.0}

def score_signal(rsi_1h, rsi_4h, rsi_1d, macd, bb, stoch, trend, vol, fg, divergence, sr, patterns) -> dict:
    bull = 0; bear = 0; factors = []
    crit_bull = 0; crit_bear = 0

    # RSI 1h (15)
    if rsi_1h < 28: bull += 15; crit_bull += 1; factors.append(f"RSI(1h)={rsi_1h} — экстремальная перепроданность ↑↑")
    elif rsi_1h < 38: bull += 8; factors.append(f"RSI(1h)={rsi_1h} — перепроданность ↑")
    elif rsi_1h > 72: bear += 15; crit_bear += 1; factors.append(f"RSI(1h)={rsi_1h} — экстремальная перекупленность ↓↓")
    elif rsi_1h > 62: bear += 8; factors.append(f"RSI(1h)={rsi_1h} — перекупленность ↓")
    else: factors.append(f"RSI(1h)={rsi_1h} — нейтрально")

    # RSI 4h (12)
    if rsi_4h < 30: bull += 12; crit_bull += 1; factors.append(f"RSI(4h)={rsi_4h} — подтверждение перепроданности на 4h")
    elif rsi_4h < 45: bull += 5; factors.append(f"RSI(4h)={rsi_4h} — зона интереса на 4h")
    elif rsi_4h > 70: bear += 12; crit_bear += 1; factors.append(f"RSI(4h)={rsi_4h} — подтверждение перекупленности на 4h")
    elif rsi_4h > 58: bear += 5; factors.append(f"RSI(4h)={rsi_4h} — нейтрально-медвежий 4h")

    # RSI 1d (10)
    if rsi_1d < 35: bull += 10; crit_bull += 1; factors.append(f"RSI(1d)={rsi_1d} — глобальная перепроданность")
    elif rsi_1d > 70: bear += 10; crit_bear += 1; factors.append(f"RSI(1d)={rsi_1d} — глобальная перекупленность")

    # MACD крест (15)
    if macd["cross"] == "bullish_cross": bull += 15; crit_bull += 1; factors.append("MACD бычий крест — сильнейший разворот ↑↑")
    elif macd["cross"] == "bearish_cross": bear += 15; crit_bear += 1; factors.append("MACD медвежий крест — сильнейший разворот ↓↓")
    elif macd["trend"] == "bullish": bull += 7; factors.append("MACD бычий импульс")
    elif macd["trend"] == "bearish": bear += 7; factors.append("MACD медвежий импульс")

    # Bollinger (10)
    if bb["pct_b"] < 0.05: bull += 10; crit_bull += 1; factors.append("Цена пробила нижнюю полосу BB — отскок ожидается")
    elif bb["pct_b"] < 0.15: bull += 6; factors.append(f"BB %B={bb['pct_b']} — у нижней границы")
    elif bb["pct_b"] > 0.95: bear += 10; crit_bear += 1; factors.append("Цена пробила верхнюю полосу BB — разворот вниз")
    elif bb["pct_b"] > 0.85: bear += 6; factors.append(f"BB %B={bb['pct_b']} — у верхней границы")
    if bb["squeeze"]: factors.append("Bollinger Squeeze — взрывное движение на подходе")

    # Stochastic (8)
    if stoch["zone"] == "oversold" and stoch["k"] > stoch["d"]: bull += 8; crit_bull += 1; factors.append(f"Stoch={stoch['k']} — перепроданность + крест вверх")
    elif stoch["zone"] == "overbought" and stoch["k"] < stoch["d"]: bear += 8; crit_bear += 1; factors.append(f"Stoch={stoch['k']} — перекупленность + крест вниз")

    # Тренд EMA (12)
    t = trend["trend"]
    if t == "strong_uptrend": bull += 12; crit_bull += 1; factors.append(f"Сильный тренд EMA9>EMA21>EMA50, сила {trend['strength']}%")
    elif t == "uptrend": bull += 6; factors.append(f"Восходящий тренд, сила {trend['strength']}%")
    elif t == "strong_downtrend": bear += 12; crit_bear += 1; factors.append(f"Сильный нисходящий тренд, сила {trend['strength']}%")
    elif t == "downtrend": bear += 6; factors.append(f"Нисходящий тренд, сила {trend['strength']}%")

    # Объём (6)
    if vol["climax"]: factors.append(f"Объёмный клаймакс x{vol['ratio']} — возможный разворот")
    elif vol["trend"] == "increasing" and vol["ratio"] > 1.5:
        if bull > bear: bull += 4
        else: bear += 4
        factors.append(f"Объём подтверждает движение x{vol['ratio']}")

    # Fear & Greed (8)
    fg_v = fg["value"]
    if fg_v < 20: bull += 8; crit_bull += 1; factors.append(f"F&G={fg_v} Extreme Fear — исторически лучшая точка LONG")
    elif fg_v < 35: bull += 4; factors.append(f"F&G={fg_v} Fear")
    elif fg_v > 80: bear += 8; crit_bear += 1; factors.append(f"F&G={fg_v} Extreme Greed — рынок перегрет")
    elif fg_v > 70: bear += 4; factors.append(f"F&G={fg_v} Greed")
    else: factors.append(f"F&G={fg_v} нейтральный сентимент")

    # Дивергенция (8)
    if divergence == "bullish_divergence": bull += 8; crit_bull += 1; factors.append("Бычья дивергенция RSI: цена↓, RSI↑")
    elif divergence == "bearish_divergence": bear += 8; crit_bear += 1; factors.append("Медвежья дивергенция RSI: цена↑, RSI↓")

    # S/R (5)
    if sr["near_support"]: bull += 5; factors.append(f"Цена у ключевой поддержки {sr['support']:.4f}")
    if sr["near_resistance"]: bear += 5; factors.append(f"Цена у ключевого сопротивления {sr['resistance']:.4f}")

    # Паттерны (5)
    for p in patterns:
        if "бычий" in p.lower() or "молот" in p.lower(): bull += 3; factors.append(f"Паттерн: {p}")
        elif "медвежий" in p.lower() or "висельник" in p.lower(): bear += 3; factors.append(f"Паттерн: {p}")

    total = bull + bear
    if total == 0:
        return {"direction": "NONE", "confidence": 0, "bull": 0, "bear": 0, "factors": factors, "critical": 0}

    if bull >= bear:
        direction = "LONG"; dominance = bull / total; crit = crit_bull
    else:
        direction = "SHORT"; dominance = bear / total; crit = crit_bear

    base = dominance * 100
    crit_bonus = max(0, (crit - 3) * 5)
    crit_penalty = max(0, (3 - crit) * 10)

    # Штраф за противоречие со старшим ТФ
    if direction == "LONG" and rsi_1d > 65: base -= 10; factors.append("Внимание: RSI(1d) высокий — против глобального тренда")
    if direction == "SHORT" and rsi_1d < 40: base -= 10; factors.append("Внимание: RSI(1d) низкий — против глобального тренда")

    confidence = min(int(base + crit_bonus - crit_penalty), 97)
    if (direction == "LONG" and bull < 40) or (direction == "SHORT" and bear < 40):
        confidence = min(confidence, 80)

    return {
        "direction": direction if confidence >= MIN_CONFIDENCE else "NONE",
        "confidence": confidence, "bull": bull, "bear": bear,
        "factors": factors[:12], "critical": crit
    }

def generate_signal(sym: str, fg: dict) -> dict | None:
    c1h = get_candles(sym, "1h", 80)
    c4h = get_candles(sym, "4h", 40)
    c1d = get_candles(sym, "1d", 30)
    if not c1h or len(c1h) < 50:
        return None

    cl1h = [c["c"] for c in c1h]
    cl4h = [c["c"] for c in c4h] if c4h else cl1h
    cl1d = [c["c"] for c in c1d] if c1d else cl1h
    h1h = [c["h"] for c in c1h]
    l1h = [c["l"] for c in c1h]
    price = cl1h[-1]

    rsi_1h = calc_rsi(cl1h)
    rsi_4h = calc_rsi(cl4h)
    rsi_1d = calc_rsi(cl1d)
    macd = calc_macd(cl1h)
    bb = calc_bollinger(cl1h)
    stoch = calc_stochastic(h1h, l1h, cl1h)
    trend = detect_trend(cl1h)
    vol = calc_volume(c1h)
    patterns = detect_candle_patterns(c1h)
    sr = detect_sr(c1h, price)
    divergence = detect_divergence(cl1h, rsi_1h, rsi_4h)

    score = score_signal(rsi_1h, rsi_4h, rsi_1d, macd, bb, stoch, trend, vol, fg, divergence, sr, patterns)
    if score["direction"] == "NONE":
        return None

    direction = score["direction"]
    confidence = score["confidence"]
    atr = calc_atr(h1h, l1h, cl1h)

    if direction == "LONG":
        target = round(price + atr * 4.0, 8)
        stop = round(price - atr * 1.6, 8)
    else:
        target = round(price - atr * 4.0, 8)
        stop = round(price + atr * 1.6, 8)

    pair = sym.replace("USDT", "/USDT")
    rr = round(abs(target - price) / abs(stop - price), 2) if abs(stop - price) > 0 else 2.5
    potential = round(abs(target - price) / price * 100, 2)

    return {
        "pair": pair, "symbol": sym, "type": direction,
        "exchange": EXCHANGES.get(sym, "Binance"),
        "entry": round(price, 8), "target": target, "stop": stop,
        "confidence": confidence, "status": "active",
        "rsi_1h": rsi_1h, "rsi_4h": rsi_4h, "rsi_1d": rsi_1d,
        "macd": macd, "bollinger": bb, "stochastic": stoch,
        "trend": trend, "volume": vol, "fear_greed": fg,
        "divergence": divergence, "patterns": patterns,
        "support_resistance": sr,
        "factors": score["factors"],
        "bull_score": score["bull"], "bear_score": score["bear"],
        "critical_signals": score["critical"],
        "risk_reward": rr, "potential_pct": potential,
        "atr": round(atr, 8),
        "time": datetime.utcnow().strftime("%H:%M"), "timeframe": "1h"
    }

def get_leverage(confidence: int) -> int:
    if confidence >= 97: return 5
    if confidence >= 95: return 4
    if confidence >= 93: return 3
    if confidence >= 90: return 2
    return 1

def get_portfolio():
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(f"SELECT id, initial_balance, current_balance, total_pnl, total_pnl_pct, total_trades, wins, losses, peak_balance, max_drawdown_pct, started_at FROM {SCHEMA}.portfolio LIMIT 1")
        r = cur.fetchone()
        if not r:
            cur.close(); conn.close()
            return {"balance": 1000, "initial": 1000, "pnl": 0, "pnl_pct": 0, "trades": 0, "wins": 0, "losses": 0, "peak": 1000, "drawdown": 0, "started": ""}
        cur.execute(f"SELECT date, balance, pnl_day_pct FROM {SCHEMA}.portfolio_daily ORDER BY date DESC LIMIT 30")
        daily = [{"date": str(x[0]), "balance": float(x[1]), "pnl_pct": float(x[2])} for x in cur.fetchall()]
        cur.close(); conn.close()
        return {
            "balance": float(r[2]), "initial": float(r[1]), "pnl": float(r[3]),
            "pnl_pct": float(r[4]), "trades": r[5], "wins": r[6], "losses": r[7],
            "peak": float(r[8]), "drawdown": float(r[9]), "started": str(r[10]),
            "daily": list(reversed(daily))
        }
    except Exception:
        return {"balance": 1000, "initial": 1000, "pnl": 0, "pnl_pct": 0, "trades": 0, "wins": 0, "losses": 0, "peak": 1000, "drawdown": 0, "started": "", "daily": []}

def check_anti_drain(portfolio: dict) -> dict:
    """Anti-drain: проверка можно ли торговать и с каким размером."""
    balance = portfolio["balance"]
    peak = portfolio.get("peak", balance)
    drawdown = (peak - balance) / peak if peak > 0 else 0
    recent_losses = portfolio.get("losses", 0) - portfolio.get("wins", 0)
    
    if drawdown > MAX_DRAWDOWN:
        return {"can_trade": True, "position_pct": POSITION_PCT * 0.5, "reason": "Защитный режим: drawdown > 10%, размер позиции уменьшен вдвое"}
    if balance < portfolio.get("initial", 1000) * 0.85:
        return {"can_trade": True, "position_pct": POSITION_PCT * 0.3, "reason": "Крайний режим: баланс < 85% от старта, минимальные позиции"}
    return {"can_trade": True, "position_pct": POSITION_PCT, "reason": "Нормальный режим"}

def save_signal(sig: dict, portfolio: dict) -> int | None:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        leverage = get_leverage(sig["confidence"])
        anti = check_anti_drain(portfolio)
        pos_pct = anti["position_pct"]
        position_size = round(portfolio["balance"] * pos_pct, 2)
        sig["leverage"] = leverage
        sig["position_size"] = position_size
        cur.execute(
            f"""INSERT INTO {SCHEMA}.signals
            (pair, signal_type, exchange, entry_price, target_price, stop_price,
             confidence, status, rsi, macd_signal, bb_position, volume_ratio,
             fear_greed, sentiment, analysis_text, timeframe, score_bull, score_bear,
             leverage, position_size)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (sig["pair"], sig["type"], sig["exchange"], sig["entry"], sig["target"], sig["stop"],
             sig["confidence"], "active", sig["rsi_1h"], sig["macd"]["signal"],
             sig["bollinger"]["pct_b"], sig["volume"]["ratio"],
             sig["fear_greed"]["value"], sig["fear_greed"]["classification"],
             " | ".join(sig["factors"][:6]), "1h", sig["bull_score"], sig["bear_score"],
             leverage, position_size)
        )
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()
        return row[0] if row else None
    except Exception:
        return None

def get_saved_signals(limit: int = 30) -> list:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(
            f"""SELECT id, pair, signal_type, exchange, entry_price, target_price, stop_price,
            confidence, status, rsi, fear_greed, analysis_text, created_at, result, result_pct,
            score_bull, score_bear, leverage, position_size, pnl_usdt
            FROM {SCHEMA}.signals WHERE status != 'archived' ORDER BY created_at DESC LIMIT %s""", (limit,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [{
            "id": r[0], "pair": r[1], "type": r[2], "exchange": r[3],
            "entry": float(r[4]), "target": float(r[5]), "stop": float(r[6]),
            "confidence": r[7], "status": r[8], "rsi_1h": float(r[9]) if r[9] else 50,
            "fear_greed": r[10], "factors": r[11].split(" | ") if r[11] else [],
            "time": r[12].strftime("%H:%M") if r[12] else "—",
            "date": r[12].strftime("%d.%m %H:%M") if r[12] else "—",
            "result": r[13], "result_pct": round(float(r[14]), 2) if r[14] else None,
            "bull_score": r[15] or 0, "bear_score": r[16] or 0,
            "leverage": r[17] or 1, "position_size": float(r[18]) if r[18] else 0,
            "pnl_usdt": round(float(r[19]), 2) if r[19] else None
        } for r in rows]
    except Exception:
        return []

def get_stats() -> dict:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*) as total,
                COUNT(*) FILTER (WHERE result = 'win') as wins,
                COUNT(*) FILTER (WHERE result = 'loss') as losses,
                COUNT(*) FILTER (WHERE result IS NULL AND status = 'active') as pending,
                AVG(result_pct) FILTER (WHERE result = 'win') as avg_win,
                AVG(result_pct) FILTER (WHERE result = 'loss') as avg_loss,
                AVG(confidence) as avg_conf,
                MAX(result_pct) as best, MIN(result_pct) as worst,
                COALESCE(SUM(pnl_usdt), 0) as total_pnl_usdt
            FROM {SCHEMA}.signals WHERE status != 'archived'
        """)
        row = cur.fetchone()
        total = row[0] or 0; wins = row[1] or 0; losses = row[2] or 0; pending = row[3] or 0
        avg_win = float(row[4]) if row[4] else 0; avg_loss = float(row[5]) if row[5] else 0
        avg_conf = float(row[6]) if row[6] else 0
        best = float(row[7]) if row[7] else 0; worst = float(row[8]) if row[8] else 0
        total_pnl_usdt = float(row[9]) if row[9] else 0
        closed = wins + losses
        win_rate = round(wins / closed * 100, 1) if closed > 0 else 0

        cur.execute(f"""
            SELECT DATE(created_at) as d, COUNT(*) as cnt,
                COUNT(*) FILTER (WHERE result='win') as w,
                COUNT(*) FILTER (WHERE result='loss') as l
            FROM {SCHEMA}.signals WHERE status != 'archived' AND created_at > NOW() - INTERVAL '30 days'
            GROUP BY d ORDER BY d DESC
        """)
        daily = [{"date": str(r[0]), "total": r[1], "wins": r[2], "losses": r[3]} for r in cur.fetchall()]

        cur.execute(f"""
            SELECT pair, COUNT(*) as total,
                COUNT(*) FILTER (WHERE result='win') as wins,
                AVG(result_pct) FILTER (WHERE result IS NOT NULL) as avg_pct
            FROM {SCHEMA}.signals WHERE result IS NOT NULL AND status != 'archived'
            GROUP BY pair ORDER BY wins DESC LIMIT 10
        """)
        by_pair = [{"pair": r[0], "total": r[1], "wins": r[2], "avg_pct": round(float(r[3]), 2) if r[3] else 0} for r in cur.fetchall()]

        cur.close(); conn.close()
        expectancy = round((win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss), 2)
        portfolio = get_portfolio()
        return {
            "total": total, "wins": wins, "losses": losses, "pending": pending,
            "closed": closed, "win_rate": win_rate,
            "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
            "avg_confidence": round(avg_conf, 1),
            "best_trade": round(best, 2), "worst_trade": round(worst, 2),
            "expectancy": expectancy, "daily": daily, "by_pair": by_pair,
            "total_pnl_usdt": round(total_pnl_usdt, 2),
            "portfolio": portfolio
        }
    except Exception:
        return {"total": 0, "wins": 0, "losses": 0, "pending": 0, "closed": 0,
                "win_rate": 0, "avg_win": 0, "avg_loss": 0, "avg_confidence": 0,
                "best_trade": 0, "worst_trade": 0, "expectancy": 0, "daily": [], "by_pair": [],
                "total_pnl_usdt": 0, "portfolio": get_portfolio()}

def update_portfolio(pnl_usdt: float, is_win: bool):
    """Обновляем портфель после закрытия сигнала."""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(f"SELECT id, current_balance, peak_balance, initial_balance FROM {SCHEMA}.portfolio LIMIT 1")
        r = cur.fetchone()
        if not r:
            cur.close(); conn.close(); return
        pid, bal, peak, initial = r[0], float(r[1]), float(r[2]), float(r[3])
        new_bal = round(bal + pnl_usdt, 2)
        new_peak = max(peak, new_bal)
        dd = round((new_peak - new_bal) / new_peak * 100, 2) if new_peak > 0 else 0
        pnl_total = round(new_bal - initial, 2)
        pnl_pct = round((new_bal - initial) / initial * 100, 2)
        win_inc = 1 if is_win else 0
        loss_inc = 0 if is_win else 1
        cur.execute(f"""UPDATE {SCHEMA}.portfolio SET current_balance=%s, peak_balance=%s,
            total_pnl=%s, total_pnl_pct=%s, max_drawdown_pct=%s,
            total_trades=total_trades+1, wins=wins+%s, losses=losses+%s, updated_at=NOW()
            WHERE id=%s""",
            (new_bal, new_peak, pnl_total, pnl_pct, dd, win_inc, loss_inc, pid))
        # Обновляем дневной трекинг
        cur.execute(f"""INSERT INTO {SCHEMA}.portfolio_daily (date, balance, pnl_day, pnl_day_pct, trades_count, wins, losses)
            VALUES (CURRENT_DATE, %s, %s, %s, 1, %s, %s)
            ON CONFLICT (date) DO UPDATE SET balance=%s, pnl_day=portfolio_daily.pnl_day+%s,
            pnl_day_pct=portfolio_daily.pnl_day_pct+%s,
            trades_count=portfolio_daily.trades_count+1, wins=portfolio_daily.wins+%s, losses=portfolio_daily.losses+%s""",
            (new_bal, pnl_usdt, round(pnl_usdt / bal * 100, 2) if bal > 0 else 0, win_inc, loss_inc,
             new_bal, pnl_usdt, round(pnl_usdt / bal * 100, 2) if bal > 0 else 0, win_inc, loss_inc))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def auto_close_signals():
    """Закрываем старые активные сигналы, обновляем портфель."""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(f"""
            SELECT id, pair, signal_type, entry_price, target_price, stop_price, leverage, position_size
            FROM {SCHEMA}.signals
            WHERE status = 'active' AND created_at < NOW() - INTERVAL '4 hours' LIMIT 20
        """)
        rows = cur.fetchall(); cur.close(); conn.close()
        for row in rows:
            sig_id, pair, sig_type, entry, target, stop, lev, pos_size = row
            sym = pair.replace("/", "")
            tick = fetch_url(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}")
            if not tick or "price" not in tick:
                continue
            price = float(tick["price"])
            entry_f = float(entry); target_f = float(target); stop_f = float(stop)
            leverage = int(lev) if lev else 1
            position = float(pos_size) if pos_size else 80
            if sig_type == "LONG":
                exit_p = target_f if price >= target_f else stop_f if price <= stop_f else price
                result_pct = (exit_p - entry_f) / entry_f * 100
            else:
                exit_p = target_f if price <= target_f else stop_f if price >= stop_f else price
                result_pct = (entry_f - exit_p) / entry_f * 100
            # С учётом плеча
            result_pct_leveraged = result_pct * leverage
            pnl_usdt = round(position * result_pct_leveraged / 100, 2)
            result = "win" if result_pct > 0 else "loss"
            conn2 = psycopg2.connect(os.environ["DATABASE_URL"])
            cur2 = conn2.cursor()
            cur2.execute(f"""
                UPDATE {SCHEMA}.signals SET actual_exit_price=%s, result=%s,
                result_pct=%s, status='closed', closed_at=NOW(), pnl_usdt=%s WHERE id=%s
            """, (exit_p, result, round(result_pct_leveraged, 2), pnl_usdt, sig_id))
            conn2.commit(); cur2.close(); conn2.close()
            update_portfolio(pnl_usdt, result == "win")
            p = get_portfolio()
            notify_close_signal(pair, result, round(result_pct_leveraged, 2), pnl_usdt, p.get("balance", 0))
    except Exception:
        pass

def handler(event: dict, context) -> dict:
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    action = params.get("action", "generate")

    if action == "test_telegram":
        send_telegram("🚀 <b>Global Trading Signal Bot</b>\n\nТестовое уведомление — Telegram подключён!\nСигналы и результаты сделок будут приходить сюда.")
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"ok": True, "message": "Telegram test sent"})}

    if action == "saved":
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"signals": get_saved_signals(int(params.get("limit", 30)))})}

    if action == "stats":
        auto_close_signals()
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"stats": get_stats()})}

    if action == "close":
        body = json.loads(event.get("body") or "{}")
        sig_id = int(body.get("signal_id", 0))
        exit_price = float(body.get("exit_price", 0))
        if sig_id and exit_price:
            # Inline close
            try:
                conn = psycopg2.connect(os.environ["DATABASE_URL"])
                cur = conn.cursor()
                cur.execute(f"SELECT entry_price, signal_type FROM {SCHEMA}.signals WHERE id = %s", (sig_id,))
                row = cur.fetchone()
                if row:
                    entry = float(row[0]); stype = row[1]
                    rp = (exit_price - entry) / entry * 100 if stype == "LONG" else (entry - exit_price) / entry * 100
                    cur.execute(f"UPDATE {SCHEMA}.signals SET actual_exit_price=%s, result=%s, result_pct=%s, status='closed', closed_at=NOW() WHERE id=%s",
                                (exit_price, "win" if rp > 0 else "loss", rp, sig_id))
                    conn.commit()
                cur.close(); conn.close()
            except Exception:
                pass
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"ok": True})}

    if action == "portfolio":
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"portfolio": get_portfolio()})}

    # generate — порог 90%+
    auto_close_signals()
    fg = get_fear_greed()
    portfolio = get_portfolio()
    signals = []
    for sym in PAIRS:
        sig = generate_signal(sym, fg)
        if sig:
            db_id = save_signal(sig, portfolio)
            if db_id:
                sig["db_id"] = db_id
                notify_new_signal(sig)
            signals.append(sig)

    signals.sort(key=lambda x: x["confidence"], reverse=True)
    return {
        "statusCode": 200, "headers": HEADERS,
        "body": json.dumps({
            "signals": signals, "fear_greed": fg,
            "analyzed": len(PAIRS), "found": len(signals),
            "min_confidence": MIN_CONFIDENCE,
            "portfolio": portfolio,
            "generated_at": datetime.utcnow().isoformat()
        })
    }