import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


BOLD_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "RUB": "₽", "GBP": "£",
    "JPY": "¥", "CNY": "¥", "KZT": "₸", "TRY": "₺",
    "UAH": "₴", "BYN": "Br", "CHF": "Fr", "CAD": "C$",
    "AUD": "A$", "PLN": "zl", "INR": "₹", "KRW": "₩",
}

# ---------- Палитра (фиолетовые тона, отличные от @send) ----------
GRADIENT_TOP = (124, 58, 237)      # насыщенный violet
GRADIENT_BOTTOM = (49, 30, 100)    # глубокий indigo
PATTERN_COLOR = (255, 255, 255, 30)
CIRCLE_BG = (30, 27, 55)           # тёмный кружок под символ
CIRCLE_FG = (255, 255, 255)
TEXT_COLOR = (25, 22, 45)
SWAP_BG = (228, 220, 250)
SWAP_FG = (90, 60, 200)


def _load_font(size: int):
    for p in BOLD_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _fmt(x: float) -> str:
    if x >= 1000:
        return f"{x:,.2f}".replace(",", " ").replace(".", ",")
    if x >= 1:
        return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{x:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def _text_width(text: str, font) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _fit_font(text: str, max_width: int, start_size: int, min_size: int):
    size = start_size
    while size > min_size:
        f = _load_font(size)
        if _text_width(text, f) <= max_width:
            return f
        size -= 4
    return _load_font(min_size)


def _draw_gradient(img, top, bottom):
    w, h = img.size
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _draw_pattern(img, size):
    font = _load_font(80)
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    step = 130
    for row_idx, y in enumerate(range(-40, size, step)):
        offset = (row_idx % 2) * (step // 2)
        for x in range(-40 + offset, size, step):
            od.text((x, y), "$", font=font, fill=PATTERN_COLOR)
    img.paste(overlay, (0, 0), overlay)


def _circle_symbol(draw, cx, cy, r, symbol, font):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CIRCLE_BG)
    draw.text((cx, cy), symbol, font=font, fill=CIRCLE_FG, anchor="mm")


def _swap_icon(draw, cx, cy, r, ss):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SWAP_BG)
    color = SWAP_FG
    w = 5 * ss
    off = 12 * ss
    arr = 9 * ss
    hlen = 18 * ss
    # Левая стрелка вниз
    ax = cx - off
    draw.line([(ax, cy - hlen), (ax, cy + hlen)], fill=color, width=w)
    draw.polygon([
        (ax - arr, cy + hlen - arr),
        (ax + arr, cy + hlen - arr),
        (ax, cy + hlen + arr),
    ], fill=color)
    # Правая стрелка вверх
    ax = cx + off
    draw.line([(ax, cy - hlen), (ax, cy + hlen)], fill=color, width=w)
    draw.polygon([
        (ax - arr, cy - hlen + arr),
        (ax + arr, cy - hlen + arr),
        (ax, cy - hlen - arr),
    ], fill=color)


def generate_card(from_code: str, from_amount: float,
                  to_code: str, to_amount: float,
                  base_size: int = 512) -> BytesIO:
    SS = 2
    S = base_size * SS

    img = Image.new("RGB", (S, S), GRADIENT_TOP)
    _draw_gradient(img, GRADIENT_TOP, GRADIENT_BOTTOM)
    _draw_pattern(img, S)

    card = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    margin = 40 * SS
    cd.rounded_rectangle(
        [margin, margin, S - margin, S - margin],
        radius=60 * SS, fill=(255, 255, 255, 255),
    )
    img.paste(card, (0, 0), card)

    draw = ImageDraw.Draw(img)

    left = margin + 55 * SS
    right = S - margin - 55 * SS
    top_y = margin + 115 * SS
    bot_y = S - margin - 115 * SS

    r = 46 * SS
    circle_cx = left + r
    code_x = circle_cx + r + 30 * SS

    f_sym = _load_font(50 * SS)
    f_code = _load_font(46 * SS)

    def row(code: str, amount: float, y: int):
        _circle_symbol(draw, circle_cx, y, r,
                       CURRENCY_SYMBOLS.get(code, code[:1]), f_sym)

        # --- Код валюты: рисуем и измеряем реальную ширину ---
        code_w = _text_width(code, f_code)
        draw.text((code_x, y), code, font=f_code,
                  fill=TEXT_COLOR, anchor="lm")

        # --- Сколько места осталось под сумму (с отступом 24px) ---
        amount_max_w = right - (code_x + code_w) - 24 * SS

        # --- Сумма: автоподбор размера, выравнивание по правому краю ---
        text = _fmt(amount)
        f_amount = _fit_font(text, amount_max_w, 60 * SS, 22 * SS)
        draw.text((right, y), text, font=f_amount,
                  fill=TEXT_COLOR, anchor="rm")

    row(from_code, from_amount, top_y)
    row(to_code, to_amount, bot_y)

    _swap_icon(draw, S // 2, (top_y + bot_y) // 2, 34 * SS, SS)

    img = img.resize((base_size, base_size), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf