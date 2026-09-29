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

# ---------- ФИОЛЕТОВАЯ ПАЛИТРА ----------
GRADIENT_TOP = (124, 76, 200)
GRADIENT_BOTTOM = (72, 30, 128)
PATTERN_COLOR = (255, 255, 255, 26)
CARD_BG = (255, 255, 255)
CIRCLE_BG = (170, 170, 178)
CIRCLE_FG = (255, 255, 255)
TEXT_COLOR = (12, 12, 18)
LINE_COLOR = (228, 228, 234)
SWAP_BG = (232, 224, 250)
SWAP_FG = (110, 62, 190)


def _load_font(size):
    for p in BOLD_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _fmt(x):
    if x >= 1:
        return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{x:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def _measure(text, font):
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit(text, max_width, start_size, min_size):
    size = start_size
    while size > min_size:
        f = _load_font(size)
        w, _ = _measure(text, f)
        if w <= max_width:
            return f
        size -= 2
    return _load_font(min_size)


def _draw_lm(draw, x, y, text, font, fill):
    bbox = font.getbbox(text)
    h = bbox[3] - bbox[1]
    draw.text((x - bbox[0], y - h / 2 - bbox[1]), text, font=font, fill=fill)
    return bbox[2] - bbox[0]


def _draw_rm(draw, x, y, text, font, fill):
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((x - w - bbox[0], y - h / 2 - bbox[1]), text, font=font, fill=fill)


def _draw_mm(draw, x, y, text, font, fill):
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((x - w / 2 - bbox[0], y - h / 2 - bbox[1]),
              text, font=font, fill=fill)


def _gradient(img, top, bottom):
    w, h = img.size
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)


def _pattern(img, size):
    """Крупные $ в шахматном порядке — как у @send."""
    font = _load_font(int(size * 0.14))
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    step = int(size * 0.22)
    for row_idx, y in enumerate(range(-step, size + step, step)):
        off = (row_idx % 2) * (step // 2)
        for x in range(-step + off, size + step, step):
            ld.text((x, y), "$", font=font, fill=PATTERN_COLOR)
    img.paste(layer, (0, 0), layer)


def _circle_symbol(draw, cx, cy, r, symbol, font):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CIRCLE_BG)
    _draw_mm(draw, cx, cy, symbol, font, CIRCLE_FG)


def _swap_icon(draw, cx, cy, r):
    """Компактный ⇅ — тонкие стрелки, как у @send."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SWAP_BG)
    color = SWAP_FG
    # Длина стрелки внутри кружка
    h = int(r * 0.95)
    w = max(2, int(r * 0.16))
    head = int(r * 0.32)
    gap = int(r * 0.30)

    y_top = cy - h // 2
    y_bot = cy + h // 2

    # Левая стрелка — вниз
    x1 = cx - gap
    draw.line([(x1, y_top), (x1, y_bot)], fill=color, width=w)
    draw.polygon([
        (x1 - head, y_bot - head),
        (x1 + head, y_bot - head),
        (x1, y_bot + head // 2),
    ], fill=color)

    # Правая стрелка — вверх
    x2 = cx + gap
    draw.line([(x2, y_top), (x2, y_bot)], fill=color, width=w)
    draw.polygon([
        (x2 - head, y_top + head),
        (x2 + head, y_top + head),
        (x2, y_top - head // 2),
    ], fill=color)


def generate_card(from_code, from_amount, to_code, to_amount, base_size=512):
    SS = 2
    S = base_size * SS

    # Фон
    img = Image.new("RGB", (S, S), GRADIENT_TOP)
    _gradient(img, GRADIENT_TOP, GRADIENT_BOTTOM)
    _pattern(img, S)

    draw = ImageDraw.Draw(img)

    # Карточка — меньше, чем была (больше фона по краям, как у @send)
    margin = int(S * 0.125)
    radius = int(S * 0.09)
    draw.rounded_rectangle(
        [margin, margin, S - margin, S - margin],
        radius=radius, fill=CARD_BG,
    )

    # Внутренние горизонтальные отступы
    pad_x = int(S * 0.055)
    inner_x0 = margin + pad_x
    inner_x1 = S - margin - pad_x

    # Позиции строк — 34% и 66% от всего полотна (симметрично центру)
    row1_y = int(S * 0.345)
    row2_y = int(S * 0.655)
    mid_y = int(S * 0.5)

    # Кружок символа валюты — меньше, чем был
    circle_r = int(S * 0.048)
    circle_cx = inner_x0 + circle_r
    code_x = circle_cx + circle_r + int(S * 0.035)

    # Символы и шрифты
    f_sym = _load_font(int(S * 0.052))
    f_code = _load_font(int(S * 0.085))
    amount_size = int(S * 0.085)
    min_amount_size = int(S * 0.045)

    def row(code, amount, y):
        _circle_symbol(draw, circle_cx, y, circle_r,
                       CURRENCY_SYMBOLS.get(code, code[:1]), f_sym)

        code_w = _draw_lm(draw, code_x, y, code, f_code, TEXT_COLOR)

        text = _fmt(amount)
        avail_w = inner_x1 - (code_x + code_w) - int(S * 0.02)
        f_amount = _fit(text, avail_w, amount_size, min_amount_size)
        _draw_rm(draw, inner_x1, y, text, f_amount, TEXT_COLOR)

    row(from_code, from_amount, row1_y)
    row(to_code, to_amount, row2_y)

    # Разделительная линия — очень светлая, с прорезью под swap
    swap_r = int(S * 0.045)
    line_w = max(1, int(S * 0.0022))
    gap = int(S * 0.014)
    line_y = mid_y
    draw.line([(inner_x0, line_y), (S // 2 - swap_r - gap, line_y)],
              fill=LINE_COLOR, width=line_w)
    draw.line([(S // 2 + swap_r + gap, line_y), (inner_x1, line_y)],
              fill=LINE_COLOR, width=line_w)

    _swap_icon(draw, S // 2, mid_y, swap_r)

    # Финальный ресайз со сглаживанием
    img = img.resize((base_size, base_size), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf