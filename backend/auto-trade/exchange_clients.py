"""Exchange API clients: Binance, Bybit, OKX."""
import json, urllib.request, urllib.parse, hashlib, hmac, time, os, base64
from datetime import datetime

def fetch_url(url, method="GET", headers=None, body=None):
    try:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "Bot/1.0"}, method=method)
        if body: req.data = body.encode()
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

# Binance
def binance_sign(params, secret):
    q = urllib.parse.urlencode(params)
    return hmac.new(secret.encode(), q.encode(), hashlib.sha256).hexdigest()

def binance_req(endpoint, params, api_key, secret, method="GET"):
    params["timestamp"] = int(time.time() * 1000)
    params["signature"] = binance_sign(params, secret)
    q = urllib.parse.urlencode(params)
    base = "https://api.binance.com"
    hdrs = {"X-MBX-APIKEY": api_key}
    if method == "GET":
        return fetch_url(f"{base}{endpoint}?{q}", headers=hdrs)
    hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    return fetch_url(f"{base}{endpoint}", "POST", hdrs, q)

def binance_balance(api_key, secret):
    d = binance_req("/api/v3/account", {}, api_key, secret)
    if "error" in d or "balances" not in d: return {"error": d.get("error","err")}
    usdt = next((float(b["free"]) for b in d["balances"] if b["asset"]=="USDT"), 0)
    return {"usdt": round(usdt,2), "exchange": "Binance", "ok": True}

def binance_order(symbol, side, qty, api_key, secret):
    return binance_req("/api/v3/order", {"symbol":symbol,"side":side,"type":"MARKET","quantity":round(qty,6)}, api_key, secret, "POST")

def binance_oco(symbol, qty, stop, limit, api_key, secret):
    return binance_req("/api/v3/orderList/oco", {
        "symbol":symbol,"side":"SELL","quantity":round(qty,6),
        "price":round(limit,8),"stopPrice":round(stop,8),
        "stopLimitPrice":round(stop*0.999,8),"stopLimitTimeInForce":"GTC"
    }, api_key, secret, "POST")

# Bybit
def bybit_sign(params, secret, ts, api_key):
    param_str = "&".join(f"{k}={v}" for k,v in sorted(params.items()))
    payload = f"{ts}{api_key[:8]}5000{param_str}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def bybit_req(endpoint, params, api_key, secret, method="GET"):
    ts = int(time.time() * 1000)
    sign = bybit_sign(params, secret, ts, api_key)
    hdrs = {"X-BAPI-API-KEY":api_key,"X-BAPI-SIGN":sign,"X-BAPI-TIMESTAMP":str(ts),"X-BAPI-RECV-WINDOW":"5000","Content-Type":"application/json"}
    base = "https://api.bybit.com"
    if method == "GET":
        return fetch_url(f"{base}{endpoint}?{urllib.parse.urlencode(params)}", headers=hdrs)
    return fetch_url(f"{base}{endpoint}", "POST", hdrs, json.dumps(params))

def bybit_balance(api_key, secret):
    d = bybit_req("/v5/account/wallet-balance", {"accountType":"UNIFIED"}, api_key, secret)
    if "error" in d: return {"error": d["error"]}
    try:
        coins = d["result"]["list"][0]["coin"]
        usdt = next((float(c["walletBalance"]) for c in coins if c["coin"]=="USDT"), 0)
        return {"usdt": round(usdt,2), "exchange":"Bybit","ok":True}
    except Exception: return {"error": "parse_error"}

def bybit_order(symbol, side, qty, api_key, secret):
    return bybit_req("/v5/order/create", {"category":"spot","symbol":symbol,"side":"Buy" if side=="BUY" else "Sell","orderType":"Market","qty":str(round(qty,6))}, api_key, secret, "POST")

# OKX
def okx_sign(ts, method, path, body, secret):
    msg = f"{ts}{method}{path}{body}"
    return base64.b64encode(hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()

def okx_req(endpoint, method, params, api_key, secret, passphrase):
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = json.dumps(params) if method=="POST" else ""
    path = endpoint + ("?" + urllib.parse.urlencode(params) if method=="GET" and params else "")
    hdrs = {"OK-ACCESS-KEY":api_key,"OK-ACCESS-SIGN":okx_sign(ts,method,endpoint,body,secret),"OK-ACCESS-TIMESTAMP":ts,"OK-ACCESS-PASSPHRASE":passphrase,"Content-Type":"application/json"}
    base = "https://www.okx.com"
    return fetch_url(f"{base}{path}" if method=="GET" else f"{base}{endpoint}", method, hdrs, body if method=="POST" else None)

def okx_balance(api_key, secret, passphrase):
    d = okx_req("/api/v5/account/balance","GET",{},api_key,secret,passphrase)
    if "error" in d: return {"error": d["error"]}
    try:
        details = d["data"][0]["details"]
        usdt = next((float(x["cashBal"]) for x in details if x["ccy"]=="USDT"), 0)
        return {"usdt": round(usdt,2),"exchange":"OKX","ok":True}
    except Exception: return {"error": "parse_error"}

def okx_order(symbol, side, qty, api_key, secret, passphrase):
    inst = symbol.replace("USDT","-USDT")
    return okx_req("/api/v5/trade/order","POST",{"instId":inst,"tdMode":"cash","side":"buy" if side=="BUY" else "sell","ordType":"market","sz":str(round(qty,6))},api_key,secret,passphrase)

# MEXC
def mexc_sign(params, secret):
    q = urllib.parse.urlencode(params)
    return hmac.new(secret.encode(), q.encode(), hashlib.sha256).hexdigest()

def mexc_req(endpoint, params, api_key, secret, method="GET"):
    params["timestamp"] = int(time.time() * 1000)
    params["signature"] = mexc_sign(params, secret)
    q = urllib.parse.urlencode(params)
    base = "https://api.mexc.com"
    hdrs = {"X-MEXC-APIKEY": api_key, "Content-Type": "application/json"}
    if method == "GET":
        return fetch_url(f"{base}{endpoint}?{q}", headers=hdrs)
    return fetch_url(f"{base}{endpoint}?{q}", "POST", hdrs)

def mexc_balance(api_key, secret):
    d = mexc_req("/api/v3/account", {}, api_key, secret)
    if "error" in d or "balances" not in d: return {"error": d.get("error","err")}
    usdt = next((float(b["free"]) for b in d["balances"] if b["asset"]=="USDT"), 0)
    return {"usdt": round(usdt,2), "exchange": "MEXC", "ok": True}

def mexc_order(symbol, side, qty, api_key, secret):
    return mexc_req("/api/v3/order", {"symbol":symbol,"side":side,"type":"MARKET","quantity":str(round(qty,6))}, api_key, secret, "POST")