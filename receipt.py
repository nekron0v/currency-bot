import re
import logging
from io import BytesIO

CURRENCY_SIGNS = {
    "USD": ["$", "usd", "долл"],
    "EUR": ["€", "eur", "евро"],
    "RUB": ["₽", "rub", "руб", "rur"],
    "KZT": ["₸", "kzt", "тенге"],
    "TRY": ["₺", "try", "лир"],
    "GBP": ["£", "gbp", "фунт"],
}

NUMBER_RE = r"\d{1,3}(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?|\d+[.,]\d{1,2}|\d+"
TOTAL_KEYWORDS = r"итог|total|к оплате|сумма|итого|сумма к оплате"


def ocr_space(image_bytes: bytes, apikey: str = "helloworld") -> str:
    """Облачный OCR.space. Ключ 'helloworld' — демо, лимит ~500/день."""
    import requests
    resp = requests.post(
        "https://api.ocr.space/parse/image",
        files={"file": ("receipt.jpg", image_bytes, "image/jpeg")},
        data={"apikey": apikey, "language": "rus", "OCREngine": 2},
        timeout=30,
    )
    data = resp.json()
    if data.get("IsErroredOnProcessing"):
        raise RuntimeError(data.get("ErrorMessage", "OCR error"))
    return data["ParsedResults"][0]["ParsedText"]


def ocr_tesseract(image_bytes: bytes) -> str:
    """Локальный OCR. На Render не сработает без Docker — только fallback."""
    import pytesseract
    from PIL import Image
    img = Image.open(BytesIO(image_bytes))
    w, h = img.size
    if w < 1000:
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
    return pytesseract.image_to_string(img, lang="rus+eng")


def _to_float(s: str):
    s = s.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def detect_currency(text: str):
    low = text.lower()
    for code, markers in CURRENCY_SIGNS.items():
        if any(m in low for m in markers):
            return code
    return None


def parse_receipt(text: str) -> dict:
    """
    Возвращает:
      {"amount": float|None, "currency": str|None,
       "confidence": "high"|"medium"|"low", "reason": str}
    """
    currency = detect_currency(text) or "RUB"

    # 1. Приоритет — строка со словом «Итого»
    for line in text.splitlines():
        if re.search(TOTAL_KEYWORDS, line, re.IGNORECASE):
            for n in re.findall(NUMBER_RE, line):
                v = _to_float(n)
                if v and 1 <= v <= 10_000_000:
                    return {
                        "amount": v, "currency": currency,
                        "confidence": "high",
                        "reason": "нашёл строку «итого»",
                    }

    # 2. Fallback — максимум из чисел
    nums = []
    for n in re.findall(NUMBER_RE, text):
        v = _to_float(n)
        if v and 1 <= v <= 10_000_000:
            nums.append(v)

    if not nums:
        return {
            "amount": None, "currency": currency,
            "confidence": "low", "reason": "не нашёл ни одного числа",
        }

    return {
        "amount": max(nums), "currency": currency,
        "confidence": "medium", "reason": "взял максимум из чисел",
    }


def parse_manual(text: str):
    """'120 USD' → (120.0, 'USD', 'RUB'); '120 USD EUR' → (120.0, 'USD', 'EUR')."""
    text = text.strip().upper()
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*([A-Z]{3})?(?:\s+([A-Z]{3}))?$", text)
    if not m:
        return None
    amount = _to_float(m.group(1))
    if not amount:
        return None
    return amount, m.group(2) or "RUB", m.group(3) or "RUB"