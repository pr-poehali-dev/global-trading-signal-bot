"""
MEXC Auto-Bot v1 — копирует сигналы PumpBot и торгует фьючерсами MEXC.

Настройки (фиксированные):
  - Плечо: 10x
  - Размер позиции: 15% от баланса USDT
  - TP2 из сигнала (оптимальная цель)
  - SL из сигнала
  - Timeout: 4 часа → закрываем по рынку

Запуск/стоп: через DB-флаг is_running (одна кнопка на сайте).
Работает 24/7 через cron (bot-cron вызывает ?action=tick каждые 5 мин).

MEXC Futures API v1:
  https://futures.mexc.com/api/v1/
"""
from __future__ import annotations
import json
import os
import hashlib
import hmac
import time
import urllib.request
import urllib.parse
import psycopg2
from datetime import datetime, timezone

HEADERS_RESP = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}
SCHEMA   = "t_p73206386_global_trading_signa"
LEVERAGE = 10
POS_PCT  = 0.15      # 15% баланса на сделку
MAX_OPEN = 3         # не более 3 одновременных позиций
TIMEOUT_H = 4        # закрывать через 4 часа если нет TP/SL
MIN_SCORE = 70       # минимальный score для входа
MEXC_FUTURES = "https://contract.mexc.com/api/v1"

# ─── MEXC Futures API ─────────────────────────────────────────────────────────

def _mexc_sign(params: dict, secret: str) -> str:
    """Подпись MEXC Futures: HMAC-SHA256 от sorted query string."""
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()

def mexc_request(method: str, path: str, params: dict | None = None, signed: bool = False) -> dict | None:
    api_key = os.environ.get("MEXC_API_KEY", "")
    secret  = os.environ.get("MEXC_SECRET_KEY", "")
    if not api_key or not secret:
        return None

    params = params or {}
    if signed:
        params["timestamp"] = str(int(time.time() * 1000))
        sig = _mexc_sign(params, secret)
        params["signature"] = sig

    url = f"{MEXC_FUTURES}{path}"
    headers = {
        "User-Agent": "MexcBot/1.0",
        "Content-Type": "application/json",
        "ApiKey": api_key,
        "Request-Time": str(int(time.time() * 1000)),
    }

    try:
        if method == "GET":
            qs  = urllib.parse.urlencode(params)
            req = urllib.request.Request(f"{url}?{qs}" if qs else url, headers=headers)
        else:
            body = json.dumps(params).encode()
            req  = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def get_futures_balance() -> float:
    """Баланс USDT на фьючерсном счёте MEXC."""
    r = mexc_request("GET", "/account/assets", signed=True)
    if isinstance(r, dict) and r.get("success"):
        for asset in (r.get("data") or []):
            if asset.get("currency") == "USDT":
                return float(asset.get("availableBalance", 0))
    return 0.0

def get_futures_price(symbol: str) -> float | None:
    """Текущая цена фьючерса."""
    r = mexc_request("GET", "/market/ticker", {"symbol": symbol})
    if isinstance(r, dict) and r.get("success"):
        data = r.get("data")
        if data and isinstance(data, list):
            for item in data:
                if item.get("symbol") == symbol:
                    return float(item.get("lastPrice", 0) or 0)
        elif isinstance(data, dict):
            return float(data.get("lastPrice", 0) or 0)
    return None

def set_leverage(symbol: str, leverage: int) -> bool:
    """Устанавливаем плечо для пары."""
    r = mexc_request("POST", "/position/change_leverage", {
        "symbol": symbol, "leverage": leverage, "openType": 1  # 1=isolated
    }, signed=True)
    return isinstance(r, dict) and r.get("success", False)

def open_position(symbol: str, direction: str, qty: float) -> dict | None:
    """
    Открываем позицию.
    direction: "LONG" → openType=1(long), "SHORT" → openType=3(short)
    """
    open_type = 1 if direction == "LONG" else 3
    r = mexc_request("POST", "/order/submit", {
        "symbol":    symbol,
        "side":      open_type,    # 1=open_long, 2=close_long, 3=open_short, 4=close_short
        "openType":  1,            # 1=isolated
        "type":      5,            # 5=market order
        "vol":       qty,          # количество контрактов
        "leverage":  LEVERAGE,
    }, signed=True)
    return r if isinstance(r, dict) else None

def close_position(symbol: str, direction: str, qty: float) -> dict | None:
    """Закрываем позицию по рынку."""
    close_side = 2 if direction == "LONG" else 4  # 2=close_long, 4=close_short
    r = mexc_request("POST", "/order/submit", {
        "symbol":   symbol,
        "side":     close_side,
        "openType": 1,
        "type":     5,
        "vol":      qty,
        "leverage": LEVERAGE,
    }, signed=True)
    return r if isinstance(r, dict) else None

def to_mexc_symbol(pair: str) -> str:
    """SOL/USDT → SOL_USDT."""
    return pair.replace("/", "_")

def calc_qty(balance: float, price: float, leverage: int) -> float:
    """Количество контрактов = (баланс * pos_pct * leverage) / price."""
    if price <= 0: return 0
    notional = balance * POS_PCT * leverage
    qty = notional / price
    # Округляем до разумного кол-ва знаков
    if qty >= 100:  return round(qty, 1)
    if qty >= 10:   return round(qty, 2)
    if qty >= 1:    return round(qty, 3)
    return round(qty, 4)

# ─── БД ───────────────────────────────────────────────────────────────────────

def get_bot_state() -> dict:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"SELECT is_running, leverage, position_pct, balance_usdt FROM {SCHEMA}.mexc_bot_state LIMIT 1")
        r = cur.fetchone()
        cur.close(); conn.close()
        return {"running": bool(r[0]), "leverage": r[1], "pos_pct": float(r[2]), "balance": float(r[3] or 0)} if r else {"running": False}
    except Exception:
        return {"running": False}

def set_bot_running(running: bool):
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        if running:
            cur.execute(f"UPDATE {SCHEMA}.mexc_bot_state SET is_running=true, started_at=NOW(), updated_at=NOW()")
        else:
            cur.execute(f"UPDATE {SCHEMA}.mexc_bot_state SET is_running=false, stopped_at=NOW(), updated_at=NOW()")
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def update_balance_db(balance: float):
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"UPDATE {SCHEMA}.mexc_bot_state SET balance_usdt=%s, updated_at=NOW()", (balance,))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def get_open_count() -> int:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.mexc_bot_trades WHERE status='open'")
        n = cur.fetchone()[0]
        cur.close(); conn.close()
        return n
    except Exception:
        return 0

def already_trading(symbol: str) -> bool:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.mexc_bot_trades WHERE symbol=%s AND status='open'", (symbol,))
        n = cur.fetchone()[0]
        cur.close(); conn.close()
        return n > 0
    except Exception:
        return True

def save_trade(pair: str, symbol: str, direction: str, entry: float, qty: float,
               pos_usdt: float, tp1: float, tp2: float, sl: float,
               tp1_pct: float, tp2_pct: float, sl_pct: float,
               score: int, factors: list, order_id: str,
               signal_id: int | None) -> int | None:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"""INSERT INTO {SCHEMA}.mexc_bot_trades
            (signal_id, pair, symbol, direction, entry_price, qty, position_usdt, leverage,
             tp1_price, tp2_price, sl_price, tp1_pct, tp2_pct, sl_pct,
             score, factors_json, mexc_order_id, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'open')
            RETURNING id""",
            (signal_id, pair, symbol, direction, entry, qty, pos_usdt, LEVERAGE,
             tp1, tp2, sl, tp1_pct, tp2_pct, sl_pct,
             score, json.dumps(factors, ensure_ascii=False), order_id))
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()
        return row[0] if row else None
    except Exception:
        return None

def close_trade_db(trade_id: int, exit_price: float, pnl_usdt: float, pnl_pct: float, reason: str):
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"""UPDATE {SCHEMA}.mexc_bot_trades
            SET exit_price=%s, pnl_usdt=%s, pnl_pct=%s, close_reason=%s,
                status=%s, closed_at=NOW()
            WHERE id=%s""",
            (exit_price, round(pnl_usdt,2), round(pnl_pct,4), reason,
             "profit" if pnl_usdt >= 0 else "loss", trade_id))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def get_open_trades() -> list:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"""SELECT id, pair, symbol, direction, entry_price, qty, position_usdt,
                tp1_price, tp2_price, sl_price, opened_at, mexc_order_id
            FROM {SCHEMA}.mexc_bot_trades WHERE status='open'
            ORDER BY opened_at""")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [{
            "id": r[0], "pair": r[1], "symbol": r[2], "direction": r[3],
            "entry": float(r[4]), "qty": float(r[5]), "pos_usdt": float(r[6]),
            "tp1": float(r[7]) if r[7] else 0,
            "tp2": float(r[8]) if r[8] else 0,
            "sl":  float(r[9]) if r[9] else 0,
            "opened_at": r[10],
            "order_id":  r[11] or "",
        } for r in rows]
    except Exception:
        return []

def get_recent_signals(limit: int = 10) -> list:
    """Берём последние активные сигналы из AI-бота."""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(
            f"""SELECT id, pair, signal_type, entry_price, tp1_price, tp2_price, stop_price,
                tp1_pct, tp2_pct, sl_pct, confidence, factors_json, exchange
            FROM {SCHEMA}.signals
            WHERE sentiment IN ('Pump','Dump')
              AND status = 'active'
              AND confidence >= %s
              AND created_at > NOW() - INTERVAL '10 minutes'
              AND id NOT IN (SELECT signal_id FROM {SCHEMA}.mexc_bot_trades WHERE signal_id IS NOT NULL)
            ORDER BY confidence DESC
            LIMIT %s""",
            (MIN_SCORE, limit))
        rows = cur.fetchall()
        cur.close(); conn.close()
        out = []
        for r in rows:
            factors = []
            try:
                if r[11]: factors = json.loads(r[11])
            except Exception:
                pass
            out.append({
                "id": r[0], "pair": r[1],
                "direction": "LONG" if r[2] == "LONG" else "SHORT",
                "entry": float(r[3]),
                "tp1": float(r[4]) if r[4] else 0,
                "tp2": float(r[5]) if r[5] else 0,
                "sl":  float(r[6]) if r[6] else 0,
                "tp1_pct": float(r[7] or 0),
                "tp2_pct": float(r[8] or 0),
                "sl_pct":  float(r[9] or 0),
                "score":   r[10] or 70,
                "factors": factors,
                "exchange": r[12],
            })
        return out
    except Exception:
        return []

def get_bot_stats() -> dict:
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*) total,
                COUNT(*) FILTER (WHERE status='profit') wins,
                COUNT(*) FILTER (WHERE status='loss')   losses,
                COUNT(*) FILTER (WHERE status='open')   open_cnt,
                COALESCE(SUM(pnl_usdt) FILTER (WHERE status IN ('profit','loss')), 0) pnl,
                COALESCE(AVG(pnl_pct)  FILTER (WHERE status='profit'), 0) avg_win,
                COALESCE(AVG(pnl_pct)  FILTER (WHERE status='loss'),   0) avg_loss
            FROM {SCHEMA}.mexc_bot_trades""")
        r = cur.fetchone()
        wins = r[1] or 0; losses = r[2] or 0; closed = wins + losses

        cur.execute(f"""
            SELECT id, pair, direction, entry_price, tp2_price, sl_price,
                position_usdt, opened_at, score
            FROM {SCHEMA}.mexc_bot_trades WHERE status='open'
            ORDER BY opened_at DESC""")
        open_trades = [{
            "id": x[0], "pair": x[1], "direction": x[2],
            "entry": float(x[3]), "tp2": float(x[4]) if x[4] else 0,
            "sl":    float(x[5]) if x[5] else 0,
            "pos":   float(x[6]), "score": x[8] or 0,
            "opened": x[7].strftime("%d.%m %H:%M") if x[7] else "—",
        } for x in cur.fetchall()]

        cur.execute(f"""
            SELECT id, pair, direction, pnl_usdt, pnl_pct, close_reason, closed_at, score
            FROM {SCHEMA}.mexc_bot_trades
            WHERE status IN ('profit','loss')
            ORDER BY closed_at DESC LIMIT 20""")
        history = [{
            "id": x[0], "pair": x[1], "direction": x[2],
            "pnl": float(x[3] or 0), "pnl_pct": float(x[4] or 0),
            "reason": x[5] or "", "score": x[7] or 0,
            "closed": x[6].strftime("%d.%m %H:%M") if x[6] else "—",
        } for x in cur.fetchall()]

        state = get_bot_state()
        cur.close(); conn.close()
        return {
            "running": state["running"],
            "balance": state["balance"],
            "total": r[0] or 0, "wins": wins, "losses": losses,
            "open": r[3] or 0, "closed": closed,
            "win_rate": round(wins/closed*100, 1) if closed > 0 else 0,
            "total_pnl": round(float(r[4]), 2),
            "avg_win":  round(float(r[5]), 2),
            "avg_loss": round(float(r[6]), 2),
            "open_trades": open_trades,
            "history": history,
        }
    except Exception as e:
        return {"running": False, "balance": 0, "total": 0, "wins": 0, "losses": 0,
                "open": 0, "closed": 0, "win_rate": 0, "total_pnl": 0,
                "avg_win": 0, "avg_loss": 0, "open_trades": [], "history": [], "error": str(e)}

# ─── Telegram ─────────────────────────────────────────────────────────────────

def tg(text: str):
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN",""), os.environ.get("TELEGRAM_CHAT_ID","")
    if not token or not chat_id: return
    try:
        body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=6)
    except Exception:
        pass

def fp(p: float) -> str:
    if not p: return "—"
    if p >= 1000: return f"{p:,.2f}"
    if p >= 1:    return f"{p:.4f}"
    if p >= 0.001: return f"{p:.6f}"
    return f"{p:.8f}"

# ─── Основная логика ──────────────────────────────────────────────────────────

def check_and_close_positions(balance: float) -> int:
    """Проверяем открытые позиции — TP/SL/timeout."""
    trades = get_open_trades()
    closed = 0
    now_utc = datetime.now(timezone.utc)

    for t in trades:
        price = get_futures_price(t["symbol"])
        if price is None or price <= 0:
            continue

        age_h   = (now_utc.timestamp() - t["opened_at"].timestamp()) / 3600 if t["opened_at"] else 99
        entry   = t["entry"]
        tp2     = t["tp2"]
        tp1     = t["tp1"]
        sl      = t["sl"]
        is_long = t["direction"] == "LONG"
        reason  = None
        exit_p  = price

        if is_long:
            if tp2 > 0 and price >= tp2:
                reason = f"✅ TP2 достигнут ${fp(tp2)}"; exit_p = tp2
            elif tp1 > 0 and price >= tp1 and age_h >= 0.5:
                reason = f"✅ TP1 достигнут ${fp(tp1)}"; exit_p = tp1
            elif sl > 0 and price <= sl:
                reason = f"🛑 Стоп-лосс ${fp(sl)}"; exit_p = sl
            elif age_h >= TIMEOUT_H:
                reason = f"⏱ Таймаут {TIMEOUT_H}ч"
        else:
            if tp2 > 0 and price <= tp2:
                reason = f"✅ TP2 достигнут ${fp(tp2)}"; exit_p = tp2
            elif tp1 > 0 and price <= tp1 and age_h >= 0.5:
                reason = f"✅ TP1 достигнут ${fp(tp1)}"; exit_p = tp1
            elif sl > 0 and price >= sl:
                reason = f"🛑 Стоп-лосс ${fp(sl)}"; exit_p = sl
            elif age_h >= TIMEOUT_H:
                reason = f"⏱ Таймаут {TIMEOUT_H}ч"

        if reason is None:
            continue

        # Закрываем на бирже
        close_position(t["symbol"], t["direction"], t["qty"])

        # P&L
        if is_long:
            raw_pct = (exit_p - entry) / entry * 100
        else:
            raw_pct = (entry - exit_p) / entry * 100
        lev_pct = round(raw_pct * LEVERAGE, 4)
        pnl_u   = round(t["pos_usdt"] * lev_pct / 100, 2)

        close_trade_db(t["id"], exit_p, pnl_u, lev_pct, reason)

        sign = "+" if pnl_u >= 0 else ""
        tg(
            f"{'🟢' if pnl_u >= 0 else '🔴'} <b>MEXC Бот · {t['pair']}</b> [{t['direction']}]\n"
            f"Закрыт: {reason}\n"
            f"Вход: ${fp(entry)}  →  Выход: ${fp(exit_p)}\n"
            f"P&L: <b>{sign}{lev_pct:.2f}%</b>  →  <b>{sign}${pnl_u:.2f}</b>\n"
            f"Позиция: ${t['pos_usdt']:.0f} × {LEVERAGE}x = ${t['pos_usdt']*LEVERAGE:.0f}"
        )
        closed += 1

    return closed

def open_new_positions(balance: float) -> int:
    """Открываем позиции по свежим сигналам."""
    open_cnt = get_open_count()
    if open_cnt >= MAX_OPEN:
        return 0

    signals = get_recent_signals(10)
    opened  = 0

    for sig in signals:
        if get_open_count() >= MAX_OPEN:
            break

        pair   = sig["pair"]
        symbol = to_mexc_symbol(pair)  # SOL/USDT → SOL_USDT

        if already_trading(symbol):
            continue

        price = get_futures_price(symbol)
        if price is None or price <= 0:
            continue

        qty = calc_qty(balance, price, LEVERAGE)
        if qty <= 0:
            continue

        pos_usdt = round(balance * POS_PCT, 2)

        # Устанавливаем плечо
        set_leverage(symbol, LEVERAGE)

        # Открываем ордер
        result = open_position(symbol, sig["direction"], qty)
        order_id = ""
        if isinstance(result, dict) and result.get("success"):
            order_id = str(result.get("data", {}).get("orderId", "") if isinstance(result.get("data"), dict) else "")
        elif isinstance(result, dict) and result.get("error"):
            tg(f"⚠️ MEXC Бот: ошибка открытия {pair}\n{result['error'][:200]}")
            continue

        # Сохраняем в БД
        trade_id = save_trade(
            pair=pair, symbol=symbol, direction=sig["direction"],
            entry=price, qty=qty, pos_usdt=pos_usdt,
            tp1=sig["tp1"], tp2=sig["tp2"], sl=sig["sl"],
            tp1_pct=sig["tp1_pct"], tp2_pct=sig["tp2_pct"], sl_pct=sig["sl_pct"],
            score=sig["score"], factors=sig["factors"], order_id=order_id,
            signal_id=sig["id"],
        )

        exp = round(pos_usdt * LEVERAGE, 0)
        tg(
            f"🚀 <b>MEXC Бот · Открыта позиция</b>\n\n"
            f"{'📈 LONG' if sig['direction']=='LONG' else '📉 SHORT'}  <b>{pair}</b>\n"
            f"Score: {sig['score']}/100  ·  MEXC Futures\n\n"
            f"📌 Вход:  <b>${fp(price)}</b>\n"
            f"🔥 Плечо: <b>{LEVERAGE}x</b>  (${pos_usdt:.0f} → <b>${exp:.0f}</b>)\n"
            f"📦 Кол-во: {qty}\n\n"
            f"✅ TP1: ${fp(sig['tp1'])}  (+{sig['tp1_pct']:.1f}%)\n"
            f"✅ TP2: ${fp(sig['tp2'])}  (+{sig['tp2_pct']:.1f}%)\n"
            f"🛑 SL:  ${fp(sig['sl'])}  (-{sig['sl_pct']:.1f}%)"
        )
        opened += 1

    return opened

def run_tick() -> dict:
    """Один тик бота: проверяем позиции + открываем новые."""
    state = get_bot_state()
    if not state["running"]:
        return {"skipped": True, "reason": "bot is stopped"}

    # Обновляем баланс
    balance = get_futures_balance()
    if balance > 0:
        update_balance_db(balance)
    else:
        balance = state["balance"] or 100

    closed = check_and_close_positions(balance)
    opened = open_new_positions(balance)

    return {
        "balance": balance,
        "closed_trades": closed,
        "opened_trades": opened,
        "open_count": get_open_count(),
    }

# ─── Handler ─────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """MEXC Auto-Bot: запуск/стоп/статус/тик."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS_RESP, "body": ""}

    params = event.get("queryStringParameters") or {}
    action = params.get("action", "stats")

    if action == "start":
        bal = get_futures_balance()
        if bal > 0:
            update_balance_db(bal)
        set_bot_running(True)
        tg(
            "🟢 <b>MEXC Бот запущен!</b>\n\n"
            f"💼 Баланс фьючерсов: <b>${bal:.2f} USDT</b>\n"
            f"🔥 Плечо: <b>{LEVERAGE}x</b>\n"
            f"📊 На сделку: <b>{int(POS_PCT*100)}%</b> = ${bal*POS_PCT:.2f}\n"
            f"🔁 Макс одновременных: <b>{MAX_OPEN}</b>\n"
            f"⏱ Таймаут: <b>{TIMEOUT_H} часа</b>\n\n"
            "Копирую сигналы PumpBot 24/7..."
        )
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps({"ok": True, "running": True, "balance": bal})}

    if action == "stop":
        # Закрываем все открытые позиции
        bal = get_futures_balance()
        open_trades = get_open_trades()
        for t in open_trades:
            close_position(t["symbol"], t["direction"], t["qty"])
            close_trade_db(t["id"], t["entry"], 0, 0, "Бот остановлен вручную")
        set_bot_running(False)
        tg(
            f"🔴 <b>MEXC Бот остановлен.</b>\n"
            f"Закрыто позиций: {len(open_trades)}\n"
            f"Баланс: ${bal:.2f} USDT"
        )
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps({"ok": True, "running": False, "closed": len(open_trades)})}

    if action == "tick":
        result = run_tick()
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps(result)}

    if action == "stats":
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps(get_bot_stats())}

    if action == "balance":
        bal = get_futures_balance()
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps({"balance": bal})}

    return {"statusCode": 400, "headers": HEADERS_RESP,
            "body": json.dumps({"error": "unknown action"})}
