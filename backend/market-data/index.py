"""
Реальные рыночные данные с Binance: цены, свечи, объёмы, индикаторы.
"""
import json
import urllib.request
import urllib.error
import math
import os
import psycopg2
from datetime import datetime, timedelta

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json"
}

PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT"]

def fetch_url(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None

def calc_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calc_ema(data: list, period: int) -> list:
    if not data:
        return []
    ema = [data[0]]
    mult = 2 / (period + 1)
    for v in data[1:]:
        ema.append((v - ema[-1]) * mult + ema[-1])
    return ema

def calc_macd(closes: list) -> dict:
    if len(closes) < 26:
        return {"macd": 0, "signal": 0, "histogram": 0}
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12[13:], ema26)]
    signal_line = calc_ema(macd_line, 9)
    hist = macd_line[-1] - signal_line[-1] if signal_line else 0
    return {
        "macd": round(macd_line[-1], 6),
        "signal": round(signal_line[-1], 6),
        "histogram": round(hist, 6)
    }

def calc_bollinger(closes: list, period: int = 20) -> dict:
    if len(closes) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "percent_b": 0.5}
    window = closes[-period:]
    mid = sum(window) / period
    std = math.sqrt(sum((x - mid) ** 2 for x in window) / period)
    upper = mid + 2 * std
    lower = mid - 2 * std
    current = closes[-1]
    percent_b = (current - lower) / (upper - lower) if upper != lower else 0.5
    return {
        "upper": round(upper, 4),
        "middle": round(mid, 4),
        "lower": round(lower, 4),
        "percent_b": round(percent_b, 4)
    }

def calc_stochastic(highs: list, lows: list, closes: list, k_period: int = 14) -> dict:
    if len(closes) < k_period:
        return {"k": 50, "d": 50}
    highest = max(highs[-k_period:])
    lowest = min(lows[-k_period:])
    if highest == lowest:
        return {"k": 50, "d": 50}
    k = ((closes[-1] - lowest) / (highest - lowest)) * 100
    return {"k": round(k, 2), "d": round(k, 2)}

def calc_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0
    trs = []
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        trs.append(max(hl, hc, lc))
    return round(sum(trs[-period:]) / period, 6)

def get_candles(symbol: str, interval: str = "1h", limit: int = 100) -> list:
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    raw = fetch_url(url)
    if not raw:
        return []
    return [{
        "time": int(c[0]),
        "open": float(c[1]),
        "high": float(c[2]),
        "low": float(c[3]),
        "close": float(c[4]),
        "volume": float(c[5])
    } for c in raw]

def get_ticker_24h(symbol: str) -> dict | None:
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
    return fetch_url(url)

def detect_patterns(candles: list) -> list:
    patterns = []
    if len(candles) < 5:
        return patterns
    c = candles
    for i in range(2, len(c)):
        body = abs(c[i]["close"] - c[i]["open"])
        wick_low = min(c[i]["open"], c[i]["close"]) - c[i]["low"]
        wick_high = c[i]["high"] - max(c[i]["open"], c[i]["close"])
        if body > 0 and wick_low > body * 2 and wick_high < body * 0.3:
            patterns.append("Молот (разворот вверх)")
        if body > 0 and wick_high > body * 2 and wick_low < body * 0.3:
            patterns.append("Висельник (разворот вниз)")
        if i >= 2:
            prev_body = abs(c[i-1]["close"] - c[i-1]["open"])
            if (c[i-1]["close"] < c[i-1]["open"] and c[i]["close"] > c[i]["open"] and
                    c[i]["close"] > c[i-1]["open"] and c[i]["open"] < c[i-1]["close"]):
                patterns.append("Бычье поглощение")
            if (c[i-1]["close"] > c[i-1]["open"] and c[i]["close"] < c[i]["open"] and
                    c[i]["open"] > c[i-1]["close"] and c[i]["close"] < c[i-1]["open"]):
                patterns.append("Медвежье поглощение")
    return list(set(patterns[-3:]))

def handler(event: dict, context) -> dict:
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    action = params.get("action", "all")
    symbol = params.get("symbol", "BTCUSDT")
    interval = params.get("interval", "1h")

    if action == "candles":
        candles = get_candles(symbol, interval, 100)
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"candles": candles})}

    if action == "ticker":
        ticker = get_ticker_24h(symbol)
        if not ticker:
            return {"statusCode": 502, "headers": HEADERS, "body": json.dumps({"error": "Binance unavailable"})}
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps(ticker)}

    if action == "indicators":
        candles = get_candles(symbol, interval, 100)
        if not candles:
            return {"statusCode": 502, "headers": HEADERS, "body": json.dumps({"error": "No data"})}
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        volumes = [c["volume"] for c in candles]
        avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1
        vol_ratio = round(volumes[-1] / avg_vol, 2) if avg_vol > 0 else 1
        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({
                "symbol": symbol,
                "rsi": calc_rsi(closes),
                "macd": calc_macd(closes),
                "bollinger": calc_bollinger(closes),
                "stochastic": calc_stochastic(highs, lows, closes),
                "atr": calc_atr(highs, lows, closes),
                "volume_ratio": vol_ratio,
                "patterns": detect_patterns(candles),
                "current_price": closes[-1],
                "price_change_1h": round(((closes[-1] - closes[-2]) / closes[-2]) * 100, 3) if len(closes) > 1 else 0
            })
        }

    # action == "all" — все пары сразу
    all_data = []
    for sym in PAIRS:
        ticker = get_ticker_24h(sym)
        if not ticker:
            continue
        candles = get_candles(sym, "1h", 50)
        closes = [c["close"] for c in candles]
        rsi = calc_rsi(closes) if closes else 50
        pair_name = sym.replace("USDT", "/USDT")
        all_data.append({
            "symbol": pair_name,
            "raw": sym,
            "price": float(ticker.get("lastPrice", 0)),
            "change": float(ticker.get("priceChangePercent", 0)),
            "volume": float(ticker.get("quoteVolume", 0)),
            "high": float(ticker.get("highPrice", 0)),
            "low": float(ticker.get("lowPrice", 0)),
            "rsi": rsi,
            "candles": candles[-30:]
        })

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps({"pairs": all_data, "updated_at": datetime.utcnow().isoformat()})
    }
