"""
PumpBot Cron — запускается каждые 5 минут.
Параллельно сканирует Binance, Bybit, OKX, MEXC
(каждая биржа — отдельный HTTP-запрос ~8-10 сек).
"""
import json
import urllib.request
import threading

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}

PUMP_URL   = "https://functions.poehali.dev/4b074d99-4dd2-412c-904d-50db2bf5fbed"
EXCHANGES  = ["Binance", "Bybit", "OKX", "MEXC"]

def scan_exchange(exchange: str, results: dict):
    """Сканирует одну биржу и сохраняет результат."""
    try:
        url = f"{PUMP_URL}?action=scan&exchange={exchange}"
        req = urllib.request.Request(url, headers={"User-Agent": "PumpCron/3.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode())
        results[exchange] = {
            "found":    data.get("found", 0),
            "analyzed": data.get("analyzed", 0),
            "signals":  data.get("signals", []),
        }
    except Exception as e:
        results[exchange] = {"found": 0, "analyzed": 0, "error": str(e)}

def handler(event: dict, context) -> dict:
    """Параллельный скан всех бирж — Binance, Bybit, OKX, MEXC."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    results: dict = {}
    threads = [
        threading.Thread(target=scan_exchange, args=(ex, results))
        for ex in EXCHANGES
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=26)

    total_found    = sum(r.get("found", 0)    for r in results.values())
    total_analyzed = sum(r.get("analyzed", 0) for r in results.values())
    all_signals    = []
    for r in results.values():
        all_signals.extend(r.get("signals", []))
    all_signals.sort(key=lambda x: x.get("score", 0), reverse=True)

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps({
            "ok":       True,
            "analyzed": total_analyzed,
            "found":    total_found,
            "signals":  all_signals[:20],
            "by_exchange": {k: {"found": v.get("found", 0), "analyzed": v.get("analyzed", 0)}
                            for k, v in results.items()},
        })
    }
