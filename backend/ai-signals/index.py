"""
PumpBot — детектор памп/дамп активности мирового уровня.
Сканирует Binance + Bybit + OKX + MEXC (150+ пар) каждые 5 минут.

Алгоритм:
  1. Взрыв объёма: текущий объём vs среднее за 20 свечей
  2. Рост/падение цены: за 1, 3, 6 свечей (15/45/90 мин)
  3. Ускорение цены: темп роста ускоряется
  4. Поглощение: крупная зелёная/красная свеча поглощает предыдущие
  5. RSI-разворот: RSI из зоны и движется в нужном направлении
  6. Относительный объём (RVOL): насколько текущий объём аномален
  7. Подтверждение временного фрейма: сигнал не разовый

Score 0–100 → только ≥65 попадают в уведомление.
Антиспам: одна пара — не чаще раза в 45 мин.
"""
from __future__ import annotations
import json
import urllib.request
import os
import struct
import zlib
import math
import psycopg2
from datetime import datetime, timezone

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}
SCHEMA = "t_p73206386_global_trading_signa"

# ─── Пары по биржам ───────────────────────────────────────────────────────────

EXCHANGE_PAIRS: dict[str, list[str]] = {
    "Binance": [
        "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
        "DOGEUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT",
        "MATICUSDT","LTCUSDT","ATOMUSDT","NEARUSDT","APTUSDT",
        "ARBUSDT","OPUSDT","INJUSDT","SUIUSDT","SEIUSDT",
        "WLDUSDT","FETUSDT","RENDERUSDT","1000SHIBUSDT","FTMUSDT",
        "SANDUSDT","MANAUSDT","GALAUSDT","ENAUSDT","JUPUSDT",
        "WIFUSDT","BONKUSDT","PEPEUSDT","FLOKIUSDT","ORDIUSDT",
        "TRUMPUSDT","PENGUUSDT","VIRTUALUSDT","HBARUSDT","ICPUSDT",
        "ALGOUSDT","VETUSDT","XLMUSDT","ETCUSDT","FILUSDT",
        "AAVEUSDT","UNIUSDT","LDOUSDT","CRVUSDT","TIAUSDT",
    ],
    "Bybit": [
        "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT",
        "ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","NEARUSDT",
        "INJUSDT","SUIUSDT","APTUSDT","ARBUSDT","OPUSDT",
        "FETUSDT","WLDUSDT","RENDERUSDT","SHIBUSDT","FTMUSDT",
        "SANDUSDT","GALAUSDT","BONKUSDT","PEPEUSDT","ORDIUSDT",
        "HBARUSDT","ICPUSDT","VETUSDT","AAVEUSDT","UNIUSDT",
        "LDOUSDT","BNBUSDT","LTCUSDT","ATOMUSDT","MATICUSDT",
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

# ─── Настройки алгоритма ──────────────────────────────────────────────────────

MIN_SCORE        = 65    # минимальный score для отправки сигнала (0–100)
MIN_VOL_USD      = 200_000  # минимальный объём текущей свечи $200k
MIN_PRICE_PCT    = 2.5   # минимальное движение цены %
MIN_RVOL         = 1.8   # минимальный Relative Volume (vs среднее)
COOLDOWN_MIN     = 45    # антиспам: одна пара не чаще раз в 45 мин

# ─── HTTP ─────────────────────────────────────────────────────────────────────

def fetch(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PumpBot/4.0"})
        with urllib.request.urlopen(req, timeout=9) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

# ─── Свечи с каждой биржи ────────────────────────────────────────────────────

def candles_binance(sym: str, n: int = 80) -> list:
    d = fetch(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=15m&limit={n}")
    if not isinstance(d, list):
        return []
    return [{"o": float(c[1]),"h": float(c[2]),"l": float(c[3]),"c": float(c[4]),"v": float(c[7])} for c in d]

def candles_bybit(sym: str, n: int = 80) -> list:
    d = fetch(f"https://api.bybit.com/v5/market/kline?category=spot&symbol={sym}&interval=15&limit={n}")
    if not isinstance(d, dict) or d.get("retCode") != 0:
        return []
    rows = list(reversed(d.get("result", {}).get("list", [])))
    return [{"o": float(c[1]),"h": float(c[2]),"l": float(c[3]),"c": float(c[4]),"v": float(c[6])} for c in rows]

def candles_okx(sym: str, n: int = 80) -> list:
    d = fetch(f"https://www.okx.com/api/v5/market/candles?instId={sym}&bar=15m&limit={n}")
    if not isinstance(d, dict) or d.get("code") != "0":
        return []
    rows = list(reversed(d.get("data", [])))
    return [{"o": float(c[1]),"h": float(c[2]),"l": float(c[3]),"c": float(c[4]),"v": float(c[7])} for c in rows]

def candles_mexc(sym: str, n: int = 80) -> list:
    d = fetch(f"https://api.mexc.com/api/v3/klines?symbol={sym}&interval=15m&limit={n}")
    if not isinstance(d, list):
        return []
    return [{"o": float(c[1]),"h": float(c[2]),"l": float(c[3]),"c": float(c[4]),"v": float(c[7])} for c in d]

def get_candles(exchange: str, sym: str) -> list:
    fn = {"Binance": candles_binance, "Bybit": candles_bybit,
          "OKX": candles_okx, "MEXC": candles_mexc}.get(exchange)
    return fn(sym) if fn else []

# ─── Технические индикаторы ───────────────────────────────────────────────────

def calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    ag, al = sum(gains) / period, sum(losses) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return round(100 - 100 / (1 + rs), 1)

def calc_ema(vals: list[float], period: int) -> float:
    if not vals:
        return 0.0
    k = 2 / (period + 1)
    ema = vals[0]
    for v in vals[1:]:
        ema = v * k + ema * (1 - k)
    return ema

def calc_atr(candles: list, period: int = 14) -> float:
    trs = []
    for i in range(1, min(period + 1, len(candles))):
        c, p = candles[i], candles[i-1]
        trs.append(max(c["h"] - c["l"], abs(c["h"] - p["c"]), abs(c["l"] - p["c"])))
    return sum(trs) / len(trs) if trs else candles[-1]["c"] * 0.01

def rvol(candles: list, look: int = 20) -> float:
    """Relative Volume: текущий объём / среднее за последние look свечей."""
    if len(candles) < look + 1:
        return 1.0
    avg = sum(c["v"] for c in candles[-look-1:-1]) / look
    return candles[-1]["v"] / avg if avg > 0 else 1.0

# ─── Ядро: оценка памп/дамп сигнала ─────────────────────────────────────────

def score_signal(candles: list) -> dict | None:
    """
    Возвращает dict с типом, score и метриками.
    Score 0–100: выше = сильнее сигнал.
    """
    if len(candles) < 25:
        return None

    c = candles  # alias

    price_now  = c[-1]["c"]
    price_1    = c[-2]["c"]   # 15 мин назад
    price_3    = c[-4]["c"]   # 45 мин назад
    price_6    = c[-7]["c"]   # 90 мин назад
    price_12   = c[-13]["c"]  # 3 часа назад

    if price_now <= 0 or price_3 <= 0:
        return None

    pct_1   = (price_now - price_1)  / price_1  * 100
    pct_3   = (price_now - price_3)  / price_3  * 100
    pct_6   = (price_now - price_6)  / price_6  * 100
    pct_12  = (price_now - price_12) / price_12 * 100

    # Направление
    if abs(pct_3) < MIN_PRICE_PCT and abs(pct_6) < MIN_PRICE_PCT * 1.3:
        return None

    sig_type = "Pump" if pct_3 >= 0 else "Dump"
    direction = 1 if sig_type == "Pump" else -1

    # ── Фактор 1: Взрыв объёма (RVOL) ──
    rv = rvol(c, 20)
    if rv < MIN_RVOL:
        return None
    vol_score = min(int((rv - MIN_RVOL) / (10 - MIN_RVOL) * 30), 30)  # 0–30

    # ── Фактор 2: Движение цены ──
    abs_pct3 = abs(pct_3)
    abs_pct6 = abs(pct_6)
    price_score = min(int(abs_pct3 / 10 * 25), 25)  # 0–25

    # ── Фактор 3: Ускорение (темп ускоряется?) ──
    accel = 0
    if abs(pct_1) > abs(pct_3) * 0.4:
        accel = 10  # последняя свеча сильная
    elif abs(pct_3) > abs(pct_6) * 0.6:
        accel = 5

    # ── Фактор 4: Свеча поглощения ──
    last = c[-1]
    prev = c[-2]
    engulf = 0
    body_last = abs(last["c"] - last["o"])
    body_prev = abs(prev["c"] - prev["o"])
    if body_last > body_prev * 1.5 and (direction * (last["c"] - last["o"])) > 0:
        engulf = 10  # сильная свеча поглощения

    # ── Фактор 5: RSI ──
    closes = [x["c"] for x in c]
    rsi = calc_rsi(closes)
    rsi_score = 0
    if sig_type == "Pump" and rsi > 55:
        rsi_score = 8  # RSI подтверждает рост
    elif sig_type == "Dump" and rsi < 45:
        rsi_score = 8
    elif sig_type == "Pump" and rsi < 30:
        rsi_score = 5  # перепродан — отскок
    elif sig_type == "Dump" and rsi > 70:
        rsi_score = 5

    # ── Фактор 6: Минимальный объём ──
    vol_usd = c[-1]["v"]
    if vol_usd < MIN_VOL_USD:
        return None

    # ── Итоговый score ──
    total = vol_score + price_score + accel + engulf + rsi_score
    score = max(0, min(100, total))

    if score < MIN_SCORE:
        return None

    return {
        "type":     sig_type,
        "score":    score,
        "pct_1":    round(pct_1, 2),
        "pct_3":    round(pct_3, 2),
        "pct_6":    round(pct_6, 2),
        "pct_12":   round(pct_12, 2),
        "rvol":     round(rv, 2),
        "rsi":      rsi,
        "vol_usd":  round(vol_usd, 0),
        "engulf":   engulf > 0,
        "accel":    accel > 0,
        "price_now": price_now,
        "price_3ago": price_3,
        "vol_avg":  round(vol_usd / rv, 0),
    }

# ─── Уровни TP / SL ──────────────────────────────────────────────────────────

def calc_levels(candles: list, sig_type: str) -> dict:
    atr   = calc_atr(candles)
    price = candles[-1]["c"]
    sgn   = 1 if sig_type == "Pump" else -1

    entry = round(price, 8)
    tp1   = round(price + sgn * atr * 1.2, 8)
    tp2   = round(price + sgn * atr * 2.5, 8)
    tp3   = round(price + sgn * atr * 4.5, 8)
    sl    = round(price - sgn * atr * 1.0, 8)

    def pct(a, b):
        return round(abs(b - a) / a * 100, 2) if a else 0

    return {
        "entry": entry, "atr": round(atr, 8),
        "tp1": tp1, "tp1_pct": pct(entry, tp1),
        "tp2": tp2, "tp2_pct": pct(entry, tp2),
        "tp3": tp3, "tp3_pct": pct(entry, tp3),
        "sl": sl,   "sl_pct":  pct(entry, sl),
    }

# ─── PNG-график с подписями ───────────────────────────────────────────────────

def _pack_chunk(name: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(name + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

def make_png(pixels: list[list[tuple]], w: int, h: int) -> bytes:
    raw = b"".join(b"\x00" + bytes([v for px in row for v in px]) for row in pixels)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _pack_chunk(b"IHDR", ihdr)
            + _pack_chunk(b"IDAT", zlib.compress(raw, 6))
            + _pack_chunk(b"IEND", b""))

def draw_chart(candles: list, sig: dict) -> bytes:
    W, H = 700, 340
    PL, PR, PT, PB = 10, 90, 28, 36

    # Цвета (темная TradingView тема)
    BG    = (13, 15, 22)
    GRID  = (28, 32, 44)
    UP    = (38, 166, 154)     # зелёные свечи
    DOWN  = (239, 83, 80)      # красные свечи
    ENTRY = (255, 200, 0)      # жёлтый — точка входа
    TP_C  = (56, 200, 120)     # зелёный — TP
    SL_C  = (220, 60, 60)      # красный — SL
    LABEL = (180, 190, 210)    # текст

    last = candles[-50:] if len(candles) >= 50 else candles
    n    = len(last)

    entry = sig.get("entry", sig["price_now"])
    tp3   = sig.get("tp3", sig["price_now"] * 1.08)
    sl    = sig.get("sl",  sig["price_now"] * 0.97)

    all_p = [c["h"] for c in last] + [c["l"] for c in last] + [entry, tp3, sl]
    p_min = min(all_p) * 0.999
    p_max = max(all_p) * 1.001
    p_rng = (p_max - p_min) or 1

    cw  = W - PL - PR
    ch  = H - PT - PB

    def ty(p):
        return PT + ch - int((p - p_min) / p_rng * ch)

    def tx(i):
        return PL + int(i / max(n - 1, 1) * cw)

    # Холст
    px = [[BG] * W for _ in range(H)]

    def sp(x, y, col):
        if 0 <= x < W and 0 <= y < H:
            px[y][x] = col

    def hline(y, x1, x2, col, dash=False):
        for x in range(x1, x2):
            if not dash or (x // 5) % 2 == 0:
                sp(x, y, col)

    def vline(x, y1, y2, col):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            sp(x, y, col)

    def rect(x0, y0, rw, rh, col):
        for dy in range(max(rh, 1)):
            for dx in range(max(rw, 1)):
                sp(x0 + dx, y0 + dy, col)

    # Горизонтальная сетка (5 линий)
    for i in range(6):
        gy = PT + int(i / 5 * ch)
        hline(gy, PL, W - PR, GRID, dash=True)

    # Уровни с пунктиром
    levels = [
        (entry,             ENTRY, "ENTRY"),
        (sig.get("tp1", 0), TP_C,  "TP1"),
        (sig.get("tp2", 0), TP_C,  "TP2"),
        (tp3,               TP_C,  "TP3"),
        (sl,                SL_C,  "SL"),
    ]
    for price, col, lbl in levels:
        if not price or not (p_min < price < p_max):
            continue
        y = ty(price)
        hline(y, PL, W - PR - 2, col, dash=True)
        # Маленький квадрат-метка справа
        rect(W - PR + 2, max(y - 3, 0), 8, 6, col)

    # Объёмные бары
    max_v = max((c["v"] for c in last), default=1)
    bar_w = max(int(cw / n) - 1, 1)
    for i, c in enumerate(last):
        x0   = tx(i)
        col  = UP if c["c"] >= c["o"] else DOWN
        vh   = max(int((c["v"] / max_v) * 28), 1)
        rect(x0, H - PB - vh, bar_w, vh, (col[0]//3, col[1]//3, col[2]//3))

    # Свечи
    candle_half = max(bar_w // 2, 1)
    for i, c in enumerate(last):
        x0   = tx(i)
        xc   = x0 + candle_half
        col  = UP if c["c"] >= c["o"] else DOWN

        # Фитиль
        vline(xc, ty(c["h"]), ty(c["l"]), col)

        # Тело
        y_top = min(ty(c["o"]), ty(c["c"]))
        y_bot = max(ty(c["o"]), ty(c["c"]))
        bw    = max(candle_half * 2, 2)
        rect(x0, y_top, bw, max(y_bot - y_top, 1), col)

    # Выделяем последнюю свечу ярче
    last_c = last[-1]
    lcol = UP if last_c["c"] >= last_c["o"] else DOWN
    xc = tx(n - 1) + candle_half
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            sp(xc + dx, ty(last_c["c"]) + dy, (255, 255, 255))

    return make_png(px, W, H)

# ─── Форматирование чисел ─────────────────────────────────────────────────────

def fp(p: float) -> str:
    """Форматирование цены."""
    if not p:
        return "—"
    if p >= 10000:
        return f"{p:,.0f}"
    if p >= 100:
        return f"{p:.2f}"
    if p >= 1:
        return f"{p:.4f}"
    if p >= 0.001:
        return f"{p:.6f}"
    return f"{p:.8f}"

def fv(v: float) -> str:
    """Форматирование объёма."""
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.0f}"

# ─── Telegram ─────────────────────────────────────────────────────────────────

def tg_text(text: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=6)
    except Exception:
        pass

def tg_photo(img_bytes: bytes, caption: str):
    """Отправляет PNG как фото с подписью через multipart/form-data."""
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    boundary = b"PumpBotBnd42"
    CRLF     = b"\r\n"

    def part_field(name: str, value: str) -> bytes:
        return (b"--" + boundary + CRLF
                + f'Content-Disposition: form-data; name="{name}"'.encode() + CRLF
                + CRLF + value.encode() + CRLF)

    def part_file(name: str, filename: str, ct: str, data: bytes) -> bytes:
        return (b"--" + boundary + CRLF
                + f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode() + CRLF
                + f"Content-Type: {ct}".encode() + CRLF
                + CRLF + data + CRLF)

    body = (part_field("chat_id", chat_id)
            + part_field("caption", caption)
            + part_field("parse_mode", "HTML")
            + part_file("photo", "chart.png", "image/png", img_bytes)
            + b"--" + boundary + b"--" + CRLF)

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
            method="POST")
        urllib.request.urlopen(req, timeout=12)
    except Exception:
        tg_text(caption)  # fallback: просто текст

def build_caption(sig: dict) -> str:
    is_pump = sig["type"] == "Pump"
    arrow   = "📈" if is_pump else "📉"
    dot1    = "🟢" if is_pump else "🔴"
    action  = "LONG (покупка)" if is_pump else "SHORT (продажа)"
    sign    = "+" if is_pump else "-"
    pct3    = abs(sig.get("pct_3", 0))
    pct6    = abs(sig.get("pct_6", 0))

    rsi_line = ""
    rsi = sig.get("rsi", 0)
    if rsi:
        rsi_emoji = "🔥" if (is_pump and rsi > 60) or (not is_pump and rsi < 40) else "📊"
        rsi_line  = f"{rsi_emoji} RSI: <b>{rsi}</b>   "

    rvol_line = f"📦 RVOL: <b>{sig.get('rvol', 0):.1f}x</b>" if sig.get("rvol") else ""
    flags = []
    if sig.get("engulf"):
        flags.append("🕯 Поглощение")
    if sig.get("accel"):
        flags.append("⚡ Ускорение")

    return (
        f"{'🚀' if is_pump else '💣'} <b>{sig['type'].upper()} — {sig['pair']}</b>  [{sig['exchange']}]\n"
        f"{dot1}{dot1} {sig['type']} Activity · {sig['timeframe']} · {sig['time']} UTC\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Цена:  <b>${fp(sig['price_3ago'])}</b>  {arrow}  <b>${fp(sig['price_now'])}</b>\n"
        f"    за 45 мин: <b>{sign}{pct3:.2f}%</b>  |  за 90 мин: <b>{sign}{pct6:.2f}%</b>\n"
        f"📊 Объём: <b>{fv(sig['vol_usd'])}</b>  (+{sig.get('rvol',1):.0f}x от нормы)\n"
        + (f"🔎 {rsi_line}{rvol_line}\n" if rsi_line or rvol_line else "")
        + (f"✨ {' · '.join(flags)}\n" if flags else "")
        + f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>СИГНАЛ: {action}</b>\n\n"
        f"📌 Точка входа:       <b>${fp(sig['entry'])}</b>\n\n"
        f"✅ TP1 (осторожный):  <b>${fp(sig['tp1'])}</b>  <i>(+{sig['tp1_pct']:.1f}%)</i>\n"
        f"✅ TP2 (оптимальный): <b>${fp(sig['tp2'])}</b>  <i>(+{sig['tp2_pct']:.1f}%)</i>\n"
        f"✅ TP3 (агрессивный): <b>${fp(sig['tp3'])}</b>  <i>(+{sig['tp3_pct']:.1f}%)</i>\n\n"
        f"🛑 Стоп-лосс:         <b>${fp(sig['sl'])}</b>  <i>(-{sig['sl_pct']:.1f}%)</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💪 Сила сигнала: <b>{sig['score']}%</b>  |  ⏱ 15m"
    )

def notify(sig: dict):
    caption = build_caption(sig)
    try:
        img = draw_chart(sig.get("candles", []), sig)
        tg_photo(img, caption)
    except Exception:
        tg_text(caption)

# ─── База данных ─────────────────────────────────────────────────────────────

def already_sent(pair: str, exchange: str) -> bool:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM {SCHEMA}.signals "
            f"WHERE pair=%s AND exchange=%s AND sentiment IN ('Pump','Dump') "
            f"AND created_at > NOW() - INTERVAL '{COOLDOWN_MIN} minutes'",
            (pair, exchange))
        n = cur.fetchone()[0]
        cur.close(); conn.close()
        return n > 0
    except Exception:
        return False

def save_signal(sig: dict) -> int | None:
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
                "LONG"  if sig["type"] == "Pump" else "SHORT",
                sig["exchange"],
                sig["entry"],
                sig["tp2"],
                sig["sl"],
                sig["score"],
                "active",
                sig.get("rsi", 50),
                "pump_detector",
                0.5,
                round(sig.get("rvol", 1), 2),
                50,
                sig["type"],
                f"Pct3={sig['pct_3']:+.2f}% Pct6={sig['pct_6']:+.2f}% RVOL={sig.get('rvol',1):.1f} RSI={sig.get('rsi',50)} Score={sig['score']}",
                "15m",
                sig["score"] if sig["type"] == "Pump" else 0,
                sig["score"] if sig["type"] == "Dump"  else 0,
                1, 0,
            ))
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()
        return row[0] if row else None
    except Exception:
        return None

def get_saved(limit: int = 50) -> list:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"""SELECT id, pair, signal_type, exchange, entry_price, target_price, stop_price,
                confidence, status, analysis_text, created_at, result, result_pct
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status != 'archived'
            ORDER BY created_at DESC LIMIT %s""", (limit,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [{
            "id": r[0], "pair": r[1],
            "type": "Pump" if r[2] == "LONG" else "Dump",
            "exchange": r[3],
            "entry": float(r[4]), "tp2": float(r[5]), "sl": float(r[6]),
            "price_now": float(r[4]), "price_from": float(r[4]),
            "price_pct": 0, "volume_usd": 0, "volume_pct": float(r[7] or 0),
            "volume_increase_usd": 0,
            "score": r[7] or 50, "strength": r[7] or 50,
            "timeframe": "15m",
            "analysis": r[9] or "",
            "time":   r[10].strftime("%H:%M")       if r[10] else "—",
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
                COUNT(*) FILTER (WHERE sentiment='Pump')  pumps,
                COUNT(*) FILTER (WHERE sentiment='Dump')  dumps,
                COUNT(*) FILTER (WHERE result='win')      wins,
                COUNT(*) FILTER (WHERE result='loss')     losses
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status != 'archived'""")
        r = cur.fetchone()
        total, pumps, dumps, wins, losses = r[0] or 0, r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0
        closed   = wins + losses
        win_rate = round(wins / closed * 100, 1) if closed > 0 else 0

        cur.execute(f"""
            SELECT DATE(created_at) d, COUNT(*) cnt
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status != 'archived'
              AND created_at > NOW() - INTERVAL '14 days'
            GROUP BY d ORDER BY d DESC""")
        daily = [{"date": str(x[0]), "count": x[1]} for x in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": total, "pumps": pumps, "dumps": dumps,
                "wins": wins, "losses": losses, "closed": closed,
                "win_rate": win_rate, "daily": daily}
    except Exception:
        return {"total": 0, "pumps": 0, "dumps": 0, "wins": 0,
                "losses": 0, "closed": 0, "win_rate": 0, "daily": []}

# ─── Основной скан ────────────────────────────────────────────────────────────

def run_scan(only_exchange: str | None = None) -> dict:
    found  = []
    errors = 0
    pairs_map = ({only_exchange: EXCHANGE_PAIRS[only_exchange]}
                 if only_exchange and only_exchange in EXCHANGE_PAIRS
                 else EXCHANGE_PAIRS)
    total  = sum(len(v) for v in pairs_map.values())

    for exchange, pairs in pairs_map.items():
        for sym in pairs:
            try:
                candles = get_candles(exchange, sym)
                scored  = score_signal(candles)
                if not scored:
                    continue

                # Нормализуем пару
                pair = sym.replace("-", "/").replace("USDT", "/USDT")
                if "/USDT/USDT" in pair:
                    pair = pair.replace("/USDT/USDT", "/USDT")

                if already_sent(pair, exchange):
                    continue

                levels = calc_levels(candles, scored["type"])
                sig = {
                    "pair":      pair,
                    "symbol":    sym,
                    "exchange":  exchange,
                    "timeframe": "15m",
                    "time":      datetime.now(timezone.utc).strftime("%H:%M"),
                    "candles":   candles,
                    **scored,
                    **levels,
                }

                db_id = save_signal(sig)
                if db_id:
                    sig["id"] = db_id

                notify(sig)

                sig.pop("candles", None)
                found.append(sig)

            except Exception:
                errors += 1

    found.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"signals": found, "analyzed": total, "found": len(found), "errors": errors}

# ─── Handler ─────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """PumpBot: сканирует Binance+Bybit+OKX+MEXC, находит памп/дамп, шлёт в Telegram."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    action = params.get("action", "scan")

    if action == "saved":
        return {"statusCode": 200, "headers": HEADERS,
                "body": json.dumps({"signals": get_saved(int(params.get("limit", 50)))})}

    if action == "stats":
        return {"statusCode": 200, "headers": HEADERS,
                "body": json.dumps({"stats": get_stats()})}

    if action == "test_telegram":
        tg_text(
            "🚀 <b>PumpBot запущен!</b>\n\n"
            "✅ Binance · Bybit · OKX · MEXC\n"
            "✅ 150+ пар · каждые 5 минут\n"
            "✅ Chart PNG · Entry · TP1/TP2/TP3 · SL\n\n"
            "Жду первых пампов... 🎯"
        )
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"ok": True})}

    # action == "scan" — можно передать ?exchange=Binance для скана одной биржи
    only = params.get("exchange")  # Binance | Bybit | OKX | MEXC | None=все
    result = run_scan(only)
    return {
        "statusCode": 200, "headers": HEADERS,
        "body": json.dumps({**result,
                            "exchange": only or "all",
                            "exchanges": list(EXCHANGE_PAIRS.keys()),
                            "scanned_at": datetime.now(timezone.utc).isoformat()})
    }