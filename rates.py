import os
import time
import logging
from datetime import datetime, timedelta
import requests

# Ключ ExchangeRate-API (можно переопределить через переменную окружения)
EXCHANGE_API_KEY = os.environ.get(
    "EXCHANGE_API_KEY", "438c515f5cefbf6cf1bcb921"
)

_cache = {"rates": None, "time": 0}

FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "RUB": "🇷🇺", "GBP": "🇬🇧",
    "JPY": "🇯🇵", "CNY": "🇨🇳", "KZT": "🇰🇿", "UAH": "🇺🇦",
    "BYN": "🇧🇾", "TRY": "🇹🇷", "CHF": "🇨🇭", "CAD": "🇨🇦",
    "AUD": "🇦🇺", "PLN": "🇵🇱", "INR": "🇮🇳", "KRW": "🇰🇷",
    "AED": "🇦🇪", "AMD": "🇦🇲", "GEL": "🇬🇪", "UZS": "🇺🇿",
    "AZN": "🇦🇿", "KGS": "🇰🇬", "THB": "🇹🇭", "BRL": "🇧🇷",
}


def flag(code: str) -> str:
    return FLAGS.get(code, "💱")


def format_number(x: float) -> str:
    if x >= 1000:
        return f"{x:,.2f}".replace(",", " ").replace(".", ",")
    if x >= 1:
        return f"{x:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{x:.6f}".rstrip("0").rstrip(".").replace(".", ",")


def _fetch_exchangerate_api():
    """ExchangeRate-API v6. База — USD."""
    if not EXCHANGE_API_KEY:
        raise ValueError("EXCHANGE_API_KEY не задан")
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"
    r = requests.get(url, timeout=10).json()
    if r.get("result") != "success":
        raise ValueError(f"ExchangeRate-API: {r.get('error-type', 'unknown')}")
    conv = r["conversion_rates"]
    rub = conv["RUB"]
    rates = {c: rub / v for c, v in conv.items() if v}
    rates["RUB"] = 1.0
    return rates


def _fetch_open_er():
    r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10).json()
    if r.get("result") != "success":
        raise ValueError("open.er-api error")
    rub = r["rates"]["RUB"]
    rates = {c: rub / v for c, v in r["rates"].items()}
    rates["RUB"] = 1.0
    return rates


def _fetch_cbr():
    d = requests.get(
        "https://www.cbr-xml-daily.ru/daily_json.js", timeout=10
    ).json()
    rates = {"RUB": 1.0}
    for c, info in d["Valute"].items():
        rates[c] = info["Value"] / info["Nominal"]
    return rates


def get_rates():
    """Курсы с базой RUB. Приоритет: ExchangeRate-API → open.er → ЦБ РФ."""
    now = time.time()
    if _cache["rates"] and now - _cache["time"] < 600:
        return _cache["rates"]

    for name, fetcher in (
        ("ExchangeRate-API", _fetch_exchangerate_api),
        ("open.er-api", _fetch_open_er),
        ("ЦБ РФ", _fetch_cbr),
    ):
        try:
            rates = fetcher()
            if rates and "RUB" in rates:
                _cache.update(rates=rates, time=now)
                return rates
        except Exception as e:
            logging.warning(f"{name} fail: {e}")

    logging.error("Все источники курсов недоступны")
    return None


def get_history(code: str, days: int = 7):
    """Архив ЦБ РФ. Выходные пропускаются."""
    today = datetime.now()
    out = []
    for i in range(days):
        d = today - timedelta(days=i)
        url = (
            f"https://www.cbr-xml-daily.ru/archive/"
            f"{d.year}/{d.month:02d}/{d.day:02d}/daily_json.js"
        )
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            if code == "RUB":
                out.append((d.strftime("%d.%m"), 1.0))
            elif code in data.get("Valute", {}):
                info = data["Valute"][code]
                out.append((d.strftime("%d.%m"),
                            info["Value"] / info["Nominal"]))
        except Exception:
            continue
    out.reverse()
    return out


def _sparkline(values):
    chars = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    if hi == lo:
        return chars[0] * len(values)
    return "".join(
        chars[int((v - lo) / (hi - lo) * (len(chars) - 1))] for v in values
    )


def format_chart(code: str, history):
    values = [v for _, v in history]
    labels = [d for d, _ in history]
    delta = values[-1] - values[0]
    arrow = "🟢" if delta >= 0 else "🔴"
    pct = (delta / values[0] * 100) if values[0] else 0
    return (
        f"{flag(code)} {code} → RUB за {len(history)} дн.\n\n"
        f"{_sparkline(values)}\n"
        f"{labels[0]} → {labels[-1]}\n\n"
        f"📉 Мин: {format_number(min(values))}\n"
        f"📈 Макс: {format_number(max(values))}\n"
        f"💰 Сейчас: {format_number(values[-1])}\n"
        f"{arrow} Изменение: {format_number(delta)} ({pct:+.2f}%)"
    )