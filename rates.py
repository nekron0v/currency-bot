import time
import logging
from datetime import datetime, timedelta
import requests

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


def get_rates():
    """open.er-api.com → fallback на ЦБ РФ. База — RUB."""
    now = time.time()
    if _cache["rates"] and now - _cache["time"] < 600:
        return _cache["rates"]
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10).json()
        if r.get("result") != "success":
            raise ValueError("API error")
        rub = r["rates"]["RUB"]
        rates = {c: rub / v for c, v in r["rates"].items()}
        rates["RUB"] = 1.0
        _cache.update(rates=rates, time=now)
        return rates
    except Exception as e:
        logging.warning(f"open.er-api fail: {e}, fallback to CBR")
    try:
        d = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10).json()
        rates = {"RUB": 1.0}
        for c, info in d["Valute"].items():
            rates[c] = info["Value"] / info["Nominal"]
        _cache.update(rates=rates, time=now)
        return rates
    except Exception as e:
        logging.error(f"CBR fail: {e}")
        return None


def get_history(code: str, days: int = 7):
    """История с архива ЦБ РФ. Выходные пропускаются (ЦБ не публикует)."""
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
                out.append((d.strftime("%d.%m"), info["Value"] / info["Nominal"]))
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