"""Триггер автономного бота — вызывается каждые 5 минут по cron."""
import json
import urllib.request

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json"
}

AUTO_TRADE_URL = "https://functions.poehali.dev/228287c1-2207-42c1-94aa-88fda52f4f86"

def handler(event: dict, context) -> dict:
    """Запускает цикл авто-торговли бота."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    try:
        req = urllib.request.Request(
            f"{AUTO_TRADE_URL}?action=auto_run",
            headers={"User-Agent": "BotCron/1.0"})
        with urllib.request.urlopen(req, timeout=28) as r:
            result = json.loads(r.read().decode())
        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({"ok": True, "result": result})
        }
    except Exception as e:
        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({"ok": False, "error": str(e)})
        }
