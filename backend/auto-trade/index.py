"""Auto-trading bot: Binance/Bybit/OKX. Modes: MEDIUM (safe) and HARD (aggressive)."""
import json, os, psycopg2
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
    "hard":   {"position_pct":0.15,"leverage":5,"max_sim":5,"min_conf":92,
               "daily_target":0.15,"max_daily_loss":0.05,
               "desc":"Агрессивный: 15% депозита, 5x плечо, макс 5 сделок, цель +15%/день"}
}

def db():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def get_bot_stats():
    try:
        conn = db(); cur = conn.cursor()
        cur.execute(f"""SELECT COUNT(*),
            COUNT(*) FILTER(WHERE status='profit'), COUNT(*) FILTER(WHERE status='loss'),
            COUNT(*) FILTER(WHERE status='open'),
            COALESCE(SUM(pnl_usdt) FILTER(WHERE status IN('profit','loss')),0),
            COALESCE(AVG(pnl_pct) FILTER(WHERE status='profit'),0),
            COALESCE(AVG(pnl_pct) FILTER(WHERE status='loss'),0)
            FROM {SCHEMA}.bot_trades""")
        r = cur.fetchone()
        cur.execute(f"""SELECT id,exchange_name,trade_mode,pair,direction,entry_price,
            position_usdt,leverage,target_price,stop_price,opened_at
            FROM {SCHEMA}.bot_trades WHERE status='open' ORDER BY opened_at DESC""")
        open_trades = [{"id":x[0],"exchange":x[1],"mode":x[2],"pair":x[3],"direction":x[4],
            "entry":float(x[5]),"position_usdt":float(x[6]),"leverage":x[7],
            "target":float(x[8]),"stop":float(x[9]),
            "opened_at":x[10].strftime("%d.%m %H:%M") if x[10] else "—"} for x in cur.fetchall()]
        cur.close(); conn.close()
        total=r[0] or 0; wins=r[1] or 0; losses=r[2] or 0; closed=wins+losses
        return {"total":total,"wins":wins,"losses":losses,"open":r[3] or 0,"closed":closed,
            "win_rate":round(wins/closed*100,1) if closed>0 else 0,
            "total_pnl":round(float(r[4]),2),"avg_win":round(float(r[5]),2),
            "avg_loss":round(float(r[6]),2),"open_trades":open_trades}
    except Exception: return {"total":0,"wins":0,"losses":0,"open":0,"closed":0,"win_rate":0,"total_pnl":0,"avg_win":0,"avg_loss":0,"open_trades":[]}

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
            VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING""",(exchange,mode,max_pos,active))
        conn.commit(); cur.close(); conn.close()
    except Exception: pass

def check_balance(exchange):
    if exchange == "Binance":
        k,s = os.environ.get("BINANCE_API_KEY",""), os.environ.get("BINANCE_SECRET_KEY","")
        if not k: return {"ok":False,"error":"Binance API ключи не заданы — добавьте в Секреты"}
        return binance_balance(k,s)
    if exchange == "Bybit":
        k,s = os.environ.get("BYBIT_API_KEY",""), os.environ.get("BYBIT_SECRET_KEY","")
        if not k: return {"ok":False,"error":"Bybit API ключи не заданы — добавьте в Секреты"}
        return bybit_balance(k,s)
    if exchange == "OKX":
        k,s,p = os.environ.get("OKX_API_KEY",""),os.environ.get("OKX_SECRET_KEY",""),os.environ.get("OKX_PASSPHRASE","")
        if not k: return {"ok":False,"error":"OKX API ключи не заданы — добавьте в Секреты"}
        return okx_balance(k,s,p)
    if exchange == "MEXC":
        k,s = os.environ.get("MEXC_API_KEY",""), os.environ.get("MEXC_SECRET_KEY","")
        if not k: return {"ok":False,"error":"MEXC API ключи не заданы — добавьте в Секреты"}
        return mexc_balance(k,s)
    return {"ok":False,"error":f"Неизвестная биржа: {exchange}"}

def execute_trade(exchange, mode, signal):
    cfg = TRADE_MODES.get(mode, TRADE_MODES["medium"])
    conf = signal.get("confidence",0)
    if conf < cfg["min_conf"]:
        return {"ok":False,"error":f"Уверенность {conf}% ниже порога {cfg['min_conf']}% для режима {mode}"}
    open_cnt = get_open_count(exchange)
    if open_cnt >= cfg["max_sim"]:
        return {"ok":False,"error":f"Достигнут лимит открытых сделок ({cfg['max_sim']}) для {mode} режима"}

    sym = signal["pair"].replace("/","")
    direction = signal["type"]
    side = "BUY" if direction=="LONG" else "SELL"
    entry = float(signal["entry"]); target = float(signal["target"]); stop = float(signal["stop"])

    bal = check_balance(exchange)
    if not bal.get("ok"): return bal
    usdt = bal["usdt"]
    pos_usdt = min(usdt * cfg["position_pct"], 500.0)
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

    trade_id = save_trade({"signal_id":signal.get("db_id"),"exchange":exchange,"mode":mode,
        "pair":signal["pair"],"direction":direction,"entry":entry,
        "position_usdt":round(pos_usdt,2),"leverage":cfg["leverage"],"target":target,"stop":stop})
    return {"ok":True,"trade_id":trade_id,"exchange":exchange,"mode":mode,
            "position_usdt":round(pos_usdt,2),"qty":qty,"entry":entry}

def handler(event: dict, context) -> dict:
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
        sig = body.get("signal",{})
        if not sig: return {"statusCode":400,"headers":HEADERS,"body":json.dumps({"error":"signal required"})}
        result = execute_trade(body.get("exchange","Binance"),body.get("mode","medium"),sig)
        return {"statusCode":200 if result["ok"] else 400,"headers":HEADERS,"body":json.dumps(result)}
    if action == "close_trade":
        close_trade_db(int(body.get("trade_id",0)),float(body.get("exit_price",0)),float(body.get("pnl_usdt",0)),float(body.get("pnl_pct",0)))
        return {"statusCode":200,"headers":HEADERS,"body":json.dumps({"ok":True})}
    return {"statusCode":400,"headers":HEADERS,"body":json.dumps({"error":"unknown action"})}