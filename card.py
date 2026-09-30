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


def _pattern(img, W, H):
    font = _load_font(int(H * 0.15))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    step = int(H * 0.24)
    for row_idx, y in enumerate(range(-step, H + step, step)):
        off = (row_idx % 2) * (step // 2)
        for x in range(-step + off, W + step, step):
            ld.text((x, y), "$", font=font, fill=PATTERN_COLOR)
    img.paste(layer, (0, 0), layer)


def _circle_symbol(draw, cx, cy, r, symbol, font):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CIRCLE_BG)
    _draw_mm(draw, cx, cy, symbol, font, CIRCLE_FG)


def _swap_icon(draw, cx, cy, r):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SWAP_BG)
    color = SWAP_FG
    h = int(r * 0.9)
    w = max(2, int(r * 0.16))
    head = int(r * 0.3)
    gap = int(r * 0.28)

    y_top = cy - h // 2
    y_bot = cy + h // 2

    x1 = cx - gap
    draw.line([(x1, y_top), (x1, y_bot)], fill=color, width=w)
    draw.polygon([
        (x1 - head, y_bot - head),
        (x1 + head, y_bot - head),
        (x1, y_bot + head // 2),
    ], fill=color)

    x2 = cx + gap
    draw.line([(x2, y_top), (x2, y_bot)], fill=color, width=w)
    draw.polygon([
        (x2 - head, y_top + head),
        (x2 + head, y_top + head),
        (x2, y_top - head // 2),
    ], fill=color)


def generate_card(from_code, from_amount, to_code, to_amount,
                  base_w=720, base_h=450):
    """Горизонтальная 720x450 (16:10), пропорции выверены по @send."""
    SS = 2
    W = base_w * SS           # 1440
    H = base_h * SS           # 900

    img = Image.new("RGB", (W, H), GRADIENT_TOP)
    _gradient(img, GRADIENT_TOP, GRADIENT_BOTTOM)
    _pattern(img, W, H)

    draw = ImageDraw.Draw(img)

    # ----- Карточка (отступы X < Y, как у @send) -----
    margin_x = int(W * 0.070)        # 100 из 1440 = 7.0%
    margin_y = int(H * 0.142)        # 128 из 900 = 14.2%
    radius = int(H * 0.10)
    draw.rounded_rectangle(
        [margin_x, margin_y, W - margin_x, H - margin_y],
        radius=radius, fill=CARD_BG,
    )

    # Внутренний отступ карточки
    pad = int(H * 0.05)
    inner_x0 = margin_x + pad
    inner_x1 = W - margin_x - pad

    # ----- Кружок символа валюты -----
    circle_r = int(H * 0.058)                          # 52 из 900
    circle_cx = inner_x0 + circle_r
    code_x = circle_cx + circle_r + int(H * 0.042)

    # ----- Позиции строк -----
    row1_y = int(H * 0.254)
    row2_y = int(H * 0.725)
    mid_y = H // 2

    # ----- Шрифты (одинаковые для кода и суммы) -----
    f_sym = _load_font(int(H * 0.056))
    f_code = _load_font(int(H * 0.092))
    amount_size = int(H * 0.092)
    min_amount_size = int(H * 0.045)

    def row(code, amount, y):
        _circle_symbol(draw, circle_cx, y, circle_r,
                       CURRENCY_SYMBOLS.get(code, code[:1]), f_sym)
        code_w = _draw_lm(draw, code_x, y, code, f_code, TEXT_COLOR)
        text = _fmt(amount)
        avail_w = inner_x1 - (code_x + code_w) - int(H * 0.03)
        f_amount = _fit(text, avail_w, amount_size, min_amount_size)
        _draw_rm(draw, inner_x1, y, text, f_amount, TEXT_COLOR)

    row(from_code, from_amount, row1_y)
    row(to_code, to_amount, row2_y)

    # ----- Разделитель с прорезью под swap -----
    swap_r = int(H * 0.046)
    line_w = max(1, int(H * 0.0022))
    gap = int(H * 0.014)
    draw.line([(inner_x0, mid_y), (W // 2 - swap_r - gap, mid_y)],
              fill=LINE_COLOR, width=line_w)
    draw.line([(W // 2 + swap_r + gap, mid_y), (inner_x1, mid_y)],
              fill=LINE_COLOR, width=line_w)

    _swap_icon(draw, W // 2, mid_y, swap_r)

    img = img.resize((base_w, base_h), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf