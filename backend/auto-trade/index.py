"""Автономный торговый бот мирового уровня. Торгует сам по AI-сигналам, отчитывается в Telegram."""
import json, os, psycopg2, urllib.request
from datetime import datetime
from exchange_clients import (binance_balance, binance_order, binance_oco,
                               bybit_balance, bybit_order,
                               okx_balance, okx_order,
                               mexc_balance, mexc_order)

HEADERS = {"Access-Control-Allow-Origin":"*","Access-Control-Allow-Methods":"GET,POST,OPTIONS","Access-Control-Allow-Headers":"Content-Type","Content-Type":"application/json"}
SCHEMA = "t_p73206386_global_trading_signa"

TRADE_MODES = {
    "medium": {"position_pct":0.05,"leverage":2,"max_sim":3,"min_conf":90,
               "daily_target":0.05,"max_daily_loss":0.03,
               "desc":"Безопасный: 5% депозита, 2x плечо, макс 3 сделки, цель +5%/день"},
    "hard":   {"position_pct":0.20,"leverage":5,"max_sim":5,"min_conf":85,
               "daily_target":0.15,"max_daily_loss":0.05,
               "desc":"Агрессивный: 20% депозита, 5x плечо, макс 5 сделок, порог 85%, цель +15%/день"}
}

API_SIGNALS_URL = os.environ.get("AI_SIGNALS_URL", "")

def db():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def send_telegram(text):
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

def get_bot_stats():
    try:
        conn = db(); cur = conn.cursor()
        cur.execute(f"""SELECT COUNT(*),
            COUNT(*) FILTER(WHERE status='profit'), COUNT(*) FILTER(WHERE status='loss'),
            COUNT(*) FILTER(WHERE status='open'),
            COALESCE(SUM(pnl_usdt) FILTER(WHERE status IN('profit','loss')),0),
            COALESCE(AVG(pnl_pct) FILTER(WHERE status='profit'),0),
            COALESCE(AVG(pnl_pct) FILTER(WHERE status='loss'),0)
            FROM {SCHEMA}.bot_trades WHERE status != 'archived'""")
        r = cur.fetchone()
        cur.execute(f"""SELECT id,exchange_name,trade_mode,pair,direction,entry_price,
            position_usdt,leverage,target_price,stop_price,opened_at
            FROM {SCHEMA}.bot_trades WHERE status='open' ORDER BY opened_at DESC""")
        open_trades = [{"id":x[0],"exchange":x[1],"mode":x[2],"pair":x[3],"direction":x[4],
            "entry":float(x[5]),"position_usdt":float(x[6]),"leverage":x[7],
            "target":float(x[8]),"stop":float(x[9]),
            "opened_at":x[10].strftime("%d.%m %H:%M") if x[10] else "—"} for x in cur.fetchall()]
        cur.execute(f"""SELECT COALESCE(SUM(pnl_usdt),0) FROM {SCHEMA}.bot_trades
            WHERE DATE(closed_at) = CURRENT_DATE AND status IN ('profit','loss')""")
        today_pnl = float(cur.fetchone()[0])
        cur.close(); conn.close()
        total=r[0] or 0; wins=r[1] or 0; losses=r[2] or 0; closed=wins+losses
        return {"total":total,"wins":wins,"losses":losses,"open":r[3] or 0,"closed":closed,
            "win_rate":round(wins/closed*100,1) if closed>0 else 0,
            "total_pnl":round(float(r[4]),2),"avg_win":round(float(r[5]),2),
            "avg_loss":round(float(r[6]),2),"open_trades":open_trades,
            "today_pnl":round(today_pnl,2)}
    except Exception:
        return {"total":0,"wins":0,"losses":0,"open":0,"closed":0,"win_rate":0,"total_pnl":0,"avg_win":0,"avg_loss":0,"open_trades":[],"today_pnl":0}

def save_trade(t):
    try:
        conn = db(); cur = conn.cursor()
        cur.execute(f"""INSERT INTO {SCHEMA}.bot_trades
            (signal_id,exchange_name,trade_mode,pair,direction,entry_price,position_usdt,leverage,target_price,stop_price,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'open') RETURNING id""",
            (t.get("signal_id"),t["exchange"],t["mode"],t["pair"],t["direction"],
             t["entry"],t["position_usdt"],t["leverage"],t["target"],t["stop"]))
        row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
        return row[0] if row else None
    except Exception: return None

def get_open_count(exchange):
    try:
        conn = db(); cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.bot_trades WHERE status='open' AND exchange_name=%s",(exchange,))
        n = cur.fetchone()[0]; cur.close(); conn.close()
        return n
    except Exception: return 0

def close_trade_db(trade_id, exit_price, pnl_usdt, pnl_pct):
    try:
        conn = db(); cur = conn.cursor()
        cur.execute(f"""UPDATE {SCHEMA}.bot_trades SET exit_price=%s,pnl_usdt=%s,pnl_pct=%s,
            status=%s,closed_at=NOW() WHERE id=%s""",
            (exit_price,pnl_usdt,pnl_pct,"profit" if pnl_usdt>0 else "loss",trade_id))
        conn.commit(); cur.close(); conn.close()
    except Exception: pass

def get_exchange_configs():
    try:
        conn = db(); cur = conn.cursor()
        cur.execute(f"SELECT id,exchange_name,is_active,trade_mode,max_position_usdt FROM {SCHEMA}.exchange_connections")
        rows = [{"id":r[0],"exchange":r[1],"active":r[2],"mode":r[3],"max_position":float(r[4])} for r in cur.fetchall()]
        cur.close(); conn.close(); return rows
    except Exception: return []

def save_exchange_config(exchange, mode, max_pos, active):
    try:
        conn = db(); cur = conn.cursor()
        cur.execute(f"""INSERT INTO {SCHEMA}.exchange_connections(exchange_name,trade_mode,max_position_usdt,is_active)
            VALUES(%s,%s,%s,%s)
            ON CONFLICT(exchange_name) DO UPDATE SET trade_mode=EXCLUDED.trade_mode, max_position_usdt=EXCLUDED.max_position_usdt, is_active=EXCLUDED.is_active""",(exchange,mode,max_pos,active))
        conn.commit(); cur.close(); conn.close()
    except Exception: pass

def check_balance(exchange):
    if exchange == "Binance":
        k,s = os.environ.get("BINANCE_API_KEY",""), os.environ.get("BINANCE_SECRET_KEY","")
        if not k: return {"ok":False,"error":"Binance API ключи не заданы"}
        return binance_balance(k,s)
    if exchange == "Bybit":
        k,s = os.environ.get("BYBIT_API_KEY",""), os.environ.get("BYBIT_SECRET_KEY","")
        if not k: return {"ok":False,"error":"Bybit API ключи не заданы"}
        return bybit_balance(k,s)
    if exchange == "OKX":
        k,s,p = os.environ.get("OKX_API_KEY",""),os.environ.get("OKX_SECRET_KEY",""),os.environ.get("OKX_PASSPHRASE","")
        if not k: return {"ok":False,"error":"OKX API ключи не заданы"}
        return okx_balance(k,s,p)
    if exchange == "MEXC":
        k,s = os.environ.get("MEXC_API_KEY",""), os.environ.get("MEXC_SECRET_KEY","")
        if not k: return {"ok":False,"error":"MEXC API ключи не заданы"}
        return mexc_balance(k,s)
    return {"ok":False,"error":f"Неизвестная биржа: {exchange}"}

def execute_trade(exchange, mode, signal):
    cfg = TRADE_MODES.get(mode, TRADE_MODES["medium"])
    conf = signal.get("confidence",0)
    if conf < cfg["min_conf"]:
        return {"ok":False,"error":f"Уверенность {conf}% < порога {cfg['min_conf']}%"}
    open_cnt = get_open_count(exchange)
    if open_cnt >= cfg["max_sim"]:
        return {"ok":False,"error":f"Лимит открытых сделок ({cfg['max_sim']})"}

    sym = signal["pair"].replace("/","")
    direction = signal["type"]
    side = "BUY" if direction=="LONG" else "SELL"
    entry = float(signal["entry"]); target = float(signal["target"]); stop = float(signal["stop"])

    bal = check_balance(exchange)
    if not bal.get("ok"): return bal
    usdt = bal["usdt"]
    pos_usdt = min(usdt * cfg["position_pct"], 500.0)
    if pos_usdt < 5:
        return {"ok":False,"error":f"Слишком маленькая позиция: ${pos_usdt:.2f}"}
    qty = round(pos_usdt / entry, 6)

    if exchange == "Binance":
        k,s = os.environ.get("BINANCE_API_KEY",""),os.environ.get("BINANCE_SECRET_KEY","")
        order = binance_order(sym, side, qty, k, s)
        if "error" in order: return {"ok":False,"error":order["error"]}
        if direction=="LONG": binance_oco(sym, qty, stop, target, k, s)
    elif exchange == "Bybit":
        k,s = os.environ.get("BYBIT_API_KEY",""),os.environ.get("BYBIT_SECRET_KEY","")
        order = bybit_order(sym, side, qty, k, s)
        if "error" in order: return {"ok":False,"error":order["error"]}
    elif exchange == "OKX":
        k,s,p = os.environ.get("OKX_API_KEY",""),os.environ.get("OKX_SECRET_KEY",""),os.environ.get("OKX_PASSPHRASE","")
        order = okx_order(sym, side, qty, k, s, p)
        if "error" in order: return {"ok":False,"error":order["error"]}
    elif exchange == "MEXC":
        k,s = os.environ.get("MEXC_API_KEY",""),os.environ.get("MEXC_SECRET_KEY","")
        order = mexc_order(sym, side, qty, k, s)
        if "error" in order: return {"ok":False,"error":order["error"]}
    else:
        return {"ok":False,"error":"Неизвестная биржа"}

    trade_id = save_trade({"signal_id":signal.get("db_id") or signal.get("id"),"exchange":exchange,"mode":mode,
        "pair":signal["pair"],"direction":direction,"entry":entry,
        "position_usdt":round(pos_usdt,2),"leverage":cfg["leverage"],"target":target,"stop":stop})
    return {"ok":True,"trade_id":trade_id,"exchange":exchange,"mode":mode,
            "position_usdt":round(pos_usdt,2),"qty":qty,"entry":entry}

def fetch_url_simple(url, timeout=25):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}

def get_daily_pnl_for_exchange(exchange):
    try:
        conn = db(); cur = conn.cursor()
        cur.execute(f"""SELECT COALESCE(SUM(pnl_usdt),0) FROM {SCHEMA}.bot_trades
            WHERE exchange_name=%s AND DATE(closed_at) = CURRENT_DATE AND status IN ('profit','loss')""",(exchange,))
        pnl = float(cur.fetchone()[0]); cur.close(); conn.close()
        return pnl
    except Exception: return 0

def check_daily_target_reached(exchange, mode, balance):
    cfg = TRADE_MODES.get(mode, TRADE_MODES["medium"])
    target_pnl = balance * cfg["daily_target"]
    daily_pnl = get_daily_pnl_for_exchange(exchange)
    return daily_pnl >= target_pnl, daily_pnl, target_pnl

def check_and_close_open_trades():
    """Проверяем открытые сделки бота — закрываем по TP/SL/времени."""
    closed_trades = []
    try:
        conn = db(); cur = conn.cursor()
        cur.execute(f"""SELECT id, exchange_name, pair, direction, entry_price, target_price, stop_price,
            position_usdt, leverage, opened_at, trade_mode
            FROM {SCHEMA}.bot_trades WHERE status='open'""")
        rows = cur.fetchall(); cur.close(); conn.close()
        for row in rows:
            tid, exchange, pair, direction, entry, target, stop, pos_usdt, lev, opened_at, mode = row
            sym = pair.replace("/","")
            tick = fetch_url_simple(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}")
            if not tick or "price" not in tick:
                continue
            price = float(tick["price"])
            entry_f = float(entry); target_f = float(target); stop_f = float(stop)
            leverage = int(lev) if lev else 1
            position = float(pos_usdt) if pos_usdt else 20

            hit_tp = (direction == "LONG" and price >= target_f) or (direction == "SHORT" and price <= target_f)
            hit_sl = (direction == "LONG" and price <= stop_f) or (direction == "SHORT" and price >= stop_f)
            too_old = opened_at and (datetime.utcnow() - opened_at).total_seconds() > 6 * 3600

            if not hit_tp and not hit_sl and not too_old:
                continue

            if direction == "LONG":
                exit_p = target_f if hit_tp else stop_f if hit_sl else price
                pct = (exit_p - entry_f) / entry_f * 100
            else:
                exit_p = target_f if hit_tp else stop_f if hit_sl else price
                pct = (entry_f - exit_p) / entry_f * 100

            pct_leveraged = pct * leverage
            pnl_usdt = round(position * pct_leveraged / 100, 2)
            close_trade_db(tid, exit_p, pnl_usdt, round(pct_leveraged, 2))

            reason = "🎯 Take Profit" if hit_tp else "🛑 Stop Loss" if hit_sl else "⏰ Таймаут"
            emoji = "✅" if pnl_usdt > 0 else "❌"
            send_telegram(
                f"{emoji} <b>Сделка закрыта: {pair}</b>\n"
                f"Биржа: {exchange} · {direction} · {leverage}x\n"
                f"Причина: {reason}\n"
                f"Вход: {entry_f} → Выход: {exit_p}\n"
                f"P&L: <b>{'+' if pnl_usdt>=0 else ''}${pnl_usdt}</b> ({'+' if pct_leveraged>=0 else ''}{pct_leveraged:.1f}%)"
            )
            closed_trades.append({"pair":pair,"pnl":pnl_usdt,"exchange":exchange,"mode":mode})
    except Exception:
        pass
    return closed_trades

def auto_run():
    """Главный цикл автономной торговли. Вызывается по расписанию."""
    results = {"checked": 0, "opened": 0, "closed": 0, "skipped_target": 0, "errors": []}

    closed = check_and_close_open_trades()
    results["closed"] = len(closed)

    configs = get_exchange_configs()
    active_configs = [c for c in configs if c.get("active")]
    if not active_configs:
        return {**results, "status": "no_active_exchanges"}

    try:
        fetch_url_simple("https://functions.poehali.dev/4b074d99-4dd2-412c-904d-50db2bf5fbed?action=generate")
    except Exception:
        pass

    signals_data = fetch_url_simple("https://functions.poehali.dev/4b074d99-4dd2-412c-904d-50db2bf5fbed?action=saved&limit=15")
    signals = signals_data.get("signals", [])
    active_signals = [s for s in signals if s.get("status") == "active" and s.get("confidence", 0) >= 85]
    results["checked"] = len(active_signals)

    if not active_signals:
        return {**results, "status": "no_signals"}

    for cfg in active_configs:
        exchange = cfg["exchange"]
        mode = cfg["mode"]
        trade_cfg = TRADE_MODES.get(mode, TRADE_MODES["medium"])

        bal = check_balance(exchange)
        if not bal.get("ok"):
            results["errors"].append(f"{exchange}: {bal.get('error','ошибка')}")
            continue
        balance = bal["usdt"]

        reached, daily_pnl, target_pnl = check_daily_target_reached(exchange, mode, balance)
        if reached:
            results["skipped_target"] += 1
            continue

        for sig in active_signals:
            if sig.get("confidence", 0) < trade_cfg["min_conf"]:
                continue

            already_exists = False
            try:
                conn = db(); cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.bot_trades WHERE pair=%s AND exchange_name=%s AND status='open'",(sig["pair"],exchange))
                already_exists = cur.fetchone()[0] > 0
                cur.close(); conn.close()
            except Exception: pass
            if already_exists:
                continue

            result = execute_trade(exchange, mode, sig)
            if result.get("ok"):
                results["opened"] += 1
                lev = trade_cfg["leverage"]
                send_telegram(
                    f"🤖 <b>Бот открыл сделку!</b>\n"
                    f"Биржа: {exchange} · Режим: {mode.upper()}\n"
                    f"{'🟢' if sig['type']=='LONG' else '🔴'} <b>{sig['type']} {sig['pair']}</b>\n"
                    f"Уверенность AI: {sig.get('confidence',0)}%\n"
                    f"Плечо: {lev}x · Позиция: ${result['position_usdt']}\n"
                    f"▫️ Вход: {result['entry']}\n"
                    f"🎯 Цель: {sig['target']}\n"
                    f"🛑 Стоп: {sig['stop']}"
                )
                open_cnt = get_open_count(exchange)
                if open_cnt >= trade_cfg["max_sim"]:
                    break

    for cfg in active_configs:
        exchange = cfg["exchange"]
        mode = cfg["mode"]
        bal = check_balance(exchange)
        if not bal.get("ok"):
            continue
        balance = bal["usdt"]
        reached, daily_pnl, target_pnl = check_daily_target_reached(exchange, mode, balance)
        if reached and daily_pnl > 0:
            pct = round(daily_pnl / (balance - daily_pnl) * 100, 1) if balance > daily_pnl else 0
            send_telegram(
                f"🏆 <b>ДНЕВНОЙ ПЛАН ВЫПОЛНЕН!</b>\n\n"
                f"Биржа: {exchange} · Режим: {mode.upper()}\n"
                f"Прибыль за день: <b>+${daily_pnl:.2f}</b> (+{pct}%)\n"
                f"Цель была: +${target_pnl:.2f}\n"
                f"Баланс: <b>${balance:.2f}</b>\n\n"
                f"🤖 Бот завершил работу на сегодня. Следующая сессия — завтра."
            )

    results["status"] = "ok"
    return results

def handler(event: dict, context) -> dict:
    """Автономный торговый бот с Telegram-уведомлениями."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode":200,"headers":HEADERS,"body":""}
    params = event.get("queryStringParameters") or {}
    body = {}
    if event.get("body"):
        try: body = json.loads(event["body"])
        except Exception: pass
    action = params.get("action") or body.get("action","stats")

    if action == "stats":
        return {"statusCode":200,"headers":HEADERS,"body":json.dumps(get_bot_stats())}
    if action == "balance":
        exch = params.get("exchange") or body.get("exchange","Binance")
        return {"statusCode":200,"headers":HEADERS,"body":json.dumps(check_balance(exch))}
    if action == "config":
        return {"statusCode":200,"headers":HEADERS,"body":json.dumps({"configs":get_exchange_configs(),"modes":TRADE_MODES,"exchanges":["Binance","Bybit","OKX","MEXC"]})}
    if action == "save_config":
        save_exchange_config(body.get("exchange","Binance"),body.get("mode","medium"),float(body.get("max_position",50)),bool(body.get("active",False)))
        return {"statusCode":200,"headers":HEADERS,"body":json.dumps({"ok":True})}
    if action == "trade":
        exch = body.get("exchange","Binance"); mode = body.get("mode","medium"); sig = body.get("signal",{})
        result = execute_trade(exch, mode, sig)
        return {"statusCode":200,"headers":HEADERS,"body":json.dumps(result)}

    if action == "auto_run":
        result = auto_run()
        return {"statusCode":200,"headers":HEADERS,"body":json.dumps(result)}

    return {"statusCode":200,"headers":HEADERS,"body":json.dumps(get_bot_stats())}