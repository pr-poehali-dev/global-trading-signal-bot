"""
PumpBot Cron — запускается каждые 5 минут.
1. Параллельно сканирует все биржи (Binance, Bybit, OKX, MEXC)
2. Запускает тик MEXC Auto-Bot (проверяет TP/SL, открывает новые позиции)
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

PUMP_URL     = "https://functions.poehali.dev/4b074d99-4dd2-412c-904d-50db2bf5fbed"
MEXC_BOT_URL = "https://functions.poehali.dev/d798c17a-255c-4fb0-869f-37ff1213fbbe"
EXCHANGES    = ["Binance", "Bybit", "OKX", "MEXC"]


def scan_exchange(exchange: str, results: dict):
    try:
        url = f"{PUMP_URL}?action=scan&exchange={exchange}"
        req = urllib.request.Request(url, headers={"User-Agent": "PumpCron/4.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode())
        results[exchange] = {
            "found":    data.get("found", 0),
            "analyzed": data.get("analyzed", 0),
            "signals":  data.get("signals", []),
        }
    except Exception as e:
        results[exchange] = {"found": 0, "analyzed": 0, "error": str(e)}


def run_mexc_bot_tick(results: dict):
    """Тик MEXC Auto-Bot."""
    if not MEXC_BOT_URL:
        results["mexc_bot"] = {"skipped": True, "reason": "url not set"}
        return
    try:
        req = urllib.request.Request(
            f"{MEXC_BOT_URL}?action=tick",
            headers={"User-Agent": "PumpCron/4.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            results["mexc_bot"] = json.loads(r.read().decode())
    except Exception as e:
        results["mexc_bot"] = {"error": str(e)}


def handler(event: dict, context) -> dict:
    """Параллельный скан всех бирж + тик MEXC-бота."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    results: dict = {}

    # Читаем URL mexc-bot из func2url (инжектируется платформой)
    global MEXC_BOT_URL
    try:
        import os
        func2url_path = os.path.join(os.path.dirname(__file__), "..", "func2url.json")
        with open(func2url_path) as f:
            urls = json.load(f)
            MEXC_BOT_URL = urls.get("mexc-bot", "")
    except Exception:
        pass

    threads = [
        threading.Thread(target=scan_exchange, args=(ex, results))
        for ex in EXCHANGES
    ]
    # Тик бота — параллельно со сканом
    bot_thread = threading.Thread(target=run_mexc_bot_tick, args=(results,))
    threads.append(bot_thread)

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=26)

    total_found    = sum(results.get(ex, {}).get("found", 0) for ex in EXCHANGES)
    total_analyzed = sum(results.get(ex, {}).get("analyzed", 0) for ex in EXCHANGES)
    all_signals    = []
    for ex in EXCHANGES:
        all_signals.extend(results.get(ex, {}).get("signals", []))
    all_signals.sort(key=lambda x: x.get("score", 0), reverse=True)

    return {
        "statusCode": 200,
        "headers": HEADERS,
        "body": json.dumps({
            "ok":       True,
            "analyzed": total_analyzed,
            "found":    total_found,
            "signals":  all_signals[:20],
            "mexc_bot": results.get("mexc_bot", {}),
            "by_exchange": {
                k: {"found": results.get(k, {}).get("found", 0),
                    "analyzed": results.get(k, {}).get("analyzed", 0)}
                for k in EXCHANGES
            },
        })
    }