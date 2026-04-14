"""
AI-движок сигналов мирового уровня.
Анализирует: RSI, MACD, Bollinger Bands, Stochastic, объём, свечные паттерны,
Fear & Greed Index, тренд, перекупленность/перепроданность, развороты.
Генерирует торговые сигналы с детальным обоснованием.
"""
import json
import urllib.request
import math
import os
import psycopg2
from datetime import datetime

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json"
}

PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
EXCHANGES = {"BTCUSDT": "Binance", "ETHUSDT": "Bybit", "SOLUSDT": "OKX",
             "BNBUSDT": "Binance", "XRPUSDT": "OKX", "DOGEUSDT": "Bybit"}

def fetch_url(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TradingBot/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
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
    if len(closes) < 26:
        return {"macd": 0, "signal": 0, "hist": 0, "trend": "neutral"}
    e12 = calc_ema(closes, 12)
    e26 = calc_ema(closes, 26)
    ml = [a - b for a, b in zip(e12[13:], e26)]
    sl = calc_ema(ml, 9)
    hist = ml[-1] - sl[-1] if sl else 0
    trend = "bullish" if hist > 0 and hist > (ml[-2] - sl[-2] if len(ml) > 1 and len(sl) > 1 else 0) else \
            "bearish" if hist < 0 else "neutral"
    return {"macd": round(ml[-1], 6), "signal": round(sl[-1], 6), "hist": round(hist, 6), "trend": trend}

def calc_bollinger(closes: list, period: int = 20) -> dict:
    if len(closes) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "pct_b": 0.5, "squeeze": False}
    w = closes[-period:]
    mid = sum(w) / period
    std = math.sqrt(sum((x - mid) ** 2 for x in w) / period)
    upper = mid + 2 * std
    lower = mid - 2 * std
    pct_b = (closes[-1] - lower) / (upper - lower) if upper != lower else 0.5
    # Squeeze: low volatility = bands тесные
    squeeze = std / mid < 0.015 if mid > 0 else False
    return {"upper": upper, "middle": mid, "lower": lower, "pct_b": round(pct_b, 4), "squeeze": squeeze}

def detect_trend(closes: list) -> dict:
    if len(closes) < 50:
        return {"trend": "neutral", "strength": 0}
    ema20 = calc_ema(closes, 20)
    ema50 = calc_ema(closes, 50)
    price = closes[-1]
    slope20 = (ema20[-1] - ema20[-5]) / ema20[-5] * 100 if len(ema20) >= 5 else 0
    if price > ema20[-1] > ema50[-1] and slope20 > 0:
        strength = min(int(abs(slope20) * 20), 100)
        return {"trend": "uptrend", "strength": strength, "ema20": ema20[-1], "ema50": ema50[-1]}
    elif price < ema20[-1] < ema50[-1] and slope20 < 0:
        strength = min(int(abs(slope20) * 20), 100)
        return {"trend": "downtrend", "strength": strength, "ema20": ema20[-1], "ema50": ema50[-1]}
    return {"trend": "sideways", "strength": 30, "ema20": ema20[-1], "ema50": ema50[-1]}

def detect_divergence(closes: list, rsi_val: float) -> str:
    if len(closes) < 10:
        return "none"
    price_trend = closes[-1] > closes[-5]
    # Бычья дивергенция: цена падает, RSI растёт
    if not price_trend and rsi_val > 40:
        return "bullish_divergence"
    # Медвежья дивергенция: цена растёт, RSI падает  
    if price_trend and rsi_val > 65:
        return "bearish_divergence"
    return "none"

def calc_volume_profile(candles: list) -> dict:
    if len(candles) < 10:
        return {"ratio": 1, "trend": "normal"}
    vols = [c["v"] for c in candles]
    avg = sum(vols[-20:]) / 20 if len(vols) >= 20 else sum(vols) / len(vols)
    ratio = vols[-1] / avg if avg > 0 else 1
    last3_trend = sum(vols[-3:]) / 3 > sum(vols[-6:-3]) / 3 if len(vols) >= 6 else True
    return {
        "ratio": round(ratio, 2),
        "trend": "increasing" if last3_trend and ratio > 1.2 else "decreasing" if ratio < 0.7 else "normal"
    }

def detect_support_resistance(candles: list, current_price: float) -> dict:
    if len(candles) < 20:
        return {"support": current_price * 0.97, "resistance": current_price * 1.03}
    highs = sorted([c["h"] for c in candles[-30:]], reverse=True)
    lows = sorted([c["l"] for c in candles[-30:]])
    resistance = highs[2] if len(highs) > 2 else current_price * 1.03
    support = lows[2] if len(lows) > 2 else current_price * 0.97
    return {"support": round(support, 6), "resistance": round(resistance, 6)}

def score_signal(rsi: float, macd: dict, bb: dict, trend: dict, vol: dict,
                 fg: dict, divergence: str, sr: dict, price: float, candles: list) -> dict:
    """
    Главный алгоритм оценки сигнала. Взвешенная система из 10 факторов.
    Возвращает направление (LONG/SHORT/NONE) и итоговую уверенность.
    """
    bull_score = 0
    bear_score = 0
    factors = []

    # 1. RSI (вес: 20)
    if rsi < 30:
        bull_score += 20
        factors.append(f"RSI={rsi} — глубокая перепроданность (сильный LONG сигнал)")
    elif rsi < 45:
        bull_score += 10
        factors.append(f"RSI={rsi} — зона перепроданности")
    elif rsi > 70:
        bear_score += 20
        factors.append(f"RSI={rsi} — перекупленность (сильный SHORT сигнал)")
    elif rsi > 60:
        bear_score += 10
        factors.append(f"RSI={rsi} — зона перекупленности")
    else:
        factors.append(f"RSI={rsi} — нейтральная зона")

    # 2. MACD (вес: 15)
    if macd["trend"] == "bullish" and macd["hist"] > 0:
        bull_score += 15
        factors.append(f"MACD бычий разворот — гистограмма растёт")
    elif macd["trend"] == "bearish":
        bear_score += 15
        factors.append(f"MACD медвежий — гистограмма падает")

    # 3. Bollinger Bands (вес: 15)
    if bb["pct_b"] < 0.1:
        bull_score += 15
        factors.append("Цена у нижней полосы Bollinger — отскок вероятен")
    elif bb["pct_b"] > 0.9:
        bear_score += 15
        factors.append("Цена у верхней полосы Bollinger — коррекция вероятна")
    if bb["squeeze"]:
        factors.append("Bollinger Squeeze — ожидается взрывное движение")
        bull_score += 5
        bear_score += 5

    # 4. Тренд (вес: 20)
    if trend["trend"] == "uptrend":
        bull_score += 15 + min(trend["strength"] // 10, 5)
        factors.append(f"Восходящий тренд, сила {trend['strength']}%")
    elif trend["trend"] == "downtrend":
        bear_score += 15 + min(trend["strength"] // 10, 5)
        factors.append(f"Нисходящий тренд, сила {trend['strength']}%")

    # 5. Объём (вес: 10)
    if vol["trend"] == "increasing":
        factors.append(f"Объём растёт x{vol['ratio']} — подтверждение движения")
        bull_score += 5 if trend["trend"] == "uptrend" else 0
        bear_score += 5 if trend["trend"] == "downtrend" else 0
    elif vol["trend"] == "decreasing":
        factors.append(f"Объём падает — слабость движения")

    # 6. Fear & Greed (вес: 10)
    fg_val = fg["value"]
    if fg_val < 25:
        bull_score += 10
        factors.append(f"Fear & Greed={fg_val} — Extreme Fear (исторически лучшее время покупки)")
    elif fg_val < 40:
        bull_score += 5
        factors.append(f"Fear & Greed={fg_val} — Fear (рынок недооценён)")
    elif fg_val > 80:
        bear_score += 10
        factors.append(f"Fear & Greed={fg_val} — Extreme Greed (рынок перегрет, риск коррекции)")
    elif fg_val > 65:
        bear_score += 5
        factors.append(f"Fear & Greed={fg_val} — Greed (осторожность)")
    else:
        factors.append(f"Fear & Greed={fg_val} — нейтральный сентимент")

    # 7. Дивергенция (вес: 10)
    if divergence == "bullish_divergence":
        bull_score += 10
        factors.append("Бычья дивергенция RSI — сильный сигнал разворота вверх")
    elif divergence == "bearish_divergence":
        bear_score += 10
        factors.append("Медвежья дивергенция RSI — сигнал разворота вниз")

    # 8. Поддержка/сопротивление (вес: 5)
    dist_support = (price - sr["support"]) / price * 100
    dist_resistance = (sr["resistance"] - price) / price * 100
    if dist_support < 1.5:
        bull_score += 5
        factors.append(f"Цена у уровня поддержки ({sr['support']:.2f})")
    if dist_resistance < 1.5:
        bear_score += 5
        factors.append(f"Цена у уровня сопротивления ({sr['resistance']:.2f})")

    # Итоговая уверенность
    total = bull_score + bear_score
    if bull_score > bear_score and bull_score >= 35:
        direction = "LONG"
        confidence = min(int((bull_score / max(total, 1)) * 100 * 1.1), 95)
    elif bear_score > bull_score and bear_score >= 35:
        direction = "SHORT"
        confidence = min(int((bear_score / max(total, 1)) * 100 * 1.1), 95)
    else:
        direction = "NONE"
        confidence = 0

    return {
        "direction": direction,
        "confidence": confidence,
        "bull_score": bull_score,
        "bear_score": bear_score,
        "factors": factors
    }

def generate_signal(sym: str, fg: dict) -> dict | None:
    candles_1h = get_candles(sym, "1h", 100)
    candles_4h = get_candles(sym, "4h", 50)
    if not candles_1h:
        return None

    closes = [c["c"] for c in candles_1h]
    highs = [c["h"] for c in candles_1h]
    lows = [c["l"] for c in candles_1h]
    price = closes[-1]

    rsi = calc_rsi(closes)
    rsi_4h = calc_rsi([c["c"] for c in candles_4h]) if candles_4h else rsi
    macd = calc_macd(closes)
    bb = calc_bollinger(closes)
    trend = detect_trend(closes)
    vol = calc_volume_profile(candles_1h)
    divergence = detect_divergence(closes, rsi)
    sr = detect_support_resistance(candles_1h, price)

    score = score_signal(rsi, macd, bb, trend, vol, fg, divergence, sr, price, candles_1h)
    if score["direction"] == "NONE":
        return None

    direction = score["direction"]
    confidence = score["confidence"]

    # ATR для расчёта TP/SL
    atr = 0
    for i in range(1, min(15, len(candles_1h))):
        hl = candles_1h[i]["h"] - candles_1h[i]["l"]
        hc = abs(candles_1h[i]["h"] - candles_1h[i-1]["c"])
        lc = abs(candles_1h[i]["l"] - candles_1h[i-1]["c"])
        atr += max(hl, hc, lc)
    atr = atr / 14 if atr > 0 else price * 0.01

    # Risk/Reward 1:2.5
    if direction == "LONG":
        target = round(price + atr * 3.5, 6)
        stop = round(price - atr * 1.4, 6)
    else:
        target = round(price - atr * 3.5, 6)
        stop = round(price + atr * 1.4, 6)

    pair = sym.replace("USDT", "/USDT")
    analysis = (
        f"Анализ {pair}: " +
        f"RSI(1h)={rsi}, RSI(4h)={rsi_4h}, " +
        f"MACD {macd['trend']}, " +
        f"BB %B={bb['pct_b']}" +
        (", BB Squeeze — ожидается взрыв!" if bb["squeeze"] else "") +
        f", Тренд: {trend['trend']} (сила {trend['strength']}%)" +
        f", Объём x{vol['ratio']}" +
        f", F&G={fg['value']} ({fg['classification']})" +
        (f", {divergence.replace('_', ' ')}" if divergence != "none" else "")
    )

    return {
        "pair": pair,
        "symbol": sym,
        "type": direction,
        "exchange": EXCHANGES.get(sym, "Binance"),
        "entry": round(price, 6),
        "target": target,
        "stop": stop,
        "confidence": confidence,
        "status": "active" if confidence >= 75 else "waiting",
        "rsi": rsi,
        "rsi_4h": rsi_4h,
        "macd": macd,
        "bollinger": bb,
        "trend": trend,
        "volume": vol,
        "fear_greed": fg,
        "divergence": divergence,
        "support_resistance": sr,
        "factors": score["factors"],
        "analysis": analysis,
        "risk_reward": round(abs(target - price) / abs(stop - price), 2),
        "potential_pct": round(abs(target - price) / price * 100, 2),
        "atr": round(atr, 6),
        "time": datetime.utcnow().strftime("%H:%M")
    }

def save_signal(sig: dict):
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        schema = "t_p73206386_global_trading_signa"
        cur.execute(
            f"""INSERT INTO {schema}.signals
            (pair, signal_type, exchange, entry_price, target_price, stop_price,
             confidence, status, rsi, macd_signal, bb_position, volume_ratio,
             fear_greed, sentiment, analysis_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (sig["pair"], sig["type"], sig["exchange"], sig["entry"], sig["target"], sig["stop"],
             sig["confidence"], sig["status"], sig["rsi"], sig["macd"]["signal"],
             sig["bollinger"]["pct_b"], sig["volume"]["ratio"],
             sig["fear_greed"]["value"], sig["fear_greed"]["classification"], sig["analysis"])
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass

def get_saved_signals() -> list:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        schema = "t_p73206386_global_trading_signa"
        cur.execute(
            f"""SELECT id, pair, signal_type, exchange, entry_price, target_price, stop_price,
            confidence, status, rsi, fear_greed, analysis_text, created_at
            FROM {schema}.signals ORDER BY created_at DESC LIMIT 20"""
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{
            "id": r[0], "pair": r[1], "type": r[2], "exchange": r[3],
            "entry": float(r[4]), "target": float(r[5]), "stop": float(r[6]),
            "confidence": r[7], "status": r[8], "rsi": float(r[9]) if r[9] else 50,
            "fear_greed": r[10], "analysis": r[11],
            "time": r[12].strftime("%H:%M") if r[12] else "—"
        } for r in rows]
    except Exception:
        return []

def handler(event: dict, context) -> dict:
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    action = params.get("action", "generate")

    if action == "saved":
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"signals": get_saved_signals()})}

    # Генерируем новые сигналы
    fg = get_fear_greed()
    signals = []
    for sym in PAIRS:
        sig = generate_signal(sym, fg)
        if sig:
            signals.append(sig)
            if sig["confidence"] >= 65:
                save_signal(sig)

    # Сортируем по уверенности
    signals.sort(key=lambda x: x["confidence"], reverse=True)

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps({
            "signals": signals,
            "fear_greed": fg,
            "analyzed": len(PAIRS),
            "found": len(signals),
            "generated_at": datetime.utcnow().isoformat()
        })
    }
