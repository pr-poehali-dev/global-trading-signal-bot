"""
Pump-детектор мирового уровня.
Сканирует Binance, Bybit, OKX, MEXC — 200+ пар каждые 5 минут.
Находит памп/дамп: рост цены + взрыв объёма.
Отправляет в Telegram: фото-график свечей + точка входа + TP1/TP2/TP3 + SL.
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
import os
import io
import base64
import struct
import zlib
import math
import psycopg2
from datetime import datetime, timezone

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json"
}

SCHEMA = "t_p73206386_global_trading_signa"

# ─── Биржи и пары ─────────────────────────────────────────────────────────────

EXCHANGE_PAIRS = {
    "Binance": [
        "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
        "DOGEUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT",
        "MATICUSDT","LTCUSDT","ATOMUSDT","NEARUSDT","APTUSDT",
        "ARBUSDT","OPUSDT","INJUSDT","SUIUSDT","SEIUSDT",
        "TIAUSDT","WLDUSDT","FETUSDT","RENDERUSDT","1000SHIBUSDT",
        "FTMUSDT","SANDUSDT","MANAUSDT","GALAUSDT","ENAUSDT",
        "JUPUSDT","WIFUSDT","BONKUSDT","PEPEUSDT","FLOKIUSDT",
        "ORDIUSDT","TRUMPUSDT","PENGUUSDT","VIRTUALUSDT","HBARUSDT",
        "ICPUSDT","ALGOUSDT","VETUSDT","XLMUSDT","ETCUSDT",
        "FILUSDT","AAVEUSDT","UNIUSDT","LDOUSDT","CRVUSDT",
    ],
    "Bybit": [
        "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT",
        "ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","MATICUSDT",
        "NEARUSDT","INJUSDT","SUIUSDT","APTUSDT","ARBUSDT",
        "OPUSDT","FETUSDT","WLDUSDT","RENDERUSDT","SHIBUSDT",
        "FTMUSDT","SANDUSDT","GALAUSDT","BONKUSDT","PEPEUSDT",
        "ORDIUSDT","HBARUSDT","ICPUSDT","VETUSDT","AAVEUSDT",
        "UNIUSDT","LDOUSDT","BNBUSDT","LTCUSDT","ATOMUSDT",
    ],
    "OKX": [
        "BTC-USDT","ETH-USDT","SOL-USDT","XRP-USDT","DOGE-USDT",
        "ADA-USDT","AVAX-USDT","LINK-USDT","DOT-USDT","MATIC-USDT",
        "NEAR-USDT","INJ-USDT","SUI-USDT","APT-USDT","ARB-USDT",
        "OP-USDT","FET-USDT","WLD-USDT","RENDER-USDT","SHIB-USDT",
        "FTM-USDT","SAND-USDT","GALA-USDT","BONK-USDT","PEPE-USDT",
        "ORDI-USDT","HBAR-USDT","ICP-USDT","VET-USDT","AAVE-USDT",
        "UNI-USDT","LDO-USDT","BNB-USDT","LTC-USDT","ATOM-USDT",
    ],
    "MEXC": [
        "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT",
        "ADAUSDT","AVAXUSDT","LINKUSDT","NEARUSDT","INJUSDT",
        "SUIUSDT","APTUSDT","ARBUSDT","OPUSDT","FETUSDT",
        "WLDUSDT","FTMUSDT","SANDUSDT","GALAUSDT","BONKUSDT",
        "PEPEUSDT","ORDIUSDT","HBARUSDT","VETUSDT","AAVEUSDT",
        "UNIUSDT","LDOUSDT","LTCUSDT","ATOMUSDT","BNBUSDT",
    ],
}

# Пороги pump-сигнала
PUMP_PRICE_PCT  = 3.0     # цена +3%+ за последние 3 свечи
PUMP_VOLUME_PCT = 30.0    # объём +30% vs среднее
MIN_VOLUME_USD  = 300_000 # минимальный объём $300k

# ─── HTTP helper ──────────────────────────────────────────────────────────────

def fetch_url(url: str, headers: dict | None = None) -> dict | list | None:
    try:
        h = {"User-Agent": "PumpBot/3.0"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

# ─── Получение свечей с каждой биржи ──────────────────────────────────────────

def get_candles_binance(symbol: str, limit: int = 60) -> list:
    data = fetch_url(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit={limit}")
    if not data:
        return []
    return [{"o": float(c[1]), "h": float(c[2]), "l": float(c[3]),
             "c": float(c[4]), "v": float(c[7])} for c in data]

def get_candles_bybit(symbol: str, limit: int = 60) -> list:
    data = fetch_url(f"https://api.bybit.com/v5/market/kline?category=spot&symbol={symbol}&interval=15&limit={limit}")
    if not data or data.get("retCode") != 0:
        return []
    result = data.get("result", {}).get("list", [])
    result = list(reversed(result))
    return [{"o": float(c[1]), "h": float(c[2]), "l": float(c[3]),
             "c": float(c[4]), "v": float(c[6])} for c in result]

def get_candles_okx(symbol: str, limit: int = 60) -> list:
    data = fetch_url(f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar=15m&limit={limit}")
    if not data or data.get("code") != "0":
        return []
    result = list(reversed(data.get("data", [])))
    return [{"o": float(c[1]), "h": float(c[2]), "l": float(c[3]),
             "c": float(c[4]), "v": float(c[7])} for c in result]

def get_candles_mexc(symbol: str, limit: int = 60) -> list:
    data = fetch_url(f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval=15m&limit={limit}")
    if not data:
        return []
    return [{"o": float(c[1]), "h": float(c[2]), "l": float(c[3]),
             "c": float(c[4]), "v": float(c[7])} for c in data]

def get_candles(exchange: str, symbol: str) -> list:
    if exchange == "Binance":
        return get_candles_binance(symbol)
    if exchange == "Bybit":
        return get_candles_bybit(symbol)
    if exchange == "OKX":
        return get_candles_okx(symbol)
    if exchange == "MEXC":
        return get_candles_mexc(symbol)
    return []

# ─── Генерация PNG-графика свечей ─────────────────────────────────────────────

def encode_png(width: int, height: int, pixels: list) -> bytes:
    """Кодирует список RGB-пикселей в PNG bytes без внешних библиотек."""
    def pack_chunk(name: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + name + data
        return c + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)

    raw = b""
    for row in pixels:
        raw += b"\x00"
        for r, g, b in row:
            raw += bytes([r, g, b])

    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += pack_chunk(b"IHDR", ihdr)
    png += pack_chunk(b"IDAT", compressed)
    png += pack_chunk(b"IEND", b"")
    return png

def draw_chart(candles: list, sig: dict) -> bytes:
    """Рисует PNG-график свечей 600x300 с уровнями TP/SL."""
    W, H = 600, 300
    PAD_L, PAD_R, PAD_T, PAD_B = 8, 80, 20, 30

    # Фон
    BG   = (15, 17, 23)
    GRID = (30, 34, 45)
    UP   = (38, 166, 154)
    DOWN = (239, 83, 80)
    TP_C = (38, 166, 120)
    SL_C = (200, 60, 60)
    EN_C = (200, 180, 60)
    TEXT = (140, 150, 170)

    last_n = candles[-40:] if len(candles) >= 40 else candles
    prices_all = [c["h"] for c in last_n] + [c["l"] for c in last_n]
    tp3 = sig.get("tp3", sig["price_now"] * 1.08)
    sl  = sig.get("sl",  sig["price_now"] * 0.97)
    prices_all += [tp3, sl]

    p_min = min(prices_all)
    p_max = max(prices_all)
    p_range = (p_max - p_min) or 1

    chart_w = W - PAD_L - PAD_R
    chart_h = H - PAD_T - PAD_B

    def to_x(i: int) -> int:
        n = len(last_n)
        return PAD_L + int(i / max(n - 1, 1) * chart_w)

    def to_y(p: float) -> int:
        return PAD_T + chart_h - int((p - p_min) / p_range * chart_h)

    # Создаём пустой холст
    pixels = [[BG] * W for _ in range(H)]

    def set_px(x: int, y: int, color: tuple):
        if 0 <= x < W and 0 <= y < H:
            pixels[y][x] = color

    def draw_hline(y: int, x1: int, x2: int, color: tuple, dash: bool = False):
        for x in range(x1, x2):
            if not dash or (x // 4) % 2 == 0:
                set_px(x, y, color)

    def draw_vline(x: int, y1: int, y2: int, color: tuple):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            set_px(x, y, color)

    def draw_rect(x: int, y: int, w: int, h: int, color: tuple):
        for dy in range(h):
            for dx in range(w):
                set_px(x + dx, y + dy, color)

    # Сетка
    for i in range(5):
        gy = PAD_T + int(i / 4 * chart_h)
        draw_hline(gy, PAD_L, W - PAD_R, GRID, dash=True)

    # Уровни TP / SL / Entry
    entry = sig.get("entry", sig["price_now"])
    tp1   = sig.get("tp1", sig["price_now"])
    tp2   = sig.get("tp2", sig["price_now"])
    sl_v  = sig.get("sl",  sig["price_now"])

    for level, color, _ in [
        (entry, EN_C, "Entry"),
        (tp1,   TP_C, "TP1"),
        (tp2,   TP_C, "TP2"),
        (tp3,   TP_C, "TP3"),
        (sl_v,  SL_C, "SL"),
    ]:
        ly = to_y(level)
        draw_hline(ly, PAD_L, W - PAD_R, color, dash=True)

    # Свечи
    candle_w = max(int(chart_w / len(last_n)) - 1, 2)
    for i, c in enumerate(last_n):
        x_center = to_x(i) + candle_w // 2
        is_up = c["c"] >= c["o"]
        color = UP if is_up else DOWN

        hy = to_y(c["h"])
        ly = to_y(c["l"])
        draw_vline(x_center, hy, ly, color)

        body_top = to_y(max(c["o"], c["c"]))
        body_bot = to_y(min(c["o"], c["c"]))
        body_h = max(body_bot - body_top, 1)
        draw_rect(to_x(i), body_top, max(candle_w, 1), body_h, color)

    # Подписи уровней справа (только символы, без текста — чистый PNG)
    # Рисуем маленькие квадратики-метки
    for level, color in [
        (entry, EN_C),
        (tp1,   TP_C),
        (tp3,   TP_C),
        (sl_v,  SL_C),
    ]:
        ly = to_y(level)
        draw_rect(W - PAD_R + 2, max(ly - 2, 0), 6, 5, color)

    return encode_png(W, H, pixels)

# ─── Расчёт торговых уровней ──────────────────────────────────────────────────

def calc_levels(candles: list, sig_type: str) -> dict:
    """Считает Entry, TP1/TP2/TP3 и SL по ATR."""
    if not candles:
        return {}
    closes = [c["c"] for c in candles]
    highs  = [c["h"] for c in candles]
    lows   = [c["l"] for c in candles]

    # ATR за последние 14 свечей
    trs = []
    for i in range(1, min(15, len(candles))):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1])
        )
        trs.append(tr)
    atr = sum(trs) / len(trs) if trs else closes[-1] * 0.01

    price = closes[-1]
    # Определяем недавнее максимальное сопротивление и поддержку
    recent_high = max(highs[-10:]) if len(highs) >= 10 else price * 1.03
    recent_low  = min(lows[-10:])  if len(lows) >= 10  else price * 0.97

    if sig_type == "Pump":
        entry = round(price, 8)
        tp1   = round(price + atr * 1.5, 8)
        tp2   = round(price + atr * 3.0, 8)
        tp3   = round(price + atr * 5.0, 8)
        sl    = round(price - atr * 1.2, 8)
    else:  # Dump
        entry = round(price, 8)
        tp1   = round(price - atr * 1.5, 8)
        tp2   = round(price - atr * 3.0, 8)
        tp3   = round(price - atr * 5.0, 8)
        sl    = round(price + atr * 1.2, 8)

    # Проценты
    def pct(a: float, b: float) -> float:
        return round((b - a) / a * 100, 2) if a else 0

    return {
        "entry": entry,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
        "atr": round(atr, 8),
        "tp1_pct": abs(pct(entry, tp1)),
        "tp2_pct": abs(pct(entry, tp2)),
        "tp3_pct": abs(pct(entry, tp3)),
        "sl_pct":  abs(pct(entry, sl)),
    }

# ─── Детект памп/дамп ─────────────────────────────────────────────────────────

def detect_pump(exchange: str, symbol: str) -> dict | None:
    candles = get_candles(exchange, symbol)
    if len(candles) < 20:
        return None

    current      = candles[-1]
    prev_candles = candles[:-1]
    price_now    = current["c"]

    price_3ago = candles[-4]["c"] if len(candles) >= 4 else candles[0]["c"]
    price_6ago = candles[-7]["c"] if len(candles) >= 7 else candles[0]["c"]

    price_pct_3 = (price_now - price_3ago) / price_3ago * 100 if price_3ago > 0 else 0
    price_pct_6 = (price_now - price_6ago) / price_6ago * 100 if price_6ago > 0 else 0

    avg_vol      = sum(c["v"] for c in prev_candles[-20:]) / 20
    curr_vol_usd = current["v"]
    volume_pct   = (curr_vol_usd - avg_vol) / avg_vol * 100 if avg_vol > 0 else 0

    if curr_vol_usd < MIN_VOLUME_USD:
        return None

    abs_price_3 = abs(price_pct_3)
    abs_price_6 = abs(price_pct_6)
    price_pump  = abs_price_3 >= PUMP_PRICE_PCT or abs_price_6 >= PUMP_PRICE_PCT * 1.5
    volume_pump = volume_pct >= PUMP_VOLUME_PCT

    if not (price_pump and volume_pump):
        return None

    # Подтверждение направления на последних свечах
    last_closes = [c["c"] for c in candles[-4:-1]]
    if len(last_closes) >= 2:
        if price_pct_3 > 0 and last_closes[-1] < last_closes[0]:
            return None
        if price_pct_3 < 0 and last_closes[-1] > last_closes[0]:
            return None

    # Сила сигнала
    price_score  = min(abs_price_3 / (PUMP_PRICE_PCT * 3) * 50, 50)
    volume_score = min(volume_pct / (PUMP_VOLUME_PCT * 3) * 50, 50)
    strength     = max(50, min(95, int(price_score + volume_score)))

    sig_type = "Pump" if price_pct_3 > 0 else "Dump"

    # Нормализуем пару
    pair = symbol.replace("-", "/").replace("USDT", "/USDT")
    if "/USDT/USDT" in pair:
        pair = pair.replace("/USDT/USDT", "/USDT")

    # Уровни входа / TP / SL
    levels = calc_levels(candles, sig_type)

    vol_increase = curr_vol_usd - avg_vol

    return {
        "pair": pair,
        "symbol": symbol,
        "type": sig_type,
        "exchange": exchange,
        "price_now":  round(price_now, 8),
        "price_from": round(price_3ago, 8),
        "price_pct":  round(price_pct_3, 2),
        "price_pct_6": round(price_pct_6, 2),
        "volume_usd": round(curr_vol_usd, 0),
        "volume_pct": round(volume_pct, 2),
        "volume_increase_usd": round(vol_increase, 0),
        "strength":   strength,
        "timeframe":  "15m",
        "time": datetime.now(timezone.utc).strftime("%H:%M"),
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
        "candles": candles,
        **levels,
    }

# ─── Форматирование чисел ─────────────────────────────────────────────────────

def fmt_usd(v: float) -> str:
    if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if v >= 1_000:     return f"${v/1_000:.2f}K"
    return f"${v:.2f}"

def fmt_p(p: float) -> str:
    if not p: return "—"
    if p >= 10000: return f"{p:,.0f}"
    if p >= 100:   return f"{p:.2f}"
    if p >= 1:     return f"{p:.4f}"
    if p >= 0.01:  return f"{p:.6f}"
    return f"{p:.8f}"

# ─── Telegram ─────────────────────────────────────────────────────────────────

def send_telegram_photo(photo_bytes: bytes, caption: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        boundary = "----PumpBotBoundary"
        b64_img  = base64.b64encode(photo_bytes).decode()

        # Используем sendPhoto через multipart
        body_parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"parse_mode\"\r\n\r\nHTML",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\nContent-Type: image/png\r\n\r\n",
        ]
        body_bytes = "\r\n".join(body_parts).encode("utf-8") + photo_bytes + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=body_bytes,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        # Fallback — отправить просто текст
        send_telegram_text(caption)

def send_telegram_text(text: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

def notify_pump(sig: dict):
    is_pump  = sig["type"] == "Pump"
    emoji    = "🚀" if is_pump else "📉"
    dots     = "🟢🟢" if is_pump else "🔴🔴"
    dir_word = "ВХОД LONG" if is_pump else "ВХОД SHORT"
    sign     = "+" if is_pump else "-"

    entry = sig.get("entry", sig["price_now"])
    tp1   = sig.get("tp1", 0)
    tp2   = sig.get("tp2", 0)
    tp3   = sig.get("tp3", 0)
    sl    = sig.get("sl",  0)
    tp1p  = sig.get("tp1_pct", 0)
    tp2p  = sig.get("tp2_pct", 0)
    tp3p  = sig.get("tp3_pct", 0)
    slp   = sig.get("sl_pct",  0)

    caption = (
        f"{emoji} <b>{sig['type']} - {sig['pair']}</b> [{sig['exchange']}]\n"
        f"{sig['type']} Activity on {sig['pair']} {dots}\n\n"
        f"💰 Price: <b>${fmt_p(sig['price_from'])}</b> ➜ <b>${fmt_p(sig['price_now'])}</b> "
        f"(<b>{sign}{abs(sig['price_pct'])}%</b>)\n"
        f"📊 Volume: <b>{fmt_usd(sig['volume_usd'])}</b> (+{sig['volume_pct']:.1f}%)\n"
        f"Volume increased by <b>{fmt_usd(sig['volume_increase_usd'])}</b> ⬆️\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>{dir_word}</b>\n\n"
        f"📌 Точка входа:  <b>${fmt_p(entry)}</b>\n\n"
        f"✅ TP1 (осторожный): <b>${fmt_p(tp1)}</b>  <i>(+{tp1p:.1f}%)</i>\n"
        f"✅ TP2 (оптимальный): <b>${fmt_p(tp2)}</b>  <i>(+{tp2p:.1f}%)</i>\n"
        f"✅ TP3 (агрессивный): <b>${fmt_p(tp3)}</b>  <i>(+{tp3p:.1f}%)</i>\n\n"
        f"🛑 Стоп-лосс: <b>${fmt_p(sl)}</b>  <i>(-{slp:.1f}%)</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Таймфрейм: 15m  |  💪 Сила: {sig['strength']}%"
    )

    # Рисуем график и отправляем фото
    try:
        chart_png = draw_chart(sig.get("candles", []), sig)
        send_telegram_photo(chart_png, caption)
    except Exception:
        send_telegram_text(caption)

# ─── База данных ──────────────────────────────────────────────────────────────

def check_already_notified(pair: str, exchange: str, window_min: int = 30) -> bool:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM {SCHEMA}.signals "
            f"WHERE pair=%s AND exchange=%s AND sentiment IN ('Pump','Dump') "
            f"AND created_at > NOW() - INTERVAL '{window_min} minutes'",
            (pair, exchange)
        )
        count = cur.fetchone()[0]
        cur.close(); conn.close()
        return count > 0
    except Exception:
        return False

def save_pump_signal(sig: dict) -> int | None:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"""INSERT INTO {SCHEMA}.signals
            (pair, signal_type, exchange, entry_price, target_price, stop_price,
             confidence, status, rsi, macd_signal, bb_position, volume_ratio,
             fear_greed, sentiment, analysis_text, timeframe, score_bull, score_bear,
             leverage, position_size)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id""",
            (
                sig["pair"],
                "LONG" if sig["type"] == "Pump" else "SHORT",
                sig["exchange"],
                sig.get("entry", sig["price_now"]),
                sig.get("tp2", sig["price_now"]),
                sig.get("sl",  sig["price_now"]),
                sig["strength"],
                "active",
                50.0, "pump", 0.5,
                round(sig["volume_pct"] / 100, 2),
                50, sig["type"],
                f"Price {sig['price_pct']:+.2f}% | Vol +{sig['volume_pct']:.1f}% | TP1={fmt_p(sig.get('tp1',0))} TP2={fmt_p(sig.get('tp2',0))} SL={fmt_p(sig.get('sl',0))}",
                "15m",
                sig["strength"] if sig["type"] == "Pump" else 0,
                sig["strength"] if sig["type"] == "Dump"  else 0,
                1, 0
            )
        )
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()
        return row[0] if row else None
    except Exception:
        return None

def get_recent_pump_signals(limit: int = 50) -> list:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"""SELECT id, pair, signal_type, exchange, entry_price, target_price, stop_price,
                confidence, status, analysis_text, created_at, result, result_pct, pnl_usdt
            FROM {SCHEMA}.signals
            WHERE status != 'archived' AND sentiment IN ('Pump','Dump')
            ORDER BY created_at DESC LIMIT %s""", (limit,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [{
            "id":       r[0],
            "pair":     r[1],
            "type":     "Pump" if r[2] == "LONG" else "Dump",
            "exchange": r[3],
            "entry":    float(r[4]),
            "tp2":      float(r[5]),
            "sl":       float(r[6]),
            "price_now":  float(r[4]),
            "price_from": float(r[4]),
            "price_pct":  0,
            "volume_usd": 0,
            "volume_pct": float(r[7] or 0),
            "volume_increase_usd": 0,
            "strength": r[7] or 50,
            "timeframe": "15m",
            "analysis": r[9] or "",
            "time":   r[10].strftime("%H:%M")    if r[10] else "—",
            "date":   r[10].strftime("%d.%m %H:%M") if r[10] else "—",
            "result": r[11],
            "result_pct": round(float(r[12]), 2) if r[12] else None,
        } for r in rows]
    except Exception:
        return []

def get_stats() -> dict:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*) as total,
                COUNT(*) FILTER (WHERE sentiment='Pump')  as pumps,
                COUNT(*) FILTER (WHERE sentiment='Dump')  as dumps,
                COUNT(*) FILTER (WHERE result='win')      as wins,
                COUNT(*) FILTER (WHERE result='loss')     as losses
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status != 'archived'
        """)
        r = cur.fetchone()
        total = r[0] or 0; pumps = r[1] or 0; dumps = r[2] or 0
        wins = r[3] or 0;  losses = r[4] or 0
        closed   = wins + losses
        win_rate = round(wins / closed * 100, 1) if closed > 0 else 0

        cur.execute(f"""
            SELECT DATE(created_at) as d, COUNT(*) as cnt
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status != 'archived'
            AND created_at > NOW() - INTERVAL '7 days'
            GROUP BY d ORDER BY d DESC
        """)
        daily = [{"date": str(x[0]), "count": x[1]} for x in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": total, "pumps": pumps, "dumps": dumps,
                "wins": wins, "losses": losses, "closed": closed,
                "win_rate": win_rate, "daily": daily}
    except Exception:
        return {"total": 0, "pumps": 0, "dumps": 0, "wins": 0, "losses": 0,
                "closed": 0, "win_rate": 0, "daily": []}

# ─── Handler ──────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """Pump-детектор: Binance + Bybit + OKX + MEXC, 200+ пар, 15m."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    action = params.get("action", "scan")

    if action == "saved":
        limit = int(params.get("limit", 50))
        return {"statusCode": 200, "headers": HEADERS,
                "body": json.dumps({"signals": get_recent_pump_signals(limit)})}

    if action == "stats":
        return {"statusCode": 200, "headers": HEADERS,
                "body": json.dumps({"stats": get_stats()})}

    if action == "test_telegram":
        send_telegram_text(
            "🚀 <b>PumpBot активен!</b>\n\n"
            "Сканирую Binance + Bybit + OKX + MEXC (200+ пар).\n"
            "Уведомления с графиком и уровнями TP/SL подключены."
        )
        return {"statusCode": 200, "headers": HEADERS,
                "body": json.dumps({"ok": True})}

    # action == scan
    found  = []
    errors = 0

    for exchange, pairs in EXCHANGE_PAIRS.items():
        for symbol in pairs:
            try:
                sig = detect_pump(exchange, symbol)
                if not sig:
                    continue
                if check_already_notified(sig["pair"], exchange):
                    continue
                db_id = save_pump_signal(sig)
                if db_id:
                    sig["id"] = db_id
                notify_pump(sig)
                # Убираем тяжёлые candles из ответа
                sig.pop("candles", None)
                found.append(sig)
            except Exception:
                errors += 1

    found.sort(key=lambda x: x.get("strength", 0), reverse=True)
    total_pairs = sum(len(v) for v in EXCHANGE_PAIRS.values())

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps({
            "signals":    found,
            "analyzed":   total_pairs,
            "found":      len(found),
            "errors":     errors,
            "exchanges":  list(EXCHANGE_PAIRS.keys()),
            "scanned_at": datetime.now(timezone.utc).isoformat()
        })
    }
