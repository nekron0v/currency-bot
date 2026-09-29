import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


# Пути к жирному шрифту — ищем первый доступный
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
    """Полупрозрачные '$' на фоне."""
    font = _load_font(80)
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    step = 130
    for row, y in enumerate(range(-40, size, step)):
        offset = (row % 2) * (step // 2)
        for x in range(-40 + offset, size, step):
            od.text((x, y), "$", font=font, fill=(255, 255, 255, 30))
    img.paste(overlay, (0, 0), overlay)


def _circle_symbol(draw, cx, cy, r, symbol, font):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(60, 60, 70))
    bbox = draw.textbbox((0, 0), symbol, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]),
              symbol, font=font, fill=(255, 255, 255))


def _swap_icon(draw, cx, cy, r, ss):
    """Две стрелки вверх/вниз в кружке."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(230, 235, 245))
    # Верхняя стрелка вниз
    ax = cx - 14 * ss
    draw.line([(ax, cy - 18 * ss), (ax, cy + 18 * ss)],
              fill=(70, 110, 210), width=4 * ss)
    draw.polygon([
        (ax - 8 * ss, cy + 10 * ss),
        (ax + 8 * ss, cy + 10 * ss),
        (ax, cy + 22 * ss),
    ], fill=(70, 110, 210))
    # Нижняя стрелка вверх
    ax = cx + 14 * ss
    draw.line([(ax, cy - 18 * ss), (ax, cy + 18 * ss)],
              fill=(70, 110, 210), width=4 * ss)
    draw.polygon([
        (ax - 8 * ss, cy - 10 * ss),
        (ax + 8 * ss, cy - 10 * ss),
        (ax, cy - 22 * ss),
    ], fill=(70, 110, 210))


def generate_card(from_code: str, from_amount: float,
                  to_code: str, to_amount: float,
                  base_size: int = 512) -> BytesIO:
    """
    Рисует квадратную карточку конвертации, похожую на @send.
    Возвращает BytesIO с PNG.
    """
    SS = 2                       # supersampling для сглаживания
    S = base_size * SS           # внутренний размер

    img = Image.new("RGB", (S, S), (40, 110, 200))
    _draw_gradient(img, (72, 155, 235), (35, 80, 170))
    _draw_pattern(img, S)

    # Белая карточка
    card = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    margin = 40 * SS
    cd.rounded_rectangle(
        [margin, margin, S - margin, S - margin],
        radius=60 * SS, fill=(255, 255, 255, 255),
    )
    img.paste(card, (0, 0), card)

    draw = ImageDraw.Draw(img)

    f_code = _load_font(46 * SS)
    f_amount = _load_font(60 * SS)
    f_sym = _load_font(50 * SS)

    left = margin + 55 * SS
    right = S - margin - 55 * SS
    top_y = margin + 115 * SS
    bot_y = S - margin - 115 * SS

    def row(code, amount, y):
        r = 46 * SS
        cx = left + r
        _circle_symbol(draw, cx, y, r,
                       CURRENCY_SYMBOLS.get(code, code[:1]), f_sym)
        tx = cx + r + 32 * SS
        bbox = draw.textbbox((0, 0), code, font=f_code)
        th = bbox[3] - bbox[1]
        draw.text((tx, y - th / 2 - bbox[1]),
                  code, font=f_code, fill=(30, 30, 40))
        text = _fmt(amount)
        bbox = draw.textbbox((0, 0), text, font=f_amount)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((right - tw - bbox[0], y - th / 2 - bbox[1]),
                  text, font=f_amount, fill=(30, 30, 40))

    row(from_code, from_amount, top_y)
    row(to_code, to_amount, bot_y)
    _swap_icon(draw, (margin + (S - margin)) // 2,
               (top_y + bot_y) // 2, 32 * SS, SS)

    img = img.resize((base_size, base_size), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf