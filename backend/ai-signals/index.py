"""
PumpBot v3 — детектор памп/дамп мирового уровня.
Binance + Bybit + OKX + MEXC · 150+ пар · каждые 5 минут.

Алгоритм (7 факторов → Score 0–100):
  1. RVOL  — аномальный объём vs среднее 20 свечей
  2. Price — движение цены за 15/45/90 мин
  3. Accel — ускорение: темп нарастает
  4. Engulf — свеча поглощения (тело 1.5x больше)
  5. RSI   — подтверждение направления
  6. EMA   — цена выше/ниже EMA20
  7. Trend — совпадение с трендом 1h

Score → Плечо:
  65–69  → 2x  (позиция 3% от $1000 = $30)
  70–74  → 3x  (позиция 5% = $50)
  75–79  → 5x  (позиция 7% = $70)
  80–84  → 7x  (позиция 8% = $80)
  85–89  → 10x (позиция 10% = $100)
  90+    → 15x (позиция 12% = $120)

Антиспам: одна пара не чаще раза в 45 мин.
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
SCHEMA  = "t_p73206386_global_trading_signa"
BALANCE = 1000.0  # стартовый банк

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

# Пороги
MIN_SCORE     = 65
MIN_VOL_USD   = 200_000
MIN_PRICE_PCT = 2.5
MIN_RVOL      = 1.8
COOLDOWN_MIN  = 45

# Плечо и размер позиции по score
LEVERAGE_MAP = [
    (90, 15, 0.12),
    (85, 10, 0.10),
    (80,  7, 0.08),
    (75,  5, 0.07),
    (70,  3, 0.05),
    (65,  2, 0.03),
]

def get_leverage(score: int) -> tuple[int, float]:
    for threshold, lev, pct in LEVERAGE_MAP:
        if score >= threshold:
            return lev, pct
    return 2, 0.03

# ─── HTTP ─────────────────────────────────────────────────────────────────────

def fetch(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PumpBot/4.0"})
        with urllib.request.urlopen(req, timeout=9) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

# ─── Свечи ────────────────────────────────────────────────────────────────────

def candles_binance(sym: str, n: int = 80) -> list:
    d = fetch(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=15m&limit={n}")
    if not isinstance(d, list): return []
    return [{"o":float(c[1]),"h":float(c[2]),"l":float(c[3]),"c":float(c[4]),"v":float(c[7])} for c in d]

def candles_bybit(sym: str, n: int = 80) -> list:
    d = fetch(f"https://api.bybit.com/v5/market/kline?category=spot&symbol={sym}&interval=15&limit={n}")
    if not isinstance(d, dict) or d.get("retCode") != 0: return []
    rows = list(reversed(d.get("result", {}).get("list", [])))
    return [{"o":float(c[1]),"h":float(c[2]),"l":float(c[3]),"c":float(c[4]),"v":float(c[6])} for c in rows]

def candles_okx(sym: str, n: int = 80) -> list:
    d = fetch(f"https://www.okx.com/api/v5/market/candles?instId={sym}&bar=15m&limit={n}")
    if not isinstance(d, dict) or d.get("code") != "0": return []
    rows = list(reversed(d.get("data", [])))
    return [{"o":float(c[1]),"h":float(c[2]),"l":float(c[3]),"c":float(c[4]),"v":float(c[7])} for c in rows]

def candles_mexc(sym: str, n: int = 80) -> list:
    d = fetch(f"https://api.mexc.com/api/v3/klines?symbol={sym}&interval=15m&limit={n}")
    if not isinstance(d, list): return []
    return [{"o":float(c[1]),"h":float(c[2]),"l":float(c[3]),"c":float(c[4]),"v":float(c[7])} for c in d]

def get_candles(exchange: str, sym: str) -> list:
    fn = {"Binance": candles_binance, "Bybit": candles_bybit,
          "OKX": candles_okx, "MEXC": candles_mexc}.get(exchange)
    return fn(sym) if fn else []

# ─── Технические индикаторы ───────────────────────────────────────────────────

def calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1: return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    ag, al = sum(gains)/period, sum(losses)/period
    if al == 0: return 100.0
    return round(100 - 100/(1 + ag/al), 1)

def calc_ema(vals: list[float], period: int) -> float:
    if not vals: return 0.0
    k, ema = 2/(period+1), vals[0]
    for v in vals[1:]: ema = v*k + ema*(1-k)
    return ema

def calc_atr(candles: list, period: int = 14) -> float:
    trs = []
    for i in range(1, min(period+1, len(candles))):
        c, p = candles[i], candles[i-1]
        trs.append(max(c["h"]-c["l"], abs(c["h"]-p["c"]), abs(c["l"]-p["c"])))
    return sum(trs)/len(trs) if trs else candles[-1]["c"]*0.01

def calc_rvol(candles: list, look: int = 20) -> float:
    if len(candles) < look+1: return 1.0
    avg = sum(c["v"] for c in candles[-look-1:-1])/look
    return round(candles[-1]["v"]/avg, 2) if avg > 0 else 1.0

# ─── Ядро: многофакторный scoring ────────────────────────────────────────────

def score_signal(candles: list) -> dict | None:
    if len(candles) < 25: return None

    c          = candles
    price_now  = c[-1]["c"]
    price_1    = c[-2]["c"]
    price_3    = c[-4]["c"]
    price_6    = c[-7]["c"]
    price_12   = c[-13]["c"]

    if price_now <= 0 or price_3 <= 0: return None

    pct_1  = (price_now - price_1)  / price_1  * 100
    pct_3  = (price_now - price_3)  / price_3  * 100
    pct_6  = (price_now - price_6)  / price_6  * 100
    pct_12 = (price_now - price_12) / price_12 * 100

    if abs(pct_3) < MIN_PRICE_PCT and abs(pct_6) < MIN_PRICE_PCT * 1.3:
        return None

    sig_type  = "Pump" if pct_3 >= 0 else "Dump"
    direction = 1 if sig_type == "Pump" else -1
    factors   = []  # список сработавших факторов

    # ── F1: RVOL ──────────────────────────────────────────────────────────────
    rv = calc_rvol(c, 20)
    if rv < MIN_RVOL: return None
    if rv >= 5.0:
        vol_sc = 30; factors.append(f"💥 RVOL {rv:.1f}x — экстремальный объём")
    elif rv >= 3.0:
        vol_sc = 22; factors.append(f"📊 RVOL {rv:.1f}x — сильный объём")
    else:
        vol_sc = 12; factors.append(f"📊 RVOL {rv:.1f}x — повышенный объём")

    # ── F2: Движение цены ─────────────────────────────────────────────────────
    abs3 = abs(pct_3); abs6 = abs(pct_6)
    if abs3 >= 8:
        price_sc = 25; factors.append(f"🚀 Цена {pct_3:+.2f}% за 45 мин — сильный импульс")
    elif abs3 >= 5:
        price_sc = 18; factors.append(f"📈 Цена {pct_3:+.2f}% за 45 мин")
    else:
        price_sc = 10; factors.append(f"📈 Цена {pct_3:+.2f}% за 45 мин")

    # ── F3: Ускорение ─────────────────────────────────────────────────────────
    accel_sc = 0
    if abs(pct_1) >= abs3 * 0.5:
        accel_sc = 10; factors.append(f"⚡ Ускорение: последняя свеча {pct_1:+.2f}%")
    elif abs3 > abs6 * 0.7 and abs6 > 0:
        accel_sc = 5;  factors.append(f"⚡ Ускорение: импульс нарастает")

    # ── F4: Свеча поглощения ──────────────────────────────────────────────────
    engulf_sc = 0
    last, prev = c[-1], c[-2]
    body_l = abs(last["c"] - last["o"])
    body_p = abs(prev["c"] - prev["o"])
    is_correct_dir = (direction * (last["c"] - last["o"])) > 0
    if body_l > body_p * 1.5 and is_correct_dir:
        engulf_sc = 10; factors.append("🕯 Свеча поглощения — тело в 1.5x+ крупнее предыдущей")

    # ── F5: RSI ───────────────────────────────────────────────────────────────
    closes = [x["c"] for x in c]
    rsi    = calc_rsi(closes)
    rsi_sc = 0
    if sig_type == "Pump":
        if 55 <= rsi <= 75:
            rsi_sc = 8;  factors.append(f"📊 RSI {rsi} — зона роста, подтверждает LONG")
        elif rsi > 75:
            rsi_sc = 4;  factors.append(f"⚠️ RSI {rsi} — перекуплен, риск выше")
        elif rsi < 35:
            rsi_sc = 5;  factors.append(f"📊 RSI {rsi} — перепродан, отскок возможен")
    else:
        if 25 <= rsi <= 45:
            rsi_sc = 8;  factors.append(f"📊 RSI {rsi} — зона падения, подтверждает SHORT")
        elif rsi < 25:
            rsi_sc = 4;  factors.append(f"⚠️ RSI {rsi} — перепродан, риск выше")
        elif rsi > 65:
            rsi_sc = 5;  factors.append(f"📊 RSI {rsi} — перекуплен, падение возможно")

    # ── F6: EMA тренд ─────────────────────────────────────────────────────────
    ema_sc = 0
    ema20 = calc_ema(closes[-20:], 20)
    ema50 = calc_ema(closes[-50:], 50) if len(closes) >= 50 else ema20
    if sig_type == "Pump" and price_now > ema20 > ema50:
        ema_sc = 7; factors.append(f"📐 EMA20 > EMA50 — восходящий тренд подтверждён")
    elif sig_type == "Dump" and price_now < ema20 < ema50:
        ema_sc = 7; factors.append(f"📐 EMA20 < EMA50 — нисходящий тренд подтверждён")
    elif sig_type == "Pump" and price_now > ema20:
        ema_sc = 3; factors.append(f"📐 Цена выше EMA20")
    elif sig_type == "Dump" and price_now < ema20:
        ema_sc = 3; factors.append(f"📐 Цена ниже EMA20")

    # ── F7: Объём нарастает (последние 3 свечи) ───────────────────────────────
    vol_trend_sc = 0
    vols = [x["v"] for x in c[-4:]]
    if len(vols) == 4 and vols[-1] > vols[-2] > vols[-3]:
        vol_trend_sc = 5; factors.append("📦 Объём нарастает 3 свечи подряд")

    # ── Объём USD ─────────────────────────────────────────────────────────────
    vol_usd = c[-1]["v"]
    if vol_usd < MIN_VOL_USD: return None

    # ── Итог ──────────────────────────────────────────────────────────────────
    total = vol_sc + price_sc + accel_sc + engulf_sc + rsi_sc + ema_sc + vol_trend_sc
    score = max(0, min(100, total))

    if score < MIN_SCORE: return None

    return {
        "type":      sig_type,
        "score":     score,
        "pct_1":     round(pct_1,  4),
        "pct_3":     round(pct_3,  4),
        "pct_6":     round(pct_6,  4),
        "pct_12":    round(pct_12, 4),
        "rvol":      rv,
        "rsi":       rsi,
        "vol_usd":   round(vol_usd, 0),
        "ema20":     round(ema20, 8),
        "factors":   factors,
        "engulf":    engulf_sc > 0,
        "accel":     accel_sc  > 0,
        "price_now": price_now,
        "price_3ago": price_3,
    }

# ─── Уровни TP / SL ──────────────────────────────────────────────────────────

def calc_levels(candles: list, sig_type: str) -> dict:
    atr   = calc_atr(candles)
    price = candles[-1]["c"]
    sgn   = 1 if sig_type == "Pump" else -1

    # Уровни поддержки/сопротивления (недавние High/Low)
    highs_10 = [c["h"] for c in candles[-10:]]
    lows_10  = [c["l"] for c in candles[-10:]]
    near_res = max(highs_10)
    near_sup = min(lows_10)

    entry = round(price, 8)
    # TP на основе ATR + ближайшие уровни
    tp1 = round(price + sgn * atr * 1.2, 8)
    tp2 = round(price + sgn * atr * 2.8, 8)
    tp3 = round(price + sgn * atr * 5.0, 8)
    sl  = round(price - sgn * atr * 1.0, 8)

    def pct(a: float, b: float) -> float:
        return round(abs(b - a) / a * 100, 4) if a else 0

    return {
        "entry":    entry,
        "atr":      round(atr, 8),
        "tp1":      tp1,  "tp1_pct": pct(entry, tp1),
        "tp2":      tp2,  "tp2_pct": pct(entry, tp2),
        "tp3":      tp3,  "tp3_pct": pct(entry, tp3),
        "sl":       sl,   "sl_pct":  pct(entry, sl),
        "near_res": near_res,
        "near_sup": near_sup,
    }

# ─── PNG График ──────────────────────────────────────────────────────────────

def _chunk(name: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(name + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

def make_png(px: list, W: int, H: int) -> bytes:
    raw = b"".join(b"\x00" + bytes([v for p in row for v in p]) for row in px)
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(raw, 6))
            + _chunk(b"IEND", b""))

def draw_chart(candles: list, sig: dict) -> bytes:
    W, H = 720, 360
    PL, PR, PT, PB = 12, 95, 30, 40

    BG    = (13, 15, 22)
    GRID  = (26, 30, 42)
    UP    = (38, 166, 154)
    DOWN  = (239, 83, 80)
    ENTRY = (255, 200, 0)
    TP_C  = (56, 210, 120)
    SL_C  = (220, 55, 55)
    WHITE = (200, 210, 220)
    GRAY  = (100, 110, 130)

    last = candles[-50:] if len(candles) >= 50 else candles
    n    = len(last)

    entry = sig.get("entry", sig["price_now"])
    tp1   = sig.get("tp1",   entry * 1.02)
    tp2   = sig.get("tp2",   entry * 1.04)
    tp3   = sig.get("tp3",   entry * 1.07)
    sl    = sig.get("sl",    entry * 0.97)

    all_p = ([c["h"] for c in last] + [c["l"] for c in last]
             + [entry, tp3, sl])
    p_min = min(all_p) * 0.998
    p_max = max(all_p) * 1.002
    p_rng = (p_max - p_min) or 1

    cw, ch = W - PL - PR, H - PT - PB

    def ty(p: float) -> int:
        return PT + ch - int((p - p_min) / p_rng * ch)
    def tx(i: int) -> int:
        return PL + int(i / max(n-1, 1) * cw)

    px = [[BG]*W for _ in range(H)]

    def sp(x, y, col):
        if 0 <= x < W and 0 <= y < H: px[y][x] = col

    def hline(y, x1, x2, col, dash=False):
        for x in range(x1, x2):
            if not dash or (x//5)%2==0: sp(x, y, col)

    def vline(x, y1, y2, col):
        for y in range(min(y1,y2), max(y1,y2)+1): sp(x, y, col)

    def rect(x0, y0, rw, rh, col):
        for dy in range(max(rh,1)):
            for dx in range(max(rw,1)): sp(x0+dx, y0+dy, col)

    # Сетка
    for i in range(7):
        gy = PT + int(i/6*ch)
        hline(gy, PL, W-PR, GRID, dash=True)

    # Вертикальные линии (каждые 10 свечей)
    for i in range(0, n, 10):
        vline(tx(i), PT, PT+ch, GRID)

    # Уровни
    for price_lvl, col, lbl in [
        (entry, ENTRY, "ENTRY"),
        (tp1,   TP_C,  "TP1"),
        (tp2,   TP_C,  "TP2"),
        (tp3,   TP_C,  "TP3"),
        (sl,    SL_C,  "SL"),
    ]:
        if not price_lvl or not (p_min < price_lvl < p_max): continue
        y = ty(price_lvl)
        hline(y, PL, W-PR-4, col, dash=True)
        # Маркер цены справа
        rect(W-PR+2, max(y-4, 0), 10, 8, col)

    # Объёмные бары (снизу, 40px)
    vol_area = 40
    max_v = max((c["v"] for c in last), default=1)
    bw = max(int(cw/n)-1, 1)
    for i, c in enumerate(last):
        col = UP if c["c"] >= c["o"] else DOWN
        vh  = max(int(c["v"]/max_v * vol_area), 1)
        rect(tx(i), H-PB-vh, bw, vh, (col[0]//4, col[1]//4, col[2]//4))

    # Свечи
    half = max(bw//2, 1)
    for i, c in enumerate(last):
        x0   = tx(i)
        xc   = x0 + half
        col  = UP if c["c"] >= c["o"] else DOWN
        vline(xc, ty(c["h"]), ty(c["l"]), col)
        y_top = min(ty(c["o"]), ty(c["c"]))
        y_bot = max(ty(c["o"]), ty(c["c"]))
        rect(x0, y_top, max(bw,2), max(y_bot-y_top, 1), col)

    # Последняя свеча — белая рамка
    lc = last[-1]
    lcol = UP if lc["c"] >= lc["o"] else DOWN
    xc = tx(n-1) + half
    sp(xc, ty(lc["c"]), WHITE)

    return make_png(px, W, H)

# ─── Форматирование ───────────────────────────────────────────────────────────

def fp(p: float) -> str:
    if not p: return "—"
    if p >= 10000: return f"{p:,.0f}"
    if p >= 100:   return f"{p:.2f}"
    if p >= 1:     return f"{p:.4f}"
    if p >= 0.001: return f"{p:.6f}"
    return f"{p:.8f}"

def fv(v: float) -> str:
    if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if v >= 1_000:     return f"${v/1_000:.1f}K"
    return f"${v:.0f}"

# ─── Telegram ─────────────────────────────────────────────────────────────────

def tg_text(text: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id: return
    try:
        body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=6)
    except Exception:
        pass

def tg_photo(img: bytes, caption: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id: return
    boundary = b"PB77"
    CRLF     = b"\r\n"
    def pf(name, val):
        return b"--"+boundary+CRLF+f'Content-Disposition: form-data; name="{name}"'.encode()+CRLF+CRLF+val.encode()+CRLF
    def pfile(name, fname, ct, data):
        return (b"--"+boundary+CRLF
                +f'Content-Disposition: form-data; name="{name}"; filename="{fname}"'.encode()+CRLF
                +f"Content-Type: {ct}".encode()+CRLF+CRLF+data+CRLF)
    body = (pf("chat_id", chat_id)+pf("caption", caption)+pf("parse_mode","HTML")
            +pfile("photo","chart.png","image/png",img)
            +b"--"+boundary+b"--"+CRLF)
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
            method="POST")
        urllib.request.urlopen(req, timeout=14)
    except Exception:
        tg_text(caption)

def build_caption(sig: dict) -> str:
    is_pump   = sig["type"] == "Pump"
    lev       = sig.get("leverage", 2)
    pos_usdt  = sig.get("position_usdt", 30)
    pos_with_lev = round(pos_usdt * lev, 1)
    entry     = sig.get("entry", sig["price_now"])
    tp1, tp2, tp3, sl = sig.get("tp1",0), sig.get("tp2",0), sig.get("tp3",0), sig.get("sl",0)
    tp1p, tp2p, tp3p  = sig.get("tp1_pct",0), sig.get("tp2_pct",0), sig.get("tp3_pct",0)
    slp               = sig.get("sl_pct",0)

    # Прибыль в USDT на каждом уровне
    def profit(pct_val: float) -> str:
        return f"+${pos_with_lev * pct_val/100:.2f}"

    action   = "LONG 📈" if is_pump else "SHORT 📉"
    sign     = "+" if is_pump else "-"
    score    = sig.get("score", 65)
    rvol_v   = sig.get("rvol", 1)
    rsi_v    = sig.get("rsi",  50)
    pct3     = abs(sig.get("pct_3", 0))
    pct6     = abs(sig.get("pct_6", 0))

    # Факторы (первые 5, кратко)
    factors  = sig.get("factors", [])
    facts_txt = "\n".join(f"  • {f}" for f in factors[:6])

    return (
        f"{'🚀' if is_pump else '💣'} <b>{sig['type'].upper()} — {sig['pair']}</b>  [{sig['exchange']}]\n"
        f"{'🟢'*2 if is_pump else '🔴'*2}  Score: <b>{score}/100</b>  ·  15m  ·  {sig['time']} UTC\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Цена:  ${fp(sig['price_3ago'])} → <b>${fp(sig['price_now'])}</b>"
        f"  (<b>{sign}{pct3:.2f}%</b> / 45м,  {sign}{pct6:.2f}% / 90м)\n"
        f"📊 Объём: <b>{fv(sig['vol_usd'])}</b>  ·  RVOL <b>{rvol_v:.1f}x</b>  ·  RSI <b>{rsi_v}</b>\n"
        f"\n<b>━ ПОЧЕМУ СИГНАЛ ━</b>\n"
        f"{facts_txt}\n"
        f"\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>СИГНАЛ: {action}</b>\n\n"
        f"📌 Вход:          <b>${fp(entry)}</b>\n"
        f"🔥 Плечо:         <b>{lev}x</b>  (позиция ${pos_usdt:.0f} → ${pos_with_lev:.0f})\n\n"
        f"✅ TP1 <i>(осторожный)</i>:   <b>${fp(tp1)}</b>  +{tp1p:.1f}%  →  <b>{profit(tp1p)}</b>\n"
        f"✅ TP2 <i>(оптимальный)</i>:  <b>${fp(tp2)}</b>  +{tp2p:.1f}%  →  <b>{profit(tp2p)}</b>\n"
        f"✅ TP3 <i>(агрессивный)</i>:  <b>${fp(tp3)}</b>  +{tp3p:.1f}%  →  <b>{profit(tp3p)}</b>\n\n"
        f"🛑 Стоп-лосс:     <b>${fp(sl)}</b>  -{slp:.1f}%  →  <b>-${pos_with_lev * slp/100:.2f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 Банк: $1000  ·  На сделку: <b>${pos_usdt:.0f}</b>  ·  Плечо: <b>{lev}x</b>"
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

def get_portfolio_balance() -> float:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"SELECT current_balance FROM {SCHEMA}.pump_portfolio LIMIT 1")
        r = cur.fetchone()
        cur.close(); conn.close()
        return float(r[0]) if r else BALANCE
    except Exception:
        return BALANCE

def save_signal(sig: dict) -> int | None:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        lev       = sig.get("leverage", 2)
        pos_usdt  = sig.get("position_usdt", 30)
        factors_j = json.dumps(sig.get("factors", []), ensure_ascii=False)
        reasoning = "\n".join(sig.get("factors", []))

        cur.execute(
            f"""INSERT INTO {SCHEMA}.signals
            (pair, signal_type, exchange, entry_price, target_price, stop_price,
             confidence, status, rsi, macd_signal, bb_position, volume_ratio,
             fear_greed, sentiment, analysis_text, timeframe,
             score_bull, score_bear, leverage, position_size,
             leverage_recommended, position_usdt, reasoning, factors_json,
             rvol, rsi_value, pct_15m, pct_45m, pct_90m,
             tp1_price, tp2_price, tp3_price, tp1_pct, tp2_pct, tp3_pct,
             sl_pct, atr_value)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id""",
            (
                sig["pair"], "LONG" if sig["type"]=="Pump" else "SHORT",
                sig["exchange"], sig["entry"], sig["tp2"], sig["sl"],
                sig["score"], "active",
                sig.get("rsi", 50), "pump_v3", 0.5,
                round(sig.get("rvol", 1), 2), 50, sig["type"],
                reasoning[:500], "15m",
                sig["score"] if sig["type"]=="Pump" else 0,
                sig["score"] if sig["type"]=="Dump"  else 0,
                lev, round(pos_usdt * lev, 2),
                lev, round(pos_usdt, 2),
                reasoning[:1000], factors_j,
                sig.get("rvol", 1), sig.get("rsi", 50),
                sig.get("pct_1", 0), sig.get("pct_3", 0), sig.get("pct_6", 0),
                sig.get("tp1", 0), sig.get("tp2", 0), sig.get("tp3", 0),
                sig.get("tp1_pct", 0), sig.get("tp2_pct", 0), sig.get("tp3_pct", 0),
                sig.get("sl_pct", 0), sig.get("atr", 0),
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
            f"""SELECT id, pair, signal_type, exchange,
                entry_price, target_price, stop_price,
                confidence, status, analysis_text, created_at,
                result, result_pct, pnl_usdt,
                leverage_recommended, position_usdt, reasoning, factors_json,
                rvol, rsi_value, pct_15m, pct_45m, pct_90m,
                tp1_price, tp2_price, tp3_price,
                tp1_pct, tp2_pct, tp3_pct, sl_pct
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status != 'archived'
            ORDER BY created_at DESC LIMIT %s""", (limit,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        out = []
        for r in rows:
            factors = []
            try:
                if r[17]: factors = json.loads(r[17])
            except Exception:
                pass
            out.append({
                "id": r[0], "pair": r[1],
                "type": "Pump" if r[2]=="LONG" else "Dump",
                "exchange": r[3],
                "entry": float(r[4]), "tp2": float(r[5]), "sl": float(r[6]),
                "price_now": float(r[4]), "price_from": float(r[4]),
                "price_pct": float(r[22] or 0),
                "volume_usd": 0, "volume_pct": float(r[7] or 0),
                "volume_increase_usd": 0,
                "score": r[7] or 50, "strength": r[7] or 50,
                "timeframe": "15m",
                "analysis": r[9] or "",
                "reasoning": r[16] or "",
                "factors": factors,
                "leverage": r[14] or 1,
                "position_usdt": float(r[15] or 0),
                "rvol": float(r[18] or 1),
                "rsi": float(r[19] or 50),
                "pct_1":  float(r[20] or 0),
                "pct_3":  float(r[21] or 0),
                "pct_6":  float(r[22] or 0),
                "tp1": float(r[23] or 0), "tp2": float(r[24] or 0), "tp3": float(r[25] or 0),
                "tp1_pct": float(r[26] or 0), "tp2_pct": float(r[27] or 0),
                "tp3_pct": float(r[28] or 0), "sl_pct": float(r[29] or 0),
                "time":   r[10].strftime("%H:%M")         if r[10] else "—",
                "date":   r[10].strftime("%d.%m %H:%M")   if r[10] else "—",
                "result": r[11],
                "result_pct": round(float(r[12]),2) if r[12] else None,
                "pnl_usdt":   round(float(r[13]),2) if r[13] else None,
            })
        return out
    except Exception:
        return []

def get_stats() -> dict:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*) total,
                COUNT(*) FILTER (WHERE sentiment='Pump')  pumps,
                COUNT(*) FILTER (WHERE sentiment='Dump')  dumps,
                COUNT(*) FILTER (WHERE result='win')      wins,
                COUNT(*) FILTER (WHERE result='loss')     losses,
                AVG(confidence) FILTER (WHERE sentiment IN ('Pump','Dump')) avg_score,
                AVG(result_pct) FILTER (WHERE result='win') avg_win_pct,
                COALESCE(SUM(pnl_usdt),0) total_pnl
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status != 'archived'""")
        r = cur.fetchone()
        total = r[0] or 0; pumps=r[1] or 0; dumps=r[2] or 0
        wins=r[3] or 0; losses=r[4] or 0
        closed = wins+losses
        wr = round(wins/closed*100,1) if closed>0 else 0

        # По биржам
        cur.execute(f"""
            SELECT exchange, COUNT(*) cnt,
                COUNT(*) FILTER (WHERE result='win') w
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status!='archived'
            GROUP BY exchange ORDER BY cnt DESC""")
        by_exch = [{"exchange": x[0], "total": x[1], "wins": x[2]} for x in cur.fetchall()]

        # По дням
        cur.execute(f"""
            SELECT DATE(created_at) d, COUNT(*) cnt
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status!='archived'
              AND created_at > NOW() - INTERVAL '14 days'
            GROUP BY d ORDER BY d DESC""")
        daily = [{"date": str(x[0]), "count": x[1]} for x in cur.fetchall()]

        # Портфель
        cur.execute(f"SELECT initial_balance,current_balance,wins,losses,total_signals FROM {SCHEMA}.pump_portfolio LIMIT 1")
        pr = cur.fetchone()
        portfolio = {}
        if pr:
            bal = float(pr[1])
            ini = float(pr[0])
            portfolio = {
                "balance": bal, "initial": ini,
                "pnl": round(bal-ini, 2),
                "pnl_pct": round((bal-ini)/ini*100, 2),
                "wins": pr[2] or 0, "losses": pr[3] or 0,
                "total_signals": pr[4] or 0,
            }

        cur.close(); conn.close()
        return {
            "total": total, "pumps": pumps, "dumps": dumps,
            "wins": wins, "losses": losses, "closed": closed,
            "win_rate": wr,
            "avg_score": round(float(r[5] or 0), 1),
            "avg_win_pct": round(float(r[6] or 0), 2),
            "total_pnl": round(float(r[7] or 0), 2),
            "daily": daily, "by_exchange": by_exch,
            "portfolio": portfolio,
        }
    except Exception:
        return {"total":0,"pumps":0,"dumps":0,"wins":0,"losses":0,"closed":0,
                "win_rate":0,"avg_score":0,"avg_win_pct":0,"total_pnl":0,
                "daily":[],"by_exchange":[],"portfolio":{}}

# ─── Сканирование ────────────────────────────────────────────────────────────

def run_scan(only_exchange: str | None = None) -> dict:
    pairs_map = ({only_exchange: EXCHANGE_PAIRS[only_exchange]}
                 if only_exchange and only_exchange in EXCHANGE_PAIRS
                 else EXCHANGE_PAIRS)
    total   = sum(len(v) for v in pairs_map.values())
    found   = []
    errors  = 0
    balance = get_portfolio_balance()

    for exchange, pairs in pairs_map.items():
        for sym in pairs:
            try:
                candles = get_candles(exchange, sym)
                scored  = score_signal(candles)
                if not scored: continue

                pair = sym.replace("-", "/").replace("USDT", "/USDT")
                if "/USDT/USDT" in pair:
                    pair = pair.replace("/USDT/USDT", "/USDT")

                if already_sent(pair, exchange): continue

                levels  = calc_levels(candles, scored["type"])
                lev, pos_pct = get_leverage(scored["score"])
                pos_usdt = round(balance * pos_pct, 2)

                sig = {
                    "pair": pair, "symbol": sym, "exchange": exchange,
                    "timeframe": "15m",
                    "time": datetime.now(timezone.utc).strftime("%H:%M"),
                    "candles": candles,
                    "leverage": lev,
                    "position_usdt": pos_usdt,
                    **scored, **levels,
                }

                db_id = save_signal(sig)
                if db_id: sig["id"] = db_id

                notify(sig)
                sig.pop("candles", None)
                found.append(sig)

            except Exception:
                errors += 1

    found.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"signals": found, "analyzed": total, "found": len(found), "errors": errors}

# ─── Handler ─────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """PumpBot v3: Binance+Bybit+OKX+MEXC · 150+ пар · Score+Leverage+Reasoning."""
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
            "🚀 <b>PumpBot v3 — активен!</b>\n\n"
            "✅ Binance · Bybit · OKX · MEXC\n"
            "✅ 150+ пар · каждые 5 минут\n"
            "✅ Score 0–100 · Плечо до 15x\n"
            "✅ Reasoning · TP1/TP2/TP3 · SL\n"
            "✅ Виртуальный банк $1,000\n\n"
            "Жду пампов... 🎯"
        )
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"ok": True})}

    only = params.get("exchange")
    result = run_scan(only)
    return {
        "statusCode": 200, "headers": HEADERS,
        "body": json.dumps({
            **result,
            "exchange": only or "all",
            "exchanges": list(EXCHANGE_PAIRS.keys()),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        })
    }
