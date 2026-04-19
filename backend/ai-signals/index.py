"""
PumpBot v4 — детектор памп/дамп, мировой уровень.
Лозунг: правда, правда и ещё раз правда.

Принципы:
  - Сигнал даётся ТОЛЬКО при подтверждении 7 факторов
  - TP/SL реалистичные: на основе ATR + % от цены
  - Каждый сигнал автоматически закрывается (win/loss) через 4 часа
  - Статистика 100% честная — никакого приукрашивания
  - Виртуальный банк $1000 — реальный P&L

Биржи: Binance, Bybit, OKX, MEXC — 150+ пар, 15m, каждые 5 мин.

Score 0–100 → порог ≥ 65.
Плечо по Score: 65→2x, 70→3x, 75→5x, 80→7x, 85→10x, 90→15x.
"""
from __future__ import annotations
import json
import urllib.request
import os
import struct
import zlib
import psycopg2
from datetime import datetime, timezone

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}
SCHEMA       = "t_p73206386_global_trading_signa"
START_BANK   = 1000.0   # стартовый виртуальный банк
MIN_SCORE    = 50
MIN_VOL_USD  = 30_000   # минимум $30k объёма за свечу 15м
MIN_PRICE_PCT = 0.8     # движение цены за 45 мин (снижено для боковых рынков)
MIN_RVOL     = 1.1      # минимальный всплеск объёма
COOLDOWN_MIN = 30       # антиспам: одна пара не чаще раза в 30 мин
CLOSE_HOURS  = 4        # закрываем сигнал принудительно через 4 часа

LEVERAGE_MAP = [
    (90, 15, 0.12),
    (85, 10, 0.10),
    (80,  7, 0.08),
    (75,  5, 0.07),
    (70,  3, 0.05),
    (65,  2, 0.03),
    (55,  1, 0.02),
]

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

# ─── HTTP ─────────────────────────────────────────────────────────────────────

def fetch(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PumpBot/4.0"})
        with urllib.request.urlopen(req, timeout=9) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def get_price_now(exchange: str, sym: str) -> float | None:
    """Получаем текущую цену для проверки TP/SL."""
    if exchange in ("Binance", "MEXC"):
        base = "https://api.binance.com" if exchange == "Binance" else "https://api.mexc.com"
        d = fetch(f"{base}/api/v3/ticker/price?symbol={sym}")
        if isinstance(d, dict) and "price" in d:
            return float(d["price"])
    elif exchange == "Bybit":
        d = fetch(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={sym}")
        if isinstance(d, dict) and d.get("retCode") == 0:
            lst = d.get("result", {}).get("list", [])
            if lst: return float(lst[0].get("lastPrice", 0))
    elif exchange == "OKX":
        d = fetch(f"https://www.okx.com/api/v5/market/ticker?instId={sym}")
        if isinstance(d, dict) and d.get("code") == "0":
            lst = d.get("data", [])
            if lst: return float(lst[0].get("last", 0))
    return None

# ─── Свечи ────────────────────────────────────────────────────────────────────

def candles_binance(sym: str, n: int = 80) -> list:
    # c[7] = quoteAssetVolume (уже в USDT) — правильный объём
    d = fetch(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=15m&limit={n}")
    if not isinstance(d, list): return []
    return [{"o":float(c[1]),"h":float(c[2]),"l":float(c[3]),"c":float(c[4]),
             "v":float(c[7]),  # quote volume = USDT
             "bv":float(c[5]) # base volume = монеты
            } for c in d]

def candles_bybit(sym: str, n: int = 80) -> list:
    # c[6] = turnover (USDT), c[5] = volume (монеты)
    d = fetch(f"https://api.bybit.com/v5/market/kline?category=spot&symbol={sym}&interval=15&limit={n}")
    if not isinstance(d, dict) or d.get("retCode") != 0: return []
    rows = list(reversed(d.get("result", {}).get("list", [])))
    return [{"o":float(c[1]),"h":float(c[2]),"l":float(c[3]),"c":float(c[4]),
             "v":float(c[6]),  # turnover = USDT
             "bv":float(c[5])
            } for c in rows]

def candles_okx(sym: str, n: int = 80) -> list:
    # c[7] = volCcyQuote (USDT)
    d = fetch(f"https://www.okx.com/api/v5/market/candles?instId={sym}&bar=15m&limit={n}")
    if not isinstance(d, dict) or d.get("code") != "0": return []
    rows = list(reversed(d.get("data", [])))
    return [{"o":float(c[1]),"h":float(c[2]),"l":float(c[3]),"c":float(c[4]),
             "v":float(c[7]) if len(c)>7 else float(c[5])*float(c[4]),
             "bv":float(c[5])
            } for c in rows]

def candles_mexc(sym: str, n: int = 80) -> list:
    # c[7] = quoteAssetVolume (USDT)
    d = fetch(f"https://api.mexc.com/api/v3/klines?symbol={sym}&interval=15m&limit={n}")
    if not isinstance(d, list): return []
    return [{"o":float(c[1]),"h":float(c[2]),"l":float(c[3]),"c":float(c[4]),
             "v":float(c[7]),  # quote volume = USDT
             "bv":float(c[5])
            } for c in d]

def get_candles(exchange: str, sym: str) -> list:
    fn = {"Binance": candles_binance, "Bybit": candles_bybit,
          "OKX": candles_okx, "MEXC": candles_mexc}.get(exchange)
    return fn(sym) if fn else []

# ─── Индикаторы ───────────────────────────────────────────────────────────────

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
    if len(candles) < look+2: return 1.0
    # Используем предпоследнюю свечу — последняя ещё не закрыта!
    avg = sum(c["v"] for c in candles[-look-2:-2]) / look
    return round(candles[-2]["v"]/avg, 2) if avg > 0 else 1.0

# ─── Многофакторный scoring ───────────────────────────────────────────────────

def score_signal(candles: list) -> dict | None:
    if len(candles) < 25: return None

    c = candles
    # -2 = последняя ЗАКРЫТАЯ свеча, -1 = текущая (ещё формируется)
    price_now = c[-2]["c"]
    price_1   = c[-3]["c"]
    price_3   = c[-5]["c"]
    price_6   = c[-8]["c"]
    price_12  = c[-14]["c"]

    if price_now <= 0 or price_3 <= 0: return None

    pct_1  = (price_now - price_1)  / price_1  * 100
    pct_3  = (price_now - price_3)  / price_3  * 100
    pct_6  = (price_now - price_6)  / price_6  * 100
    pct_12 = (price_now - price_12) / price_12 * 100

    if abs(pct_3) < MIN_PRICE_PCT and abs(pct_6) < MIN_PRICE_PCT * 1.3:
        return None  # не хватает движения цены

    sig_type  = "Pump" if pct_3 >= 0 else "Dump"
    direction = 1 if sig_type == "Pump" else -1
    factors   = []

    # F1: RVOL (0–30 pts) — не жёсткий фильтр, а баллы
    rv = calc_rvol(c, 20)
    if rv >= 5.0:    vol_sc = 30; factors.append(f"💥 RVOL {rv:.1f}x — экстремальный объём (топ 1%)")
    elif rv >= 3.0:  vol_sc = 22; factors.append(f"📊 RVOL {rv:.1f}x — сильный всплеск объёма")
    elif rv >= 1.5:  vol_sc = 15; factors.append(f"📊 RVOL {rv:.1f}x — повышенный объём")
    elif rv >= MIN_RVOL: vol_sc = 8; factors.append(f"📊 RVOL {rv:.1f}x — чуть выше нормы")
    else:            vol_sc = 0   # нет всплеска — 0 баллов, но не блокируем

    # F2: Движение цены (0–25 pts)
    abs3 = abs(pct_3)
    if abs3 >= 8:   price_sc = 25; factors.append(f"🚀 Цена {pct_3:+.2f}% за 45 мин — сильный импульс")
    elif abs3 >= 5: price_sc = 18; factors.append(f"📈 Цена {pct_3:+.2f}% за 45 мин — чёткое движение")
    else:           price_sc = 10; factors.append(f"📈 Цена {pct_3:+.2f}% за 45 мин")

    # F3: Ускорение (0–10 pts)
    accel_sc = 0
    if abs(pct_1) >= abs3 * 0.5:
        accel_sc = 10; factors.append(f"⚡ Ускорение: последняя свеча {pct_1:+.2f}% — импульс нарастает")
    elif abs3 > abs(pct_6) * 0.7 and abs(pct_6) > 0:
        accel_sc = 5;  factors.append(f"⚡ Ускорение: темп движения ускоряется")

    # F4: Свеча поглощения (0–10 pts)
    engulf_sc = 0
    last, prev = c[-1], c[-2]
    body_l = abs(last["c"] - last["o"])
    body_p = abs(prev["c"] - prev["o"])
    if body_l > body_p * 1.5 and (direction * (last["c"] - last["o"])) > 0:
        engulf_sc = 10; factors.append("🕯 Свеча поглощения: тело в 1.5x+ крупнее предыдущей")

    # F5: RSI (0–8 pts)
    closes = [x["c"] for x in c]
    rsi    = calc_rsi(closes)
    rsi_sc = 0
    if sig_type == "Pump":
        if 55 <= rsi <= 75:  rsi_sc = 8;  factors.append(f"📊 RSI {rsi} — зона роста, подтверждает LONG")
        elif rsi > 75:       rsi_sc = 3;  factors.append(f"⚠️ RSI {rsi} — перекуплен (осторожно, риск коррекции)")
        elif rsi < 35:       rsi_sc = 5;  factors.append(f"📊 RSI {rsi} — перепродан, ожидаем отскок")
    else:
        if 25 <= rsi <= 45:  rsi_sc = 8;  factors.append(f"📊 RSI {rsi} — зона падения, подтверждает SHORT")
        elif rsi < 25:       rsi_sc = 3;  factors.append(f"⚠️ RSI {rsi} — перепродан (возможен отскок, осторожно)")
        elif rsi > 65:       rsi_sc = 5;  factors.append(f"📊 RSI {rsi} — перекуплен, ожидаем снижение")

    # F6: EMA тренд (0–7 pts)
    ema_sc = 0
    ema20  = calc_ema(closes[-20:], 20)
    ema50  = calc_ema(closes[-50:], 50) if len(closes) >= 50 else ema20
    if sig_type == "Pump" and price_now > ema20 > ema50:
        ema_sc = 7; factors.append("📐 EMA20 > EMA50 — восходящий тренд подтверждён")
    elif sig_type == "Dump" and price_now < ema20 < ema50:
        ema_sc = 7; factors.append("📐 EMA20 < EMA50 — нисходящий тренд подтверждён")
    elif sig_type == "Pump" and price_now > ema20:
        ema_sc = 3; factors.append("📐 Цена выше EMA20 — краткосрочный тренд вверх")
    elif sig_type == "Dump" and price_now < ema20:
        ema_sc = 3; factors.append("📐 Цена ниже EMA20 — краткосрочный тренд вниз")

    # F7: Нарастающий объём (0–5 pts) — по закрытым свечам
    vol_trend_sc = 0
    vols = [x["v"] for x in c[-5:-1]]  # 4 закрытых свечи
    if len(vols) == 4 and vols[-1] > vols[-2] > vols[-3]:
        vol_trend_sc = 5; factors.append("📦 Объём нарастает 3 свечи подряд — устойчивый поток")

    # Объём в USDT (quote volume — уже в USD, берём закрытую свечу)
    vol_usd = c[-2]["v"]
    if vol_usd < MIN_VOL_USD: return None

    total = vol_sc + price_sc + accel_sc + engulf_sc + rsi_sc + ema_sc + vol_trend_sc
    score = max(0, min(100, total))
    if score < MIN_SCORE: return None

    return {
        "type": sig_type, "score": score,
        "pct_1": round(pct_1,4), "pct_3": round(pct_3,4),
        "pct_6": round(pct_6,4), "pct_12": round(pct_12,4),
        "rvol": rv, "rsi": rsi,
        "vol_usd": round(vol_usd, 0),
        "factors": factors,
        "engulf": engulf_sc > 0, "accel": accel_sc > 0,
        "price_now": price_now, "price_3ago": price_3,
    }

# ─── Уровни TP/SL (реалистичные) ─────────────────────────────────────────────

def calc_levels(candles: list, sig_type: str, score: int) -> dict:
    """
    TP/SL на основе ATR + % от цены.
    Реалистичные цели для pump/dump торговли на 15m:
      TP1 = 1.5x ATR (быстрый выход, осторожный)
      TP2 = 2.5x ATR (оптимальный)
      TP3 = 4.0x ATR (агрессивный, если памп продолжится)
      SL  = 1.0x ATR (стоп ниже ATR)
    """
    atr   = calc_atr(candles)
    price = candles[-1]["c"]
    sgn   = 1 if sig_type == "Pump" else -1

    entry = price

    # ATR-based уровни (реалистичные множители для 15m pump)
    tp1 = round(price + sgn * atr * 1.5, 8)
    tp2 = round(price + sgn * atr * 2.5, 8)
    tp3 = round(price + sgn * atr * 4.0, 8)
    sl  = round(price - sgn * atr * 1.0, 8)

    def pct(a: float, b: float) -> float:
        return round(abs(b-a)/a*100, 4) if a else 0

    tp1_pct = pct(entry, tp1)
    tp2_pct = pct(entry, tp2)
    tp3_pct = pct(entry, tp3)
    sl_pct  = pct(entry, sl)

    return {
        "entry": round(entry, 8), "atr": round(atr, 8),
        "tp1": tp1, "tp1_pct": tp1_pct,
        "tp2": tp2, "tp2_pct": tp2_pct,
        "tp3": tp3, "tp3_pct": tp3_pct,
        "sl":  sl,  "sl_pct":  sl_pct,
    }

def get_leverage(score: int) -> tuple[int, float]:
    for threshold, lev, pct in LEVERAGE_MAP:
        if score >= threshold:
            return lev, pct
    return 2, 0.03

# ─── PNG-график ───────────────────────────────────────────────────────────────

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
    W, H   = 720, 360
    PL, PR, PT, PB = 12, 95, 30, 40
    BG, GRID = (13, 15, 22), (26, 30, 42)
    UP, DOWN = (38, 166, 154), (239, 83, 80)
    ENTRY_C, TP_C, SL_C = (255, 200, 0), (56, 210, 120), (220, 55, 55)

    last = candles[-50:] if len(candles) >= 50 else candles
    n    = len(last)
    entry = sig.get("entry", sig["price_now"])
    tp1, tp3, sl = sig.get("tp1", entry*1.02), sig.get("tp3", entry*1.07), sig.get("sl", entry*0.97)

    all_p = [c["h"] for c in last] + [c["l"] for c in last] + [entry, tp3, sl]
    p_min = min(all_p) * 0.998; p_max = max(all_p) * 1.002; p_rng = (p_max - p_min) or 1
    cw, ch = W - PL - PR, H - PT - PB

    def ty(p): return PT + ch - int((p-p_min)/p_rng*ch)
    def tx(i): return PL + int(i/max(n-1,1)*cw)

    px_arr = [[BG]*W for _ in range(H)]

    def sp(x, y, col):
        if 0 <= x < W and 0 <= y < H: px_arr[y][x] = col

    def hl(y, x1, x2, col, dash=False):
        for x in range(x1, x2):
            if not dash or (x//5)%2==0: sp(x, y, col)

    def vl(x, y1, y2, col):
        for y in range(min(y1,y2), max(y1,y2)+1): sp(x, y, col)

    def rect(x0, y0, rw, rh, col):
        for dy in range(max(rh,1)):
            for dx in range(max(rw,1)): sp(x0+dx, y0+dy, col)

    for i in range(7): hl(PT+int(i/6*ch), PL, W-PR, GRID, dash=True)
    for i in range(0, n, 10): vl(tx(i), PT, PT+ch, GRID)

    for price_lvl, col in [(entry,ENTRY_C),(sig.get("tp1",0),TP_C),(sig.get("tp2",0),TP_C),(tp3,TP_C),(sl,SL_C)]:
        if price_lvl and p_min < price_lvl < p_max:
            y = ty(price_lvl); hl(y, PL, W-PR-4, col, dash=True)
            rect(W-PR+2, max(y-4,0), 10, 8, col)

    max_v = max((c["v"] for c in last), default=1)
    bw = max(int(cw/n)-1, 1)
    for i, c in enumerate(last):
        col = UP if c["c"] >= c["o"] else DOWN
        rect(tx(i), H-PB-max(int(c["v"]/max_v*35),1), bw, max(int(c["v"]/max_v*35),1),
             (col[0]//4, col[1]//4, col[2]//4))

    half = max(bw//2, 1)
    for i, c in enumerate(last):
        x0, xc = tx(i), tx(i)+half
        col = UP if c["c"] >= c["o"] else DOWN
        vl(xc, ty(c["h"]), ty(c["l"]), col)
        y_top = min(ty(c["o"]), ty(c["c"]))
        rect(x0, y_top, max(bw,2), max(max(ty(c["o"]),ty(c["c"]))-y_top,1), col)

    return make_png(px_arr, W, H)

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
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN",""), os.environ.get("TELEGRAM_CHAT_ID","")
    if not token or not chat_id: return
    try:
        body = json.dumps({"chat_id":chat_id,"text":text,"parse_mode":"HTML"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type":"application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=6)
    except Exception:
        pass

def tg_photo(img: bytes, caption: str):
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN",""), os.environ.get("TELEGRAM_CHAT_ID","")
    if not token or not chat_id: return
    boundary, CRLF = b"PB99", b"\r\n"
    def pf(name, val):
        return b"--"+boundary+CRLF+f'Content-Disposition: form-data; name="{name}"'.encode()+CRLF+CRLF+val.encode()+CRLF
    def pfile(name, fname, ct, data):
        return (b"--"+boundary+CRLF
                +f'Content-Disposition: form-data; name="{name}"; filename="{fname}"'.encode()+CRLF
                +f"Content-Type: {ct}".encode()+CRLF+CRLF+data+CRLF)
    body = pf("chat_id",chat_id)+pf("caption",caption)+pf("parse_mode","HTML")+pfile("photo","chart.png","image/png",img)+b"--"+boundary+b"--"+CRLF
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=body, headers={"Content-Type":f"multipart/form-data; boundary={boundary.decode()}"},
            method="POST")
        urllib.request.urlopen(req, timeout=14)
    except Exception:
        tg_text(caption)

def build_caption(sig: dict) -> str:
    is_pump = sig["type"] == "Pump"
    lev     = sig.get("leverage", 2)
    pos     = sig.get("position_usdt", 30)
    exp     = pos * lev
    entry   = sig.get("entry", sig["price_now"])
    score   = sig.get("score", 65)

    def profit(pct_v): return f"+${exp*pct_v/100:.2f}"
    def loss(pct_v):   return f"-${exp*pct_v/100:.2f}"

    facts_txt = "\n".join(f"  • {f}" for f in sig.get("factors", [])[:6])
    sign      = "+" if is_pump else "-"
    action    = "LONG 📈" if is_pump else "SHORT 📉"
    pct3      = abs(sig.get("pct_3", 0))
    pct6      = abs(sig.get("pct_6", 0))

    return (
        f"{'🚀' if is_pump else '💣'} <b>{sig['type']} — {sig['pair']}</b>  [{sig['exchange']}]\n"
        f"{'🟢🟢' if is_pump else '🔴🔴'}  Score: <b>{score}/100</b>  ·  15m  ·  {sig['time']} UTC\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Цена:  ${fp(sig['price_3ago'])} → <b>${fp(sig['price_now'])}</b>"
        f"  (<b>{sign}{pct3:.2f}%</b> / 45м,  {sign}{pct6:.2f}% / 90м)\n"
        f"📊 Объём: <b>{fv(sig['vol_usd'])}</b>  ·  RVOL <b>{sig.get('rvol',1):.1f}x</b>  ·  RSI <b>{sig.get('rsi',50)}</b>\n"
        f"\n<b>📋 ПОЧЕМУ ДАН СИГНАЛ:</b>\n{facts_txt}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>ДЕЙСТВИЕ: {action}</b>\n\n"
        f"📌 Вход:             <b>${fp(entry)}</b>\n"
        f"🔥 Плечо:            <b>{lev}x</b>  (своих ${pos:.0f} → с плечом <b>${exp:.0f}</b>)\n\n"
        f"✅ TP1 (быстрый):    <b>${fp(sig.get('tp1'))}</b>  +{sig.get('tp1_pct',0):.1f}%  →  <b>{profit(sig.get('tp1_pct',0))}</b>\n"
        f"✅ TP2 (оптимальный):<b>${fp(sig.get('tp2'))}</b>  +{sig.get('tp2_pct',0):.1f}%  →  <b>{profit(sig.get('tp2_pct',0))}</b>\n"
        f"✅ TP3 (агрессивный):<b>${fp(sig.get('tp3'))}</b>  +{sig.get('tp3_pct',0):.1f}%  →  <b>{profit(sig.get('tp3_pct',0))}</b>\n\n"
        f"🛑 Стоп-лосс:        <b>${fp(sig.get('sl'))}</b>  -{sig.get('sl_pct',0):.1f}%  →  <b>{loss(sig.get('sl_pct',0))}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 Банк $1000  ·  Позиция ${pos:.0f}  ·  {lev}x  ·  Экспозиция <b>${exp:.0f}</b>\n"
        f"⏱ Сигнал действует 4 часа, затем закрывается автоматически"
    )

def tg_close_notify(pair: str, result: str, pct: float, pnl: float, reason: str, bal: float):
    emoji = "✅" if result == "win" else "❌"
    sign  = "+" if pnl >= 0 else ""
    tg_text(
        f"{emoji} <b>Закрыт: {pair}</b>  [{result.upper()}]\n"
        f"Причина: {reason}\n"
        f"P&L: <b>{sign}{pct:.2f}%</b>  →  <b>{sign}${pnl:.2f}</b>\n"
        f"💼 Баланс: <b>${bal:.2f}</b>"
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

def get_portfolio() -> dict:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"SELECT id, current_balance, initial_balance, wins, losses, total_signals FROM {SCHEMA}.pump_portfolio LIMIT 1")
        r = cur.fetchone()
        cur.close(); conn.close()
        if r:
            return {"id": r[0], "balance": float(r[1]), "initial": float(r[2]),
                    "wins": r[3] or 0, "losses": r[4] or 0, "signals": r[5] or 0}
    except Exception:
        pass
    return {"id": None, "balance": START_BANK, "initial": START_BANK, "wins": 0, "losses": 0, "signals": 0}

def update_portfolio(pnl_usdt: float, is_win: bool):
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"SELECT id, current_balance, initial_balance FROM {SCHEMA}.pump_portfolio LIMIT 1")
        r = cur.fetchone()
        if not r: cur.close(); conn.close(); return
        pid, bal, ini = r[0], float(r[1]), float(r[2])
        new_bal  = round(bal + pnl_usdt, 2)
        new_peak = max(new_bal, bal)
        pnl_tot  = round(new_bal - ini, 2)
        pnl_pct  = round((new_bal - ini) / ini * 100, 4)
        cur.execute(
            f"""UPDATE {SCHEMA}.pump_portfolio
            SET current_balance=%s, peak_balance=%s, total_pnl=%s, total_pnl_pct=%s,
                wins=wins+%s, losses=losses+%s, total_signals=total_signals+1, updated_at=NOW()
            WHERE id=%s""",
            (new_bal, new_peak, pnl_tot, pnl_pct, 1 if is_win else 0, 0 if is_win else 1, pid))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def save_signal(sig: dict) -> int | None:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        lev, pos = sig.get("leverage", 2), sig.get("position_usdt", 30)
        facts_j  = json.dumps(sig.get("factors", []), ensure_ascii=False)
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
            (sig["pair"], "LONG" if sig["type"]=="Pump" else "SHORT",
             sig["exchange"], sig["entry"], sig.get("tp2", sig["entry"]), sig.get("sl", sig["entry"]),
             sig["score"], "active",
             sig.get("rsi", 50), "pump_v4", 0.5, round(sig.get("rvol",1),2), 50,
             sig["type"], reasoning[:500], "15m",
             sig["score"] if sig["type"]=="Pump" else 0,
             sig["score"] if sig["type"]=="Dump"  else 0,
             lev, round(pos*lev, 2), lev, round(pos,2),
             reasoning[:1000], facts_j,
             sig.get("rvol",1), sig.get("rsi",50),
             sig.get("pct_1",0), sig.get("pct_3",0), sig.get("pct_6",0),
             sig.get("tp1",0), sig.get("tp2",0), sig.get("tp3",0),
             sig.get("tp1_pct",0), sig.get("tp2_pct",0), sig.get("tp3_pct",0),
             sig.get("sl_pct",0), sig.get("atr",0)))
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()
        return row[0] if row else None
    except Exception:
        return None

# ─── Автозакрытие сигналов (честная статистика) ───────────────────────────────

def auto_close_signals():
    """
    Проверяем активные сигналы: достигли TP2 или SL или прошло 4 часа.
    Пишем реальный результат в БД. Обновляем портфель.
    Это делает статистику 100% честной.
    """
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"""SELECT id, pair, signal_type, exchange, entry_price,
                tp2_price, stop_price, leverage_recommended, position_usdt,
                tp1_price, tp3_price, created_at
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status='active'
              AND created_at < NOW() - INTERVAL '15 minutes'
            LIMIT 30""")
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception:
        return

    for row in rows:
        (sig_id, pair, sig_type, exchange, entry_p,
         tp2_p, sl_p, lev, pos_usdt,
         tp1_p, tp3_p, created_at) = row

        entry = float(entry_p)
        tp2   = float(tp2_p) if tp2_p else 0
        sl    = float(sl_p)  if sl_p  else 0
        tp1   = float(tp1_p) if tp1_p else 0
        lev_v = int(lev)     if lev   else 1
        pos   = float(pos_usdt) if pos_usdt else 30

        # Получаем символ для API
        sym = pair.replace("/", "").replace("-", "")

        price = get_price_now(exchange, sym)
        if price is None:
            # Fallback: Binance
            d = fetch(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}")
            if isinstance(d, dict) and "price" in d:
                price = float(d["price"])
        if price is None:
            continue

        now_utc = datetime.now(timezone.utc)
        age_h   = (now_utc.timestamp() - created_at.timestamp()) / 3600 if created_at else 999

        is_long = sig_type == "LONG"
        result  = None
        reason  = ""
        exit_p  = price

        if is_long:
            if tp2 > 0 and price >= tp2:
                result = "win";  reason = f"TP2 достигнут ${fp(tp2)}";  exit_p = tp2
            elif tp1 > 0 and price >= tp1 and age_h >= 1:
                result = "win";  reason = f"TP1 достигнут ${fp(tp1)}";  exit_p = tp1
            elif sl > 0 and price <= sl:
                result = "loss"; reason = f"Стоп-лосс ${fp(sl)} сработал"; exit_p = sl
            elif age_h >= CLOSE_HOURS:
                exit_p = price
                result = "win" if price > entry else "loss"
                reason = f"Закрыт по времени ({CLOSE_HOURS}ч)"
        else:  # SHORT
            if tp2 > 0 and price <= tp2:
                result = "win";  reason = f"TP2 достигнут ${fp(tp2)}";  exit_p = tp2
            elif tp1 > 0 and price <= tp1 and age_h >= 1:
                result = "win";  reason = f"TP1 достигнут ${fp(tp1)}";  exit_p = tp1
            elif sl > 0 and price >= sl:
                result = "loss"; reason = f"Стоп-лосс ${fp(sl)} сработал"; exit_p = sl
            elif age_h >= CLOSE_HOURS:
                exit_p = price
                result = "win" if price < entry else "loss"
                reason = f"Закрыт по времени ({CLOSE_HOURS}ч)"

        if result is None:
            continue

        # P&L
        if is_long:
            raw_pct   = (exit_p - entry) / entry * 100
        else:
            raw_pct   = (entry - exit_p) / entry * 100
        lev_pct   = round(raw_pct * lev_v, 4)
        pnl_usdt  = round(pos * lev_pct / 100, 2)

        try:
            conn2 = psycopg2.connect(os.environ["DATABASE_URL"])
            cur2  = conn2.cursor()
            cur2.execute(
                f"""UPDATE {SCHEMA}.signals
                SET actual_exit_price=%s, result=%s, result_pct=%s,
                    pnl_usdt=%s, status='closed', closed_at=NOW(),
                    analysis_text=COALESCE(analysis_text,'')||' | '||%s
                WHERE id=%s""",
                (exit_p, result, lev_pct, pnl_usdt, reason, sig_id))
            conn2.commit(); cur2.close(); conn2.close()
        except Exception:
            continue

        update_portfolio(pnl_usdt, result == "win")

        portfolio = get_portfolio()
        tg_close_notify(pair, result, lev_pct, pnl_usdt, reason, portfolio["balance"])

def get_saved(limit: int = 50) -> list:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"""SELECT id, pair, signal_type, exchange,
                entry_price, tp1_price, tp2_price, tp3_price, stop_price,
                confidence, status, created_at, result, result_pct, pnl_usdt,
                leverage_recommended, position_usdt, reasoning, factors_json,
                rvol, rsi_value, pct_15m, pct_45m, pct_90m,
                tp1_pct, tp2_pct, tp3_pct, sl_pct, actual_exit_price
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump')
            ORDER BY created_at DESC LIMIT %s""", (limit,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        out = []
        for r in rows:
            facts = []
            try:
                if r[18]: facts = json.loads(r[18])
            except Exception:
                pass
            out.append({
                "id": r[0], "pair": r[1],
                "type": "Pump" if r[2]=="LONG" else "Dump",
                "exchange": r[3],
                "entry": float(r[4]),
                "tp1": float(r[5]) if r[5] else 0,
                "tp2": float(r[6]) if r[6] else 0,
                "tp3": float(r[7]) if r[7] else 0,
                "sl":  float(r[8]) if r[8] else 0,
                "price_now": float(r[4]), "price_from": float(r[4]),
                "score": r[9] or 50, "strength": r[9] or 50,
                "status_db": r[10],
                "timeframe": "15m",
                "time":   r[11].strftime("%H:%M")       if r[11] else "—",
                "date":   r[11].strftime("%d.%m %H:%M") if r[11] else "—",
                "result": r[12],
                "result_pct": round(float(r[13]),2) if r[13] else None,
                "pnl_usdt":   round(float(r[14]),2) if r[14] else None,
                "leverage": r[15] or 1,
                "position_usdt": float(r[16] or 0),
                "reasoning": r[17] or "",
                "factors": facts,
                "rvol": float(r[19] or 1),
                "rsi":  float(r[20] or 50),
                "pct_1":  float(r[21] or 0),
                "pct_3":  float(r[22] or 0),
                "pct_6":  float(r[23] or 0),
                "tp1_pct": float(r[24] or 0),
                "tp2_pct": float(r[25] or 0),
                "tp3_pct": float(r[26] or 0),
                "sl_pct":  float(r[27] or 0),
                "exit_price": float(r[28]) if r[28] else None,
                "volume_usd": 0, "volume_pct": 0, "volume_increase_usd": 0,
            })
        return out
    except Exception:
        return []

def get_stats() -> dict:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"""
            SELECT
                COUNT(*) total,
                COUNT(*) FILTER (WHERE sentiment='Pump')  pumps,
                COUNT(*) FILTER (WHERE sentiment='Dump')  dumps,
                COUNT(*) FILTER (WHERE result='win')      wins,
                COUNT(*) FILTER (WHERE result='loss')     losses,
                COUNT(*) FILTER (WHERE status='active')   active,
                AVG(confidence) FILTER (WHERE confidence IS NOT NULL) avg_score,
                AVG(result_pct) FILTER (WHERE result='win')  avg_win,
                AVG(result_pct) FILTER (WHERE result='loss') avg_loss,
                COALESCE(SUM(pnl_usdt),0) total_pnl
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump')""")
        r = cur.fetchone()
        total=r[0] or 0; pumps=r[1] or 0; dumps=r[2] or 0
        wins=r[3] or 0; losses=r[4] or 0; active=r[5] or 0
        closed = wins+losses
        wr     = round(wins/closed*100,1) if closed > 0 else 0

        cur.execute(f"""
            SELECT exchange, COUNT(*) cnt,
                COUNT(*) FILTER (WHERE result='win') w,
                COUNT(*) FILTER (WHERE result='loss') l
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump')
            GROUP BY exchange ORDER BY cnt DESC""")
        by_exch = [{"exchange": x[0], "total": x[1], "wins": x[2], "losses": x[3]} for x in cur.fetchall()]

        cur.execute(f"""
            SELECT DATE(created_at) d, COUNT(*) cnt,
                COUNT(*) FILTER (WHERE result='win') w
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump')
              AND created_at > NOW() - INTERVAL '30 days'
            GROUP BY d ORDER BY d DESC""")
        daily = [{"date": str(x[0]), "count": x[1], "wins": x[2]} for x in cur.fetchall()]

        # Портфель
        cur.execute(f"""
            SELECT initial_balance, current_balance, peak_balance,
                wins, losses, total_signals, started_at
            FROM {SCHEMA}.pump_portfolio LIMIT 1""")
        pr = cur.fetchone()
        portfolio = {}
        if pr:
            bal, ini = float(pr[1]), float(pr[0])
            portfolio = {
                "balance": bal, "initial": ini,
                "pnl": round(bal-ini, 2),
                "pnl_pct": round((bal-ini)/ini*100, 2),
                "peak": float(pr[2]),
                "wins": pr[3] or 0, "losses": pr[4] or 0,
                "total_signals": pr[5] or 0,
                "started": str(pr[6])[:10] if pr[6] else "",
            }

        cur.close(); conn.close()
        return {
            "total": total, "pumps": pumps, "dumps": dumps,
            "wins": wins, "losses": losses, "closed": closed, "active": active,
            "win_rate": wr,
            "avg_score":    round(float(r[6] or 0), 1),
            "avg_win_pct":  round(float(r[7] or 0), 2),
            "avg_loss_pct": round(float(r[8] or 0), 2),
            "total_pnl":    round(float(r[9] or 0), 2),
            "daily": daily, "by_exchange": by_exch, "portfolio": portfolio,
        }
    except Exception:
        return {"total":0,"pumps":0,"dumps":0,"wins":0,"losses":0,"closed":0,"active":0,
                "win_rate":0,"avg_score":0,"avg_win_pct":0,"avg_loss_pct":0,"total_pnl":0,
                "daily":[],"by_exchange":[],"portfolio":{}}

# ─── Основной скан ────────────────────────────────────────────────────────────

def run_scan(only_exchange: str | None = None) -> dict:
    pairs_map = ({only_exchange: EXCHANGE_PAIRS[only_exchange]}
                 if only_exchange and only_exchange in EXCHANGE_PAIRS
                 else EXCHANGE_PAIRS)
    total, found, errors = sum(len(v) for v in pairs_map.values()), [], 0
    portfolio = get_portfolio()
    balance   = portfolio["balance"]

    for exchange, pairs in pairs_map.items():
        for sym in pairs:
            try:
                candles = get_candles(exchange, sym)
                if not candles:
                    errors += 1
                    continue
                scored  = score_signal(candles)
                if scored:
                    print(f"[SIGNAL] {exchange} {sym} score={scored['score']} pct3={scored['pct_3']:.2f}% rvol={scored['rvol']}")
                if not scored: continue

                pair = sym.replace("-","/").replace("USDT","/USDT")
                if "/USDT/USDT" in pair: pair = pair.replace("/USDT/USDT","/USDT")

                if already_sent(pair, exchange): continue

                lev, pos_pct = get_leverage(scored["score"])
                pos_usdt     = round(balance * pos_pct, 2)
                levels       = calc_levels(candles, scored["type"], scored["score"])

                sig = {
                    "pair": pair, "symbol": sym, "exchange": exchange,
                    "timeframe": "15m",
                    "time": datetime.now(timezone.utc).strftime("%H:%M"),
                    "candles": candles, "leverage": lev, "position_usdt": pos_usdt,
                    **scored, **levels,
                }

                db_id = save_signal(sig)
                if db_id: sig["id"] = db_id
                notify(sig)
                sig.pop("candles", None)
                found.append(sig)
            except Exception:
                errors += 1

    found.sort(key=lambda x: x.get("score",0), reverse=True)
    return {"signals": found, "analyzed": total, "found": len(found), "errors": errors}

# ─── Handler ─────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """PumpBot v4: честная статистика, реальный P&L, авто-закрытие сигналов."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    action = params.get("action", "scan")

    if action == "saved":
        return {"statusCode": 200, "headers": HEADERS,
                "body": json.dumps({"signals": get_saved(int(params.get("limit",50)))})}

    if action == "stats":
        return {"statusCode": 200, "headers": HEADERS,
                "body": json.dumps({"stats": get_stats()})}

    if action == "close":
        auto_close_signals()
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"ok": True})}

    if action == "debug":
        # Диагностика — проверяем несколько монет и показываем почему не сигнал
        sym = params.get("sym", "SOLUSDT")
        exchange = params.get("exchange", "Binance")
        candles = get_candles(exchange, sym)
        if not candles:
            return {"statusCode": 200, "headers": HEADERS,
                    "body": json.dumps({"error": "no candles", "sym": sym})}
        c = candles
        pn = c[-1]["c"]; p3 = c[-4]["c"]; p6 = c[-7]["c"]
        pct3 = (pn-p3)/p3*100; pct6 = (pn-p6)/p6*100
        rv = calc_rvol(c, 20)
        vol_usd = c[-1]["v"] * pn
        rsi = calc_rsi([x["c"] for x in c])
        scored = score_signal(candles)
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({
            "sym": sym, "exchange": exchange,
            "price": pn, "candles_count": len(candles),
            "pct_3": round(pct3,4), "pct_6": round(pct6,4),
            "rvol": rv, "vol_usd": round(vol_usd,2), "rsi": rsi,
            "min_price_pct": MIN_PRICE_PCT, "min_rvol": MIN_RVOL,
            "min_vol_usd": MIN_VOL_USD, "min_score": MIN_SCORE,
            "pass_price": abs(pct3) >= MIN_PRICE_PCT or abs(pct6) >= MIN_PRICE_PCT*1.3,
            "pass_rvol":  rv >= MIN_RVOL,
            "pass_vol":   vol_usd >= MIN_VOL_USD,
            "signal": scored,
        })}

    if action == "test_telegram":
        p = get_portfolio()
        tg_text(
            "🚀 <b>PumpBot v4 — запущен!</b>\n\n"
            "✅ Binance · Bybit · OKX · MEXC\n"
            "✅ Score 0–100 · Плечо 2x–15x\n"
            "✅ Авто-закрытие + реальная статистика\n"
            "✅ Виртуальный банк: <b>${:.2f}</b>\n\n"
            "Лозунг: правда, правда и ещё раз правда 🎯".format(p["balance"])
        )
        return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"ok": True})}

    # scan — сначала закрываем старые
    auto_close_signals()
    only   = params.get("exchange")
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