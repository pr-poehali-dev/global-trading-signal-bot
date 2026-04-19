"""
MEXC Auto-Bot v2 — копирует сигналы PumpBot и торгует фьючерсами MEXC.

Правила торговли:
  - Биржа:        MEXC Futures (contract.mexc.com)
  - Плечо:        10x (isolated)
  - Позиция:      15% от баланса USDT
  - Цель:         TP2 из сигнала
  - Стоп:         SL из сигнала
  - Таймаут:      4 часа → закрыть по рынку
  - Макс сделок:  3 одновременно
  - Мин. score:   70/100

MEXC Futures API v1:
  Base: https://contract.mexc.com/api/v1
  Auth: headers ApiKey + Request-Time + Signature
  Sign: HMAC-SHA256(accessKey + timestamp + body_json_string)
  POST body: JSON, GET params: query string (sorted dict order)
"""
from __future__ import annotations
import json
import os
import hashlib
import hmac as hmac_lib
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
SCHEMA    = "t_p73206386_global_trading_signa"
# Дефолты (берутся из DB при каждом тике)
LEVERAGE  = 10
POS_PCT   = 0.15
MAX_OPEN  = 3
TIMEOUT_H = 4
MIN_SCORE = 70
BASE_URL  = "https://contract.mexc.com/api/v1"

# ─── MEXC Futures Auth ────────────────────────────────────────────────────────

def _sign(api_key: str, secret: str, timestamp: str, param_str: str) -> str:
    """
    MEXC Futures подпись:
      target = accessKey + timestamp + paramString
      signature = HMAC-SHA256(target, secretKey).hexdigest()

    Для POST: paramString = тело JSON (строка без сортировки)
    Для GET:  paramString = sorted query string key=val&key=val
    """
    target = api_key + timestamp + param_str
    return hmac_lib.new(secret.encode("utf-8"), target.encode("utf-8"), hashlib.sha256).hexdigest()

def _get_keys() -> tuple[str, str]:
    return os.environ.get("MEXC_API_KEY", ""), os.environ.get("MEXC_SECRET_KEY", "")

def mexc_get(path: str, params: dict | None = None) -> dict:
    api_key, secret = _get_keys()
    ts  = str(int(time.time() * 1000))
    prm = params or {}
    # GET: sorted query string
    qs  = "&".join(f"{k}={v}" for k, v in sorted(prm.items()) if v is not None) if prm else ""
    sig = _sign(api_key, secret, ts, qs)
    url = f"{BASE_URL}{path}?{qs}" if qs else f"{BASE_URL}{path}"
    hdrs = {
        "ApiKey":       api_key,
        "Request-Time": ts,
        "Signature":    sig,
        "Content-Type": "application/json",
        "User-Agent":   "MexcBot/2.0",
    }
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"success": False, "error": str(e)}

def mexc_post(path: str, body: dict) -> dict:
    api_key, secret = _get_keys()
    ts       = str(int(time.time() * 1000))
    body_str = json.dumps(body, separators=(",", ":"))   # компактный JSON без пробелов
    sig      = _sign(api_key, secret, ts, body_str)
    url      = f"{BASE_URL}{path}"
    hdrs = {
        "ApiKey":       api_key,
        "Request-Time": ts,
        "Signature":    sig,
        "Content-Type": "application/json",
        "User-Agent":   "MexcBot/2.0",
    }
    try:
        req = urllib.request.Request(url, data=body_str.encode(), headers=hdrs, method="POST")
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"success": False, "error": str(e)}

# ─── MEXC Helpers ─────────────────────────────────────────────────────────────

def get_futures_balance() -> float:
    """Баланс USDT фьючерсного аккаунта."""
    r = mexc_get("/private/account/asset/USDT")
    if r.get("success"):
        data = r.get("data") or {}
        return float(data.get("availableBalance", 0) or 0)
    return 0.0

def get_ticker(symbol: str) -> dict:
    """Тикер по символу (BTC_USDT)."""
    r = mexc_get("/contract/ticker", {"symbol": symbol})
    if r.get("success"):
        data = r.get("data")
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data:
            return data[0]
    return {}

def get_price(symbol: str) -> float | None:
    t = get_ticker(symbol)
    p = t.get("lastPrice") or t.get("last") or t.get("indexPrice")
    return float(p) if p else None

def set_leverage_api(symbol: str, leverage: int) -> dict:
    # При открытии через openType=1 (isolated) плечо задаётся прямо в ордере.
    # Отдельный вызов change_leverage нужен только для существующей позиции.
    # Пробуем — если ошибка, не критично, плечо идёт в ордере.
    r = mexc_post("/private/position/change_leverage", {
        "positionId": 0,      # 0 = применить к символу
        "symbol":     symbol,
        "leverage":   leverage,
        "openType":   1,
    })
    return r

def place_order(symbol: str, side: int, vol: float, leverage: int) -> dict:
    """
    side:
      1 = open long
      2 = close long
      3 = open short
      4 = close short
    type: 6 = market (MEXC Futures market order code)
    openType: 1 = isolated, 2 = cross
    vol: количество контрактов (= notional / price)
    """
    return mexc_post("/private/order/submit", {
        "symbol":   symbol,
        "side":     side,
        "openType": 1,
        "type":     6,         # market order
        "vol":      vol,
        "leverage": leverage,
    })

def transfer_to_futures(amount: float) -> dict:
    """Перевод USDT со спотового на фьючерсный счёт MEXC."""
    return mexc_post("/private/account/transfer", {
        "currency":    "USDT",
        "amount":      str(amount),
        "transferType": 1,   # 1 = spot → futures
    })

def get_open_positions_api(symbol: str | None = None) -> list:
    """Реальные открытые позиции на MEXC (опционально по символу)."""
    params = {"symbol": symbol} if symbol else {}
    r = mexc_get("/private/position/open_positions", params)
    if r.get("success"):
        return r.get("data") or []
    return []

def close_position_api(symbol: str, direction: str, vol: float) -> dict:
    """Закрыть позицию — сначала смотрим реальный объём из API."""
    # Получаем реальные позиции по этому символу
    positions = get_open_positions_api(symbol)
    real_vol = 0.0
    for p in positions:
        if p.get("symbol") == symbol:
            hold_vol = float(p.get("holdVol", 0) or 0)
            if hold_vol > 0:
                real_vol = hold_vol
                break
    # Если позиции нет на бирже — ничего не делаем
    if real_vol <= 0:
        return {"success": True, "skipped": True, "reason": "no open position on exchange"}
    # Закрываем реальный объём
    side = 2 if direction == "LONG" else 4  # 2=close_long, 4=close_short
    return mexc_post("/private/order/submit", {
        "symbol":   symbol,
        "side":     side,
        "openType": 1,
        "type":     6,
        "vol":      real_vol,
        "leverage": LEVERAGE,
    })

def to_mexc_symbol(pair: str) -> str:
    """SOL/USDT → SOL_USDT."""
    return pair.replace("/", "_")

def calc_qty(balance: float, price: float) -> float:
    """Кол-во контрактов = (balance * POS_PCT * leverage) / price."""
    if price <= 0: return 0.0
    notional = balance * POS_PCT * LEVERAGE
    qty      = notional / price
    if qty >= 1000: return round(qty, 0)
    if qty >= 100:  return round(qty, 1)
    if qty >= 10:   return round(qty, 2)
    if qty >= 1:    return round(qty, 3)
    return round(qty, 4)

# ─── БД ───────────────────────────────────────────────────────────────────────

def db_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def get_bot_state() -> dict:
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(f"SELECT is_running, leverage, position_pct, balance_usdt FROM {SCHEMA}.mexc_bot_state LIMIT 1")
        r = cur.fetchone()
        cur.close(); conn.close()
        if r:
            return {
                "running":   bool(r[0]),
                "leverage":  int(r[1] or LEVERAGE),
                "pos_pct":   float(r[2] or POS_PCT),
                "balance":   float(r[3] or 0),
                "max_open":  MAX_OPEN,
                "min_score": MIN_SCORE,
                "timeout_h": TIMEOUT_H,
            }
        return {"running": False}
    except Exception:
        return {"running": False}

def save_settings(leverage: int, pos_pct: float, max_open: int, min_score: int) -> bool:
    """Сохранить настройки бота в БД."""
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(
            f"UPDATE {SCHEMA}.mexc_bot_state SET leverage=%s, position_pct=%s, updated_at=NOW()",
            (leverage, pos_pct)
        )
        conn.commit(); cur.close(); conn.close()
        return True
    except Exception:
        return False

def set_running(val: bool):
    try:
        conn = db_conn(); cur = conn.cursor()
        if val:
            cur.execute(f"UPDATE {SCHEMA}.mexc_bot_state SET is_running=true, started_at=NOW(), updated_at=NOW()")
        else:
            cur.execute(f"UPDATE {SCHEMA}.mexc_bot_state SET is_running=false, stopped_at=NOW(), updated_at=NOW()")
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def update_balance(bal: float):
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(f"UPDATE {SCHEMA}.mexc_bot_state SET balance_usdt=%s, updated_at=NOW()", (bal,))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def count_open() -> int:
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.mexc_bot_trades WHERE status='open'")
        n = cur.fetchone()[0]; cur.close(); conn.close()
        return n
    except Exception:
        return 0

def already_trading(symbol: str) -> bool:
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.mexc_bot_trades WHERE symbol=%s AND status='open'", (symbol,))
        n = cur.fetchone()[0]; cur.close(); conn.close()
        return n > 0
    except Exception:
        return True

def db_open_trade(pair, symbol, direction, entry, qty, pos_usdt,
                  tp1, tp2, sl, tp1_pct, tp2_pct, sl_pct,
                  score, factors, order_id, signal_id) -> int | None:
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(
            f"""INSERT INTO {SCHEMA}.mexc_bot_trades
            (signal_id,pair,symbol,direction,entry_price,qty,position_usdt,leverage,
             tp1_price,tp2_price,sl_price,tp1_pct,tp2_pct,sl_pct,
             score,factors_json,mexc_order_id,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'open')
            RETURNING id""",
            (signal_id,pair,symbol,direction,entry,qty,pos_usdt,LEVERAGE,
             tp1,tp2,sl,tp1_pct,tp2_pct,sl_pct,
             score,json.dumps(factors,ensure_ascii=False),order_id))
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()
        return row[0] if row else None
    except Exception:
        return None

def db_close_trade(trade_id, exit_price, pnl_usdt, pnl_pct, reason):
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(
            f"""UPDATE {SCHEMA}.mexc_bot_trades
            SET exit_price=%s,pnl_usdt=%s,pnl_pct=%s,close_reason=%s,
                status=%s,closed_at=NOW()
            WHERE id=%s""",
            (exit_price,round(pnl_usdt,2),round(pnl_pct,4),reason,
             "profit" if pnl_usdt >= 0 else "loss",trade_id))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def db_get_open_trades() -> list:
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(
            f"""SELECT id,pair,symbol,direction,entry_price,qty,position_usdt,
                tp1_price,tp2_price,sl_price,opened_at,mexc_order_id
            FROM {SCHEMA}.mexc_bot_trades WHERE status='open' ORDER BY opened_at""")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [{"id":r[0],"pair":r[1],"symbol":r[2],"direction":r[3],
                 "entry":float(r[4]),"qty":float(r[5]),"pos_usdt":float(r[6]),
                 "tp1":float(r[7]) if r[7] else 0,
                 "tp2":float(r[8]) if r[8] else 0,
                 "sl": float(r[9]) if r[9] else 0,
                 "opened_at":r[10], "order_id":r[11] or ""} for r in rows]
    except Exception:
        return []

def db_get_new_signals() -> list:
    """Свежие сигналы за последние 10 минут, score ≥ MIN_SCORE."""
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(
            f"""SELECT id,pair,signal_type,entry_price,
                tp1_price,tp2_price,stop_price,
                tp1_pct,tp2_pct,sl_pct,
                confidence,factors_json
            FROM {SCHEMA}.signals
            WHERE signal_type IN ('LONG','SHORT')
              AND status='active'
              AND confidence >= %s
              AND created_at > NOW() - INTERVAL '10 minutes'
              AND (id NOT IN (
                SELECT signal_id FROM {SCHEMA}.mexc_bot_trades
                WHERE signal_id IS NOT NULL
              ))
            ORDER BY confidence DESC LIMIT 5""",
            (MIN_SCORE,))
        rows = cur.fetchall(); cur.close(); conn.close()
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
                "entry":   float(r[3]),
                "tp1":     float(r[4]) if r[4] else 0,
                "tp2":     float(r[5]) if r[5] else 0,
                "sl":      float(r[6]) if r[6] else 0,
                "tp1_pct": float(r[7] or 0),
                "tp2_pct": float(r[8] or 0),
                "sl_pct":  float(r[9] or 0),
                "score":   r[10] or 70,
                "factors": factors,
            })
        return out
    except Exception:
        return []

def db_get_stats() -> dict:
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*) total,
                COUNT(*) FILTER(WHERE status='profit') wins,
                COUNT(*) FILTER(WHERE status='loss')   losses,
                COUNT(*) FILTER(WHERE status='open')   open_cnt,
                COALESCE(SUM(pnl_usdt) FILTER(WHERE status IN('profit','loss')),0) pnl,
                COALESCE(AVG(pnl_pct)  FILTER(WHERE status='profit'),0) avg_win,
                COALESCE(AVG(pnl_pct)  FILTER(WHERE status='loss'),0)  avg_loss
            FROM {SCHEMA}.mexc_bot_trades""")
        r = cur.fetchone()
        wins = r[1] or 0; losses = r[2] or 0; closed = wins + losses

        cur.execute(f"""
            SELECT id,pair,direction,entry_price,tp2_price,sl_price,
                position_usdt,opened_at,score
            FROM {SCHEMA}.mexc_bot_trades WHERE status='open'
            ORDER BY opened_at DESC""")
        open_trades = [{"id":x[0],"pair":x[1],"direction":x[2],
            "entry":float(x[3]),"tp2":float(x[4]) if x[4] else 0,
            "sl":  float(x[5]) if x[5] else 0,
            "pos": float(x[6]),"score":x[8] or 0,
            "opened":x[7].strftime("%d.%m %H:%M") if x[7] else "—"} for x in cur.fetchall()]

        cur.execute(f"""
            SELECT id,pair,direction,pnl_usdt,pnl_pct,close_reason,closed_at,score
            FROM {SCHEMA}.mexc_bot_trades
            WHERE status IN('profit','loss')
            ORDER BY closed_at DESC LIMIT 20""")
        history = [{"id":x[0],"pair":x[1],"direction":x[2],
            "pnl":float(x[3] or 0),"pnl_pct":float(x[4] or 0),
            "reason":x[5] or "","score":x[7] or 0,
            "closed":x[6].strftime("%d.%m %H:%M") if x[6] else "—"} for x in cur.fetchall()]

        state = get_bot_state()
        cur.close(); conn.close()
        return {
            "running":   state["running"],
            "balance":   state["balance"],
            # Настройки — из DB
            "leverage":  state.get("leverage",  LEVERAGE),
            "pos_pct":   state.get("pos_pct",   POS_PCT),
            "max_open":  state.get("max_open",  MAX_OPEN),
            "min_score": state.get("min_score", MIN_SCORE),
            "timeout_h": state.get("timeout_h", TIMEOUT_H),
            # Статистика
            "total":     r[0] or 0,
            "wins":      wins, "losses": losses,
            "open":      r[3] or 0, "closed": closed,
            "win_rate":  round(wins/closed*100,1) if closed > 0 else 0,
            "total_pnl": round(float(r[4]),2),
            "avg_win":   round(float(r[5]),2),
            "avg_loss":  round(float(r[6]),2),
            "open_trades": open_trades,
            "history":   history,
        }
    except Exception as e:
        return {"running":False,"balance":0,"total":0,"wins":0,"losses":0,
                "leverage":LEVERAGE,"pos_pct":POS_PCT,"max_open":MAX_OPEN,"min_score":MIN_SCORE,
                "open":0,"closed":0,"win_rate":0,"total_pnl":0,
                "avg_win":0,"avg_loss":0,"open_trades":[],"history":[],"error":str(e)}

# ─── Telegram ─────────────────────────────────────────────────────────────────

def tg(text: str):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id: return
    try:
        body = json.dumps({"chat_id":chat_id,"text":text,"parse_mode":"HTML"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type":"application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=6)
    except Exception:
        pass

def fp(p) -> str:
    if not p: return "—"
    p = float(p)
    if p >= 10000: return f"{p:,.0f}"
    if p >= 100:   return f"{p:.2f}"
    if p >= 1:     return f"{p:.4f}"
    if p >= 0.001: return f"{p:.6f}"
    return f"{p:.8f}"

# ─── Тик: проверка открытых позиций ──────────────────────────────────────────

def check_open_positions(balance: float) -> int:
    trades    = db_get_open_trades()
    now_utc   = datetime.now(timezone.utc)
    closed_n  = 0

    for t in trades:
        price = get_price(t["symbol"])
        if not price:
            continue

        age_h    = (now_utc.timestamp() - t["opened_at"].timestamp()) / 3600 if t["opened_at"] else 99
        entry    = t["entry"]
        is_long  = t["direction"] == "LONG"
        reason   = None
        exit_p   = price

        if is_long:
            if t["tp2"] > 0 and price >= t["tp2"]:
                reason = f"✅ TP2 достигнут"; exit_p = t["tp2"]
            elif t["tp1"] > 0 and price >= t["tp1"] and age_h >= 0.5:
                reason = f"✅ TP1 достигнут"; exit_p = t["tp1"]
            elif t["sl"]  > 0 and price <= t["sl"]:
                reason = "🛑 Стоп-лосс"; exit_p = t["sl"]
            elif age_h >= TIMEOUT_H:
                reason = f"⏱ Таймаут {TIMEOUT_H}ч"
        else:
            if t["tp2"] > 0 and price <= t["tp2"]:
                reason = f"✅ TP2 достигнут"; exit_p = t["tp2"]
            elif t["tp1"] > 0 and price <= t["tp1"] and age_h >= 0.5:
                reason = f"✅ TP1 достигнут"; exit_p = t["tp1"]
            elif t["sl"]  > 0 and price >= t["sl"]:
                reason = "🛑 Стоп-лосс"; exit_p = t["sl"]
            elif age_h >= TIMEOUT_H:
                reason = f"⏱ Таймаут {TIMEOUT_H}ч"

        if reason is None:
            continue

        # Закрываем на бирже
        close_position_api(t["symbol"], t["direction"], t["qty"])

        # P&L с учётом плеча
        raw_pct = ((exit_p - entry) / entry * 100) if is_long else ((entry - exit_p) / entry * 100)
        lev_pct = round(raw_pct * LEVERAGE, 4)
        pnl_u   = round(t["pos_usdt"] * lev_pct / 100, 2)

        db_close_trade(t["id"], exit_p, pnl_u, lev_pct, reason)

        sign = "+" if pnl_u >= 0 else ""
        tg(
            f"{'🟢' if pnl_u>=0 else '🔴'} <b>MEXC Бот · {t['pair']}</b> [{t['direction']}]\n"
            f"Закрыт: {reason}\n"
            f"Вход ${fp(entry)} → Выход ${fp(exit_p)}\n"
            f"P&L: <b>{sign}{lev_pct:.2f}%</b>  →  <b>{sign}${pnl_u:.2f}</b>\n"
            f"Позиция: ${t['pos_usdt']:.0f} × {LEVERAGE}x = ${t['pos_usdt']*LEVERAGE:.0f}"
        )
        closed_n += 1

    return closed_n

# ─── Тик: открытие новых позиций ─────────────────────────────────────────────

def open_new_positions(balance: float) -> int:
    if count_open() >= MAX_OPEN:
        return 0

    signals = db_get_new_signals()
    opened  = 0

    for sig in signals:
        if count_open() >= MAX_OPEN:
            break

        symbol = to_mexc_symbol(sig["pair"])

        if already_trading(symbol):
            continue

        price = get_price(symbol)
        if not price:
            continue

        qty      = calc_qty(balance, price)
        pos_usdt = round(balance * POS_PCT, 2)

        if qty <= 0 or pos_usdt <= 0:
            continue

        # Устанавливаем плечо
        set_leverage_api(symbol, LEVERAGE)
        time.sleep(0.3)

        # Направление: LONG=1, SHORT=3
        side = 1 if sig["direction"] == "LONG" else 3

        result   = place_order(symbol, side, qty, LEVERAGE)
        order_id = ""
        success  = result.get("success", False)

        if success:
            order_id = str(result.get("data", "") or "")
        else:
            err_msg = result.get("message") or result.get("error") or str(result)
            tg(f"⚠️ <b>MEXC Бот: ошибка открытия {sig['pair']}</b>\n{err_msg[:300]}")
            continue

        # Сохраняем в БД
        db_open_trade(
            pair=sig["pair"], symbol=symbol, direction=sig["direction"],
            entry=price, qty=qty, pos_usdt=pos_usdt,
            tp1=sig["tp1"], tp2=sig["tp2"], sl=sig["sl"],
            tp1_pct=sig["tp1_pct"], tp2_pct=sig["tp2_pct"], sl_pct=sig["sl_pct"],
            score=sig["score"], factors=sig["factors"], order_id=order_id,
            signal_id=sig["id"],
        )

        exp = round(pos_usdt * LEVERAGE, 0)
        tg(
            f"🚀 <b>MEXC Бот · Открыта позиция!</b>\n\n"
            f"{'📈 LONG' if sig['direction']=='LONG' else '📉 SHORT'}  <b>{sig['pair']}</b>\n"
            f"Score: {sig['score']}/100  ·  MEXC Futures\n\n"
            f"📌 Вход:  <b>${fp(price)}</b>\n"
            f"🔥 Плечо: <b>{LEVERAGE}x</b>  (${pos_usdt:.0f} → <b>${exp:.0f}</b>)\n"
            f"📦 Объём: {qty}\n\n"
            f"✅ TP1: ${fp(sig['tp1'])}  (+{sig['tp1_pct']:.1f}%)\n"
            f"✅ TP2: ${fp(sig['tp2'])}  (+{sig['tp2_pct']:.1f}%)\n"
            f"🛑 SL:  ${fp(sig['sl'])}  (-{sig['sl_pct']:.1f}%)"
        )
        opened += 1

    return opened

# ─── Тест-сделка ──────────────────────────────────────────────────────────────

def run_test_trade() -> dict:
    """
    Тест: открываем LONG DOGE_USDT (1 контракт), ВСЕГДА закрываем через finally.
    Цель: убедиться что auth + ордера работают корректно.
    """
    log    = []
    symbol = "DOGE_USDT"
    vol    = 1
    opened = False

    # 1. Баланс
    bal = get_futures_balance()
    log.append(f"{'✅' if bal > 0.01 else '⚠️'} Баланс фьючерсов: ${bal:.4f} USDT")

    if bal < 0.01:
        log.append("❌ Фьючерсный счёт пуст")
        log.append("👉 MEXC → Активы → Перевод → Фьючерсы → минимум $10 USDT")
        return {"ok": False, "log": log, "balance": bal}

    # 2. Цена DOGE
    price = get_price(symbol)
    if not price:
        log.append("❌ Не удалось получить цену DOGE_USDT")
        return {"ok": False, "log": log}
    log.append(f"✅ Цена DOGE: ${price:.5f}")

    needed = round(vol * price / LEVERAGE, 6)
    log.append(f"📊 Нужна маржа: ${needed:.4f} USDT (1 конт. × {LEVERAGE}x)")

    if bal < needed:
        log.append(f"❌ Мало маржи: нужно ${needed:.4f}, есть ${bal:.4f}")
        return {"ok": False, "log": log, "balance": bal}

    order_ok = False
    try:
        # 3. Открываем LONG
        log.append(f"→ Открываю LONG {symbol} × {vol} конт. × {LEVERAGE}x...")
        order_r   = place_order(symbol, 1, vol, LEVERAGE)
        order_ok  = order_r.get("success", False)
        order_msg = order_r.get("message") or str(order_r.get("data", ""))[:120] or str(order_r)[:120]
        log.append(f"{'✅' if order_ok else '❌'} Открытие: {order_msg}")
        if order_ok:
            opened = True
        else:
            log.append(f"Raw: {json.dumps(order_r)[:250]}")
    finally:
        # 4. Закрываем через реальные позиции API — надёжно
        if opened:
            time.sleep(2)  # ждём пока ордер исполнится
            log.append("→ Проверяю реальную позицию на MEXC...")
            positions = get_open_positions_api(symbol)
            real_vol  = 0.0
            for p in positions:
                if p.get("symbol") == symbol:
                    real_vol = float(p.get("holdVol", 0) or 0)
                    break
            if real_vol > 0:
                log.append(f"→ Закрываю позицию {real_vol} конт...")
                close_r  = place_order(symbol, 2, real_vol, LEVERAGE)
                close_ok = close_r.get("success", False)
                close_msg = close_r.get("message") or str(close_r.get("data", ""))[:100] or str(close_r)[:100]
                log.append(f"{'✅' if close_ok else '⚠️'} Закрытие: {close_msg}")
            else:
                log.append("✅ Позиция уже закрыта биржей (исполнилась)")

    # Итог
    ok = order_ok
    log.append(f"\n{'✅ ВСЁ РАБОТАЕТ!' if ok else '❌ Есть проблемы'}")
    if ok:
        log.append(f"🤖 Бот готов торговать. Нажми 'Запустить бот'!")

    tg(
        f"🧪 <b>MEXC Бот — Тестовая сделка</b>\n\n"
        + "\n".join(l for l in log if l.strip()) +
        f"\n\nРезультат: {'✅ OK' if ok else '❌ ОШИБКА'}"
    )
    return {"ok": ok, "log": log, "balance": bal, "price": price}

# ─── Основной тик ─────────────────────────────────────────────────────────────

def run_tick() -> dict:
    global LEVERAGE, POS_PCT, MAX_OPEN, MIN_SCORE
    state = get_bot_state()
    if not state["running"]:
        return {"skipped": True, "reason": "bot is stopped"}

    # Применяем настройки из БД
    LEVERAGE  = state.get("leverage",  LEVERAGE)
    POS_PCT   = state.get("pos_pct",   POS_PCT)
    MAX_OPEN  = state.get("max_open",  MAX_OPEN)
    MIN_SCORE = state.get("min_score", MIN_SCORE)

    bal = get_futures_balance()
    if bal > 0:
        update_balance(bal)
    else:
        bal = state["balance"] or 100.0

    closed = check_open_positions(bal)
    opened = open_new_positions(bal)

    return {
        "balance":       round(bal, 2),
        "closed_trades": closed,
        "opened_trades": opened,
        "open_count":    count_open(),
    }

# ─── Handler ─────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """MEXC Auto-Bot v2: start/stop/tick/stats/test."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS_RESP, "body": ""}

    params = event.get("queryStringParameters") or {}
    action = params.get("action", "stats")

    if action == "start":
        bal = get_futures_balance()
        if bal > 0: update_balance(bal)
        set_running(True)
        tg(
            "🟢 <b>MEXC Бот запущен!</b>\n\n"
            f"💼 Баланс: <b>${bal:.2f} USDT</b>\n"
            f"🔥 Плечо: <b>{LEVERAGE}x</b>\n"
            f"📊 На сделку: <b>{int(POS_PCT*100)}%</b> → ${bal*POS_PCT:.0f}\n"
            f"🔁 Макс позиций: <b>{MAX_OPEN}</b>\n"
            f"⏱ Таймаут: {TIMEOUT_H}ч\n"
            f"🎯 Мин. score: {MIN_SCORE}/100\n\n"
            "Слежу за сигналами PumpBot 24/7..."
        )
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps({"ok": True, "running": True, "balance": bal})}

    if action == "stop":
        bal = get_futures_balance()
        open_trades = db_get_open_trades()
        closed_n = 0
        for t in open_trades:
            close_position_api(t["symbol"], t["direction"], t["qty"])
            db_close_trade(t["id"], t["entry"], 0, 0, "Бот остановлен вручную")
            closed_n += 1
        set_running(False)
        tg(f"🔴 <b>MEXC Бот остановлен.</b>\nЗакрыто позиций: {closed_n}\nБаланс: ${bal:.2f}")
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps({"ok": True, "running": False, "closed": closed_n})}

    if action == "tick":
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps(run_tick())}

    if action == "test":
        result = run_test_trade()
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps(result)}

    if action == "balance":
        bal = get_futures_balance()
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps({"balance": bal})}

    if action == "ping":
        bal   = get_futures_balance()
        price = get_price("BTC_USDT")
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps({"ok": True, "balance": bal, "btc_price": price})}

    if action == "settings":
        # GET — вернуть текущие настройки
        if event.get("httpMethod") == "GET":
            state = get_bot_state()
            return {"statusCode": 200, "headers": HEADERS_RESP,
                    "body": json.dumps(state)}
        # POST — сохранить настройки
        try:
            body = json.loads(event.get("body") or "{}")
        except Exception:
            body = params  # fallback: из query params

        lev       = int(body.get("leverage",  params.get("leverage",  LEVERAGE)))
        pos_pct   = float(body.get("pos_pct", params.get("pos_pct",  POS_PCT)))
        max_open  = int(body.get("max_open",  params.get("max_open",  MAX_OPEN)))
        min_score = int(body.get("min_score", params.get("min_score", MIN_SCORE)))

        # Валидация
        lev       = max(1, min(125, lev))
        pos_pct   = max(0.01, min(0.99, pos_pct))
        max_open  = max(1, min(10, max_open))
        min_score = max(50, min(100, min_score))

        ok = save_settings(lev, pos_pct, max_open, min_score)
        if ok:
            tg(
                f"⚙️ <b>MEXC Бот — настройки обновлены</b>\n"
                f"🔥 Плечо: <b>{lev}x</b>\n"
                f"📊 На сделку: <b>{round(pos_pct*100)}%</b>\n"
                f"🔁 Макс позиций: <b>{max_open}</b>\n"
                f"🎯 Мин. score: <b>{min_score}/100</b>"
            )
        return {"statusCode": 200, "headers": HEADERS_RESP,
                "body": json.dumps({
                    "ok": ok,
                    "leverage": lev, "pos_pct": pos_pct,
                    "max_open": max_open, "min_score": min_score,
                })}

    # stats (default)
    return {"statusCode": 200, "headers": HEADERS_RESP,
            "body": json.dumps(db_get_stats())}