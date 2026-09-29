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

# ---------- ФИОЛЕТОВАЯ ПАЛИТРА (вместо синей @send) ----------
GRADIENT_TOP = (139, 92, 246)      # насыщенный violet
GRADIENT_BOTTOM = (76, 29, 149)    # глубокий purple
PATTERN_COLOR = (255, 255, 255, 22)
CARD_BG = (255, 255, 255)
CIRCLE_BG = (186, 186, 192)        # серые кружки как у @send
CIRCLE_FG = (255, 255, 255)
TEXT_COLOR = (12, 12, 18)
LINE_COLOR = (235, 235, 240)
SWAP_BG = (237, 233, 254)
SWAP_FG = (124, 58, 237)


def _load_font(size):
    for p in BOLD_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _fmt(x):
    """Без разделителя тысяч, точка → запятая. 8436.88 → '8436,88'."""
    if x >= 1:
        return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{x:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def _measure(text, font):
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit(text, max_width, start_size, min_size):
    """Подбирает размер шрифта, чтобы text влез в max_width."""
    size = start_size
    while size > min_size:
        f = _load_font(size)
        w, _ = _measure(text, f)
        if w <= max_width:
            return f
        size -= 2
    return _load_font(min_size)


def _draw_lm(draw, x, y, text, font, fill):
    """Рисует текст с left-middle anchor через bbox. Возвращает ширину."""
    bbox = font.getbbox(text)
    h = bbox[3] - bbox[1]
    draw.text((x - bbox[0], y - h / 2 - bbox[1]),
              text, font=font, fill=fill)
    return bbox[2] - bbox[0]


def _draw_rm(draw, x, y, text, font, fill):
    """right-middle anchor."""
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((x - w - bbox[0], y - h / 2 - bbox[1]),
              text, font=font, fill=fill)


def _draw_mm(draw, x, y, text, font, fill):
    """middle-middle anchor."""
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
    """Крупные $ в шахматном порядке, едва заметные."""
    font = _load_font(int(size * 0.18))
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    step = int(size * 0.24)
    for row_idx, y in enumerate(range(-step, size + step, step)):
        off = (row_idx % 2) * (step // 2)
        for x in range(-step + off, size + step, step):
            ld.text((x, y), "$", font=font, fill=PATTERN_COLOR)
    img.paste(layer, (0, 0), layer)


def _circle_symbol(draw, cx, cy, r, symbol, font):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CIRCLE_BG)
    _draw_mm(draw, cx, cy, symbol, font, CIRCLE_FG)


def _swap_icon(draw, cx, cy, r):
    """⇅ в светлом кружке."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SWAP_BG)
    color = SWAP_FG
    arrow_len = int(r * 1.1)
    head = int(r * 0.4)
    width = max(2, int(r * 0.2))
    gap = int(r * 0.35)

    y_top = cy - arrow_len // 2
    y_bot = cy + arrow_len // 2

    # Левая стрелка вниз
    x1 = cx - gap
    draw.line([(x1, y_top), (x1, y_bot)], fill=color, width=width)
    draw.polygon([(x1 - head, y_bot - head),
                  (x1 + head, y_bot - head),
                  (x1, y_bot + head // 2)], fill=color)

    # Правая стрелка вверх
    x2 = cx + gap
    draw.line([(x2, y_top), (x2, y_bot)], fill=color, width=width)
    draw.polygon([(x2 - head, y_top + head),
                  (x2 + head, y_top + head),
                  (x2, y_top - head // 2)], fill=color)


def generate_card(from_code, from_amount, to_code, to_amount, base_size=512):
    SS = 2
    S = base_size * SS

    img = Image.new("RGB", (S, S), GRADIENT_TOP)
    _gradient(img, GRADIENT_TOP, GRADIENT_BOTTOM)
    _pattern(img, S)

    draw = ImageDraw.Draw(img)

    # Белая скруглённая карточка
    margin = int(S * 0.075)
    radius = int(S * 0.11)
    draw.rounded_rectangle(
        [margin, margin, S - margin, S - margin],
        radius=radius, fill=CARD_BG,
    )

    # Внутренние отступы
    pad = int(S * 0.065)
    inner_x0 = margin + pad
    inner_x1 = S - margin - pad
    inner_y0 = margin + pad
    inner_y1 = S - margin - pad
    inner_h = inner_y1 - inner_y0

    # Позиции строк (22% и 78% от внутренней высоты)
    row1_y = inner_y0 + int(inner_h * 0.22)
    row2_y = inner_y0 + int(inner_h * 0.78)
    mid_y = (row1_y + row2_y) // 2

    # Кружок символа
    circle_r = int(S * 0.058)
    circle_cx = inner_x0 + circle_r
    code_x = circle_cx + circle_r + int(S * 0.04)

    # Разделительная линия с прорезью под swap
    swap_r = int(S * 0.05)
    line_w = max(1, int(S * 0.003))
    gap_around = int(S * 0.018)
    draw.line([(inner_x0, mid_y), (S // 2 - swap_r - gap_around, mid_y)],
              fill=LINE_COLOR, width=line_w)
    draw.line([(S // 2 + swap_r + gap_around, mid_y), (inner_x1, mid_y)],
              fill=LINE_COLOR, width=line_w)

    # Шрифты
    f_sym = _load_font(int(S * 0.062))
    f_code = _load_font(int(S * 0.095))
    amount_size = int(S * 0.105)
    min_amount_size = int(S * 0.05)

    def row(code, amount, y):
        _circle_symbol(draw, circle_cx, y, circle_r,
                       CURRENCY_SYMBOLS.get(code, code[:1]), f_sym)

        # Код — рисуем и сразу получаем РЕАЛЬНУЮ ширину
        code_w = _draw_lm(draw, code_x, y, code, f_code, TEXT_COLOR)

        # Сумма — считаем свободное место от реального правого края кода
        text = _fmt(amount)
        avail_w = inner_x1 - (code_x + code_w) - int(S * 0.02)
        f_amount = _fit(text, avail_w, amount_size, min_amount_size)
        _draw_rm(draw, inner_x1, y, text, f_amount, TEXT_COLOR)

    row(from_code, from_amount, row1_y)
    row(to_code, to_amount, row2_y)

    _swap_icon(draw, S // 2, mid_y, swap_r)

    # Финальный ресайз — сглаживание
    img = img.resize((base_size, base_size), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf