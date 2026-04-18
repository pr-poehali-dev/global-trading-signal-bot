"""Pump-детектор крон: вызывается каждые 5 минут, сканирует 80+ пар на памп-активность."""
import json
import urllib.request

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json"
}

PUMP_SCANNER_URL = "https://functions.poehali.dev/4b074d99-4dd2-412c-904d-50db2bf5fbed"

def handler(event: dict, context) -> dict:
    """Запускает сканирование памп-активности на 80+ парах Binance."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    try:
        req = urllib.request.Request(
            f"{PUMP_SCANNER_URL}?action=scan",
            headers={"User-Agent": "PumpCron/2.0"})
        with urllib.request.urlopen(req, timeout=28) as r:
            result = json.loads(r.read().decode())
        found = result.get("found", 0)
        analyzed = result.get("analyzed", 0)
        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({
                "ok": True,
                "analyzed": analyzed,
                "found": found,
                "signals": result.get("signals", [])
            })
        }
    except Exception as e:
        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({"ok": False, "error": str(e)})
        }
