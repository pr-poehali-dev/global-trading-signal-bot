"""
Pump-детектор мирового уровня.
Анализирует 80+ пар на Binance каждые 5 минут.
Ищет реальные памп-активности: резкий рост цены + взрыв объёма.
Telegram-уведомления в формате: 🚀 Pump - PAIR, цена, объём, % роста.
"""
from __future__ import annotations
import json
import urllib.request
import math
import os
import psycopg2
from datetime import datetime, timezone

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json"
}

SCHEMA = "t_p73206386_global_trading_signa"

# Все пары для сканирования (топ альткоины на Binance)
PAIRS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    "DOGEUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT",
    "MATICUSDT","LTCUSDT","ATOMUSDT","NEARUSDT","APTUSDT",
    "ARBUSDT","OPUSDT","INJUSDT","SUIUSDT","SEIUSDT",
    "TIAUSDT","WLDUSDT","FETUSDT","RENDERUSDT","1000SHIBUSDT",
    "FTMUSDT","SANDUSDT","MANAUSDT","AXSUSDT","GALAUSDT",
    "ENAUSDT","JUPUSDT","STRKUSDT","ALTUSDT","DYMUSDT",
    "PYTHUSDT","WIFUSDT","BONKUSDT","PEPEUSDT","FLOKIUSDT",
    "ORDIUSDT","SATSUSDT","1000RATSUSDT","ACEUSDT","XAIUSDT",
    "PIXELUSDT","PORTALUSDT","MANTAUSDT","ZKUSDT","LISTAUSDT",
    "ZETAUSDT","AEVOUSDT","OMNIUSDT","REZUSDT","BBUSDT",
    "NOTUSDT","IOUSDT","ZKJUSDT","MOVEUSDT","MEUSDT",
    "TRUMPUSDT","MELANIAUSDT","PENGUUSDT","VIRTUALUSDT","AIUSDT",
    "CATIUSDT","HMSTRUSDT","EIGENUSDT","SCRUSDT","NEIROUSDT",
    "IOSTUSDT","CHRUSDT","HBARUSDT","ICPUSDT","ALGOUSDT",
    "VETUSDT","XLMUSDT","ETCUSDT","FILUSDT","AAVEUSDT",
    "UNIUSDT","MKRUSDT","CRVUSDT","LDOUSDT","SNXUSDT",
]

# Пороги для определения памп-сигнала
PUMP_PRICE_PCT = 3.0    # цена выросла минимум на 3% за последние свечи
PUMP_VOLUME_PCT = 30.0  # объём вырос минимум на 30% vs среднее
MIN_VOLUME_USD = 500_000  # минимальный объём $500k (фильтр шлака)

def fetch_url(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PumpBot/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def get_candles(symbol: str, interval: str = "15m", limit: int = 50):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = fetch_url(url)
    if not data:
        return []
    return [{
        "time": int(c[0]),
        "open": float(c[1]),
        "high": float(c[2]),
        "low": float(c[3]),
        "close": float(c[4]),
        "volume": float(c[5]),
        "quote_volume": float(c[7])
    } for c in data]

def get_ticker_24h(symbol: str):
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
    return fetch_url(url)

def detect_pump(symbol: str) -> dict | None:
    candles = get_candles(symbol, "15m", 50)
    if len(candles) < 20:
        return None

    # Текущие данные
    current = candles[-1]
    prev_candles = candles[:-1]

    price_now = current["close"]
    price_3ago = candles[-4]["close"] if len(candles) >= 4 else candles[0]["close"]
    price_6ago = candles[-7]["close"] if len(candles) >= 7 else candles[0]["close"]

    # Рост цены за последние 3 и 6 свечей (45 и 90 минут)
    price_pct_3 = (price_now - price_3ago) / price_3ago * 100 if price_3ago > 0 else 0
    price_pct_6 = (price_now - price_6ago) / price_6ago * 100 if price_6ago > 0 else 0

    # Объём текущей свечи vs среднее за 20 предыдущих свечей
    avg_volume = sum(c["quote_volume"] for c in prev_candles[-20:]) / 20
    curr_volume_usd = current["quote_volume"]
    volume_pct = (curr_volume_usd - avg_volume) / avg_volume * 100 if avg_volume > 0 else 0

    # Объём предыдущей свечи тоже растёт?
    prev_volume_usd = candles[-2]["quote_volume"] if len(candles) >= 2 else 0
    total_pump_volume = curr_volume_usd + prev_volume_usd

    # Фильтры: минимальный объём
    if curr_volume_usd < MIN_VOLUME_USD:
        return None

    # Основной критерий памп-сигнала
    price_pump = price_pct_3 >= PUMP_PRICE_PCT or price_pct_6 >= PUMP_PRICE_PCT * 1.5
    volume_pump = volume_pct >= PUMP_VOLUME_PCT

    if not (price_pump and volume_pump):
        return None

    # Дополнительная проверка: цена идёт вверх на нескольких последних свечах
    last_3_closes = [c["close"] for c in candles[-4:-1]]
    if len(last_3_closes) >= 2 and last_3_closes[-1] < last_3_closes[0]:
        return None

    # Считаем силу памп-сигнала (0-100)
    price_score = min(price_pct_3 / (PUMP_PRICE_PCT * 3) * 50, 50)
    volume_score = min(volume_pct / (PUMP_VOLUME_PCT * 3) * 50, 50)
    strength = int(price_score + volume_score)
    strength = max(50, min(95, strength))

    # Определяем тип: Pump (рост) или Dump (падение)
    signal_type = "Pump" if price_pct_3 > 0 else "Dump"

    # Пара в читаемом формате
    pair = symbol.replace("USDT", "/USDT")

    # Получаем 24h данные для доп. инфо
    ticker = get_ticker_24h(symbol)
    change_24h = float(ticker.get("priceChangePercent", 0)) if ticker else 0
    volume_24h = float(ticker.get("quoteVolume", 0)) if ticker else 0
    price_from = price_3ago
    volume_increase_usd = curr_volume_usd - avg_volume

    return {
        "pair": pair,
        "symbol": symbol,
        "type": signal_type,
        "price_now": round(price_now, 8),
        "price_from": round(price_from, 8),
        "price_pct": round(price_pct_3, 2),
        "price_pct_6": round(price_pct_6, 2),
        "volume_usd": round(curr_volume_usd, 0),
        "volume_pct": round(volume_pct, 2),
        "volume_increase_usd": round(volume_increase_usd, 0),
        "volume_24h": round(volume_24h, 0),
        "change_24h": round(change_24h, 2),
        "strength": strength,
        "timeframe": "15m",
        "exchange": "Binance",
        "time": datetime.now(timezone.utc).strftime("%H:%M"),
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }

def fmt_usd(value: float) -> str:
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value/1_000:.2f}K"
    return f"${value:.2f}"

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

def notify_pump(sig: dict):
    emoji = "🚀" if sig["type"] == "Pump" else "📉"
    dot = "🟢🟢" if sig["type"] == "Pump" else "🔴🔴"
    direction = "выросла" if sig["type"] == "Pump" else "упала"
    text = (
        f"{emoji} <b>{sig['type']} - {sig['pair']}</b>\n"
        f"Pump Activity on {sig['pair']} {dot}\n\n"
        f"💰 Price: <b>${sig['price_from']:.6g}</b> ➜ <b>${sig['price_now']:.6g}</b> "
        f"(<b>+{sig['price_pct']}%</b>)\n"
        f"📊 Volume: <b>{fmt_usd(sig['volume_usd'])}</b> (+{sig['volume_pct']:.1f}%)\n"
        f"Volume increased by <b>{fmt_usd(sig['volume_increase_usd'])}</b> ⬆️\n"
        f"⏱ Timeframe: 15m | Exchange: {sig['exchange']}\n"
        f"💪 Сила сигнала: {sig['strength']}%"
    )
    send_telegram(text)

def save_pump_signal(sig: dict) -> int | None:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(
            f"""INSERT INTO {SCHEMA}.signals
            (pair, signal_type, exchange, entry_price, target_price, stop_price,
             confidence, status, rsi, macd_signal, bb_position, volume_ratio,
             fear_greed, sentiment, analysis_text, timeframe, score_bull, score_bear,
             leverage, position_size)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (
                sig["pair"],
                "LONG" if sig["type"] == "Pump" else "SHORT",
                sig["exchange"],
                sig["price_now"],
                round(sig["price_now"] * 1.05, 8),
                round(sig["price_now"] * 0.97, 8),
                sig["strength"],
                "active",
                50.0,
                "pump",
                0.5,
                round(sig["volume_pct"] / 100, 2),
                50,
                sig["type"],
                f"Price +{sig['price_pct']}% | Volume +{sig['volume_pct']:.1f}% | 15m pump detected",
                "15m",
                sig["strength"] if sig["type"] == "Pump" else 0,
                sig["strength"] if sig["type"] == "Dump" else 0,
                1,
                0
            )
        )
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()
        return row[0] if row else None
    except Exception:
        return None

def get_recent_pump_signals(limit: int = 30) -> list:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(
            f"""SELECT id, pair, signal_type, exchange, entry_price, target_price, stop_price,
            confidence, status, analysis_text, created_at, result, result_pct, pnl_usdt,
            score_bull, score_bear
            FROM {SCHEMA}.signals
            WHERE status != 'archived' AND sentiment IN ('Pump','Dump')
            ORDER BY created_at DESC LIMIT %s""", (limit,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [{
            "id": r[0],
            "pair": r[1],
            "type": "Pump" if r[2] == "LONG" else "Dump",
            "exchange": r[3],
            "price_from": float(r[4]),
            "price_now": float(r[4]),
            "price_pct": round(float(r[8] or 0), 2) if r[8] == "active" else round(float(r[12] or 0), 2),
            "volume_usd": 0,
            "volume_pct": round(float(r[7] or 0), 1),
            "strength": r[7] or 50,
            "analysis": r[9] or "",
            "status": r[10].strftime("%H:%M %d.%m") if r[10] else "—",
            "result": r[11],
            "result_pct": round(float(r[12]), 2) if r[12] else None,
            "pnl_usdt": round(float(r[13]), 2) if r[13] else None,
            "time": r[10].strftime("%H:%M") if r[10] else "—",
            "date": r[10].strftime("%d.%m %H:%M") if r[10] else "—",
        } for r in rows]
    except Exception:
        return []

def check_already_notified(symbol: str, window_minutes: int = 30) -> bool:
    """Проверяем, не отправляли ли мы уже сигнал по этой паре недавно."""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(
            f"""SELECT COUNT(*) FROM {SCHEMA}.signals
            WHERE pair = %s AND sentiment IN ('Pump','Dump')
            AND created_at > NOW() - INTERVAL '{window_minutes} minutes'""",
            (symbol.replace("USDT", "/USDT"),)
        )
        count = cur.fetchone()[0]
        cur.close(); conn.close()
        return count > 0
    except Exception:
        return False

def get_stats() -> dict:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*) as total,
                COUNT(*) FILTER (WHERE sentiment = 'Pump') as pumps,
                COUNT(*) FILTER (WHERE sentiment = 'Dump') as dumps,
                COUNT(*) FILTER (WHERE result = 'win') as wins,
                COUNT(*) FILTER (WHERE result = 'loss') as losses
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status != 'archived'
        """)
        row = cur.fetchone()
        total = row[0] or 0; pumps = row[1] or 0; dumps = row[2] or 0
        wins = row[3] or 0; losses = row[4] or 0
        closed = wins + losses
        win_rate = round(wins / closed * 100, 1) if closed > 0 else 0

        cur.execute(f"""
            SELECT DATE(created_at) as d, COUNT(*) as cnt
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump') AND status != 'archived'
            AND created_at > NOW() - INTERVAL '7 days'
            GROUP BY d ORDER BY d DESC
        """)
        daily = [{"date": str(r[0]), "count": r[1]} for r in cur.fetchall()]
        cur.close(); conn.close()
        return {
            "total": total, "pumps": pumps, "dumps": dumps,
            "wins": wins, "losses": losses, "closed": closed,
            "win_rate": win_rate, "daily": daily
        }
    except Exception:
        return {"total": 0, "pumps": 0, "dumps": 0, "wins": 0, "losses": 0,
                "closed": 0, "win_rate": 0, "daily": []}

def handler(event: dict, context) -> dict:
    """Pump-детектор: сканирует 80+ пар на Binance, находит памп-активность."""
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

    # action == "scan" или "generate"
    found_signals = []
    errors = 0

    for symbol in PAIRS:
        try:
            sig = detect_pump(symbol)
            if sig:
                already = check_already_notified(symbol)
                if not already:
                    db_id = save_pump_signal(sig)
                    if db_id:
                        sig["id"] = db_id
                        notify_pump(sig)
                    found_signals.append(sig)
        except Exception:
            errors += 1
            continue

    found_signals.sort(key=lambda x: x.get("strength", 0), reverse=True)

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps({
            "signals": found_signals,
            "analyzed": len(PAIRS),
            "found": len(found_signals),
            "errors": errors,
            "scanned_at": datetime.now(timezone.utc).isoformat()
        })
    }