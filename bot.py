import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import time as dtime, timezone, timedelta

import uvicorn
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route

from telegram import (
    Update, InlineQueryResultArticle, InlineQueryResultPhoto,
    InputTextMessageContent,
    InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, InlineQueryHandler,
    MessageHandler, CallbackQueryHandler, filters, ContextTypes,
)

from rates import get_rates, get_history, format_chart, flag, format_number
from receipt import ocr_space, ocr_tesseract, parse_receipt, parse_manual
from storage import load_subs, save_subs
from card import generate_card

# ---------- Конфиг ----------
TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", 10000))
OCRSPACE_KEY = os.environ.get("OCRSPACE_KEY", "helloworld")

COOLDOWN = 3600
CHECK_INTERVAL = 1800
DIGEST_HOUR = 9
DIGEST_MINUTE = 0
DIGEST_CODES = ["USD", "EUR", "CNY", "KZT", "TRY"]
PENDING = {}
PENDING_TTL = 600
MSK = timezone(timedelta(hours=3))

if not TOKEN:
    raise SystemExit("BOT_TOKEN не задан в переменных окружения")


# ---------- Помощники ----------
def cleanup_pending():
    now = time.time()
    for uid in list(PENDING):
        if now - PENDING[uid]["ts"] > PENDING_TTL:
            del PENDING[uid]


def build_receipt_result(amount, cur, rates):
    rub = amount * rates[cur]
    usd = rub / rates["USD"]
    eur = rub / rates["EUR"]
    return (
        f"🧾 {flag(cur)} {format_number(amount)} {cur}\n\n"
        f"≈ 🇷🇺 {format_number(rub)} RUB\n"
        f"≈ 🇺🇸 {format_number(usd)} USD\n"
        f"≈ 🇪🇺 {format_number(eur)} EUR"
    )


def _card_url(amount, frm, to) -> str:
    amount_str = f"{amount:g}".replace(",", ".")
    return f"{WEBHOOK_URL}/card/{amount_str}/{frm}/{to}.png"


# ---------- Inline ----------
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip().upper()
    parts = query.split()
    rates = get_rates()
    if not rates:
        await update.inline_query.answer([], cache_time=60)
        return
    results = []

    if len(parts) == 3:
        try:
            amount = float(parts[0].replace(",", "."))
        except ValueError:
            await update.inline_query.answer([], cache_time=60)
            return
        f, t = parts[1], parts[2]
        if f not in rates or t not in rates:
            await update.inline_query.answer([], cache_time=60)
            return
        res = amount * rates[f] / rates[t]
        text = (
            f"{flag(f)} {format_number(amount)} {f} "
            f"= {flag(t)} {format_number(res)} {t}"
        )

        if WEBHOOK_URL:
            card_url = _card_url(amount, f, t)
            results.append(InlineQueryResultPhoto(
                id="card",
                photo_url=card_url,
                thumbnail_url=card_url,
                title=text,
                description="Карточка конвертации",
                caption=text,
                photo_width=512,
                photo_height=512,
            ))

        results.append(InlineQueryResultArticle(
            id="conv_text",
            title=text,
            description="Отправить текстом",
            input_message_content=InputTextMessageContent(message_text=text),
        ))

    elif len(parts) == 1 and parts[0] in rates:
        code = parts[0]
        text = f"{flag(code)} 1 {code} = {format_number(rates[code])} RUB 🇷🇺"
        results.append(InlineQueryResultArticle(
            id="single", title=text, description="Курс к рублю",
            input_message_content=InputTextMessageContent(message_text=text),
        ))
        for other in ("USD", "EUR"):
            if other == code:
                continue
            cross = rates[code] / rates[other]
            line = (
                f"{flag(code)} 1 {code} = "
                f"{format_number(cross)} {other} {flag(other)}"
            )
            results.append(InlineQueryResultArticle(
                id=f"x_{other}", title=line, description="Кросс-курс",
                input_message_content=InputTextMessageContent(message_text=line),
            ))

    elif len(parts) == 2 and parts[0] in rates and (
        parts[1] == "CHART" or parts[1].isdigit()
    ):
        code = parts[0]
        days = 7 if parts[1] == "CHART" else min(int(parts[1]), 30)
        hist = get_history(code, days)
        if len(hist) >= 2:
            text = format_chart(code, hist)
            results.append(InlineQueryResultArticle(
                id="chart",
                title=f"📊 {code}: график за {len(hist)} дн.",
                description="Нажмите, чтобы отправить",
                input_message_content=InputTextMessageContent(message_text=text),
            ))

    else:
        hint = (
            "💱 Подсказка:\n"
            "• 100 USD RUB — карточка + текст\n"
            "• USD — курс к рублю\n"
            "• USD 7 — график за 7 дней"
        )
        results.append(InlineQueryResultArticle(
            id="hint", title="💱 Введите: 100 USD RUB",
            description="или USD, или USD 7",
            input_message_content=InputTextMessageContent(message_text=hint),
        ))

    await update.inline_query.answer(results, cache_time=300)


# ---------- Команды ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Я бот-курсы валют.\n\n"
        "📌 Inline (в любом чате):\n"
        "`@ваш_бот 100 USD RUB` — карточка конвертации\n"
        "`@ваш_бот USD` — курс к рублю\n"
        "`@ваш_бот USD 7` — график за 7 дней\n\n"
        "🖼 Карточка в личке:\n"
        "`/convert 100 USD RUB`\n\n"
        "🔔 Подписки (в личке):\n"
        "`/subscribe USD > 95` — уведомить, когда выше 95\n"
        "`/subscribe USD < 90` — когда ниже 90\n"
        "/mysubs — список\n"
        "/unsubscribe USD — удалить\n\n"
        "☀️ Утренняя сводка:\n"
        "/digest_on — включить (в 9:00 МСК)\n"
        "/digest_off — выключить\n\n"
        "🧾 Отправьте фото чека — распознаю сумму.",
        parse_mode="Markdown",
    )


async def chart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = context.args[0].upper() if context.args else "USD"
    days = 7
    if len(context.args) > 1:
        try:
            days = min(int(context.args[1]), 30)
        except ValueError:
            pass
    hist = get_history(code, days)
    if len(hist) < 2:
        await update.message.reply_text("Не удалось получить историю 😔")
        return
    await update.message.reply_text(format_chart(code, hist))


async def convert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Использование:\n"
            "`/convert 100 USD RUB`\n"
            "`/convert 100 USD` — в RUB",
            parse_mode="Markdown",
        )
        return

    parsed = parse_manual(" ".join(context.args))
    if not parsed:
        await update.message.reply_text(
            "Не понял формат 🤔 Пример: `/convert 100 USD RUB`",
            parse_mode="Markdown",
        )
        return

    amount, cur, to_cur = parsed
    rates = get_rates()
    if not rates or cur not in rates or to_cur not in rates:
        await update.message.reply_text("Не знаю такую валюту 😔")
        return

    result = amount * rates[cur] / rates[to_cur]

    try:
        buf = generate_card(cur, amount, to_cur, result)
        caption = (
            f"{flag(cur)} {format_number(amount)} {cur} = "
            f"{flag(to_cur)} {format_number(result)} {to_cur}"
        )
        await update.message.reply_photo(photo=buf, caption=caption)
    except Exception as e:
        logging.exception(f"card generation failed: {e}")
        await update.message.reply_text(
            f"{flag(cur)} {format_number(amount)} {cur} = "
            f"{flag(to_cur)} {format_number(result)} {to_cur}"
        )


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 3 or args[1] not in (">", "<"):
        await update.message.reply_text(
            "Использование:\n`/subscribe USD > 95`\n`/subscribe USD < 90`",
            parse_mode="Markdown",
        )
        return
    code = args[0].upper()
    direction = "above" if args[1] == ">" else "below"
    try:
        value = float(args[2].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Не понял число 🤔")
        return
    subs = load_subs()
    subs["alerts"].setdefault(str(update.effective_chat.id), []).append({
        "code": code, "direction": direction,
        "value": value, "last_triggered": 0,
    })
    save_subs(subs)
    sign = "≥" if direction == "above" else "≤"
    await update.message.reply_text(
        f"✅ Подписка: {flag(code)} {code} {sign} {format_number(value)} RUB"
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /unsubscribe USD")
        return
    code = context.args[0].upper()
    chat_id = str(update.effective_chat.id)
    subs = load_subs()
    if chat_id in subs["alerts"]:
        subs["alerts"][chat_id] = [
            s for s in subs["alerts"][chat_id] if s["code"] != code
        ]
        if not subs["alerts"][chat_id]:
            del subs["alerts"][chat_id]
        save_subs(subs)
    await update.message.reply_text(f"👌 Отписался от {code}")


async def mysubs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = load_subs()
    chat_id = str(update.effective_chat.id)
    items = subs["alerts"].get(chat_id, [])
    lines = []
    if items:
        lines.append("📋 Подписки на порог:")
        for s in items:
            sign = "≥" if s["direction"] == "above" else "≤"
            lines.append(
                f"• {flag(s['code'])} {s['code']} "
                f"{sign} {format_number(s['value'])} RUB"
            )
    if chat_id in subs["digests"]:
        lines.append(f"\n☀️ Утренняя сводка включена в {DIGEST_HOUR:02d}:00 МСК")
    if not lines:
        lines.append("Активных подписок нет.\n/subscribe USD > 95 или /digest_on")
    await update.message.reply_text("\n".join(lines))


async def digest_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = load_subs()
    chat_id = str(update.effective_chat.id)
    if chat_id not in subs["digests"]:
        subs["digests"].append(chat_id)
        save_subs(subs)
    await update.message.reply_text(
        f"☀️ Ок! Каждое утро в {DIGEST_HOUR:02d}:{DIGEST_MINUTE:02d} МСК пришлю курсы."
    )


async def digest_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = load_subs()
    chat_id = str(update.effective_chat.id)
    if chat_id in subs["digests"]:
        subs["digests"].remove(chat_id)
        save_subs(subs)
    await update.message.reply_text("🔕 Утренняя сводка отключена.")


# ---------- OCR ----------
async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cleanup_pending()
    msg = update.message
    photo = msg.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())

    status = await msg.reply_text("🔍 Распознаю чек...")

    text = None
    try:
        text = ocr_space(image_bytes, apikey=OCRSPACE_KEY)
    except Exception as e:
        logging.warning(f"ocr.space failed: {e}")
        try:
            text = ocr_tesseract(image_bytes)
        except Exception as e2:
            logging.warning(f"tesseract failed: {e2}")

    if not text or len(text.strip()) < 5:
        await status.edit_text(
            "😔 Не смог прочитать текст с фото.\n"
            "Напишите сумму вручную: `120 USD`",
            parse_mode="Markdown",
        )
        PENDING[update.effective_user.id] = {"ts": time.time()}
        return

    parsed = parse_receipt(text)
    rates = get_rates()
    if not rates:
        await status.edit_text("Курсы недоступны, попробуйте позже.")
        return

    if parsed["amount"] is None or parsed["currency"] not in rates:
        await status.edit_text(
            f"🤔 Не уверен в сумме ({parsed['reason']}).\n"
            f"Напишите вручную: `120 USD`",
            parse_mode="Markdown",
        )
        PENDING[update.effective_user.id] = {"ts": time.time()}
        return

    amount, cur = parsed["amount"], parsed["currency"]
    result = build_receipt_result(amount, cur, rates)

    if parsed["confidence"] == "high":
        footer = "_Распознано автоматически. Если неверно — нажмите «Исправить»._"
    else:
        footer = f"⚠️ _{parsed['reason']}. Проверьте, пожалуйста._"

    await status.edit_text(
        f"{result}\n\n{footer}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✏️ Исправить", callback_data="fix")
        ]]),
    )
    PENDING[update.effective_user.id] = {
        "amount": amount, "currency": cur, "ts": time.time(),
    }


async def on_fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    PENDING[update.effective_user.id] = {"ts": time.time()}
    await query.edit_message_text(
        "✏️ Напишите сумму и валюту:\n"
        "`120 USD`\n"
        "`120 USD EUR`\n"
        "`120` — по умолчанию RUB",
        parse_mode="Markdown",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cleanup_pending()
    uid = update.effective_user.id
    if uid not in PENDING:
        return

    parsed = parse_manual(update.message.text or "")
    if not parsed:
        await update.message.reply_text(
            "Не понял 🤔 Пример: `120 USD`", parse_mode="Markdown"
        )
        return

    amount, cur, to_cur = parsed
    rates = get_rates()
    if not rates or cur not in rates or to_cur not in rates:
        await update.message.reply_text("Не знаю такую валюту 😔")
        return

    result = amount * rates[cur] / rates[to_cur]
    await update.message.reply_text(
        f"🧾 {flag(cur)} {format_number(amount)} {cur} "
        f"= {flag(to_cur)} {format_number(result)} {to_cur}"
    )
    PENDING.pop(uid, None)


# ---------- Фоновые задачи ----------
async def check_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    subs = load_subs()
    rates = get_rates()
    if not rates:
        return
    changed = False
    now = time.time()
    for chat_id, items in list(subs["alerts"].items()):
        for sub in items:
            code = sub["code"]
            if code not in rates:
                continue
            current = rates[code]
            hit = (
                (sub["direction"] == "above" and current >= sub["value"]) or
                (sub["direction"] == "below" and current <= sub["value"])
            )
            if not hit or now - sub.get("last_triggered", 0) < COOLDOWN:
                continue
            sub["last_triggered"] = now
            changed = True
            sign = "≥" if sub["direction"] == "above" else "≤"
            text = (
                f"🔔 {flag(code)} {code} сейчас {format_number(current)} RUB\n"
                f"Сработало условие: {sign} {format_number(sub['value'])}\n"
                f"Отписаться: /unsubscribe {code}"
            )
            try:
                await context.bot.send_message(chat_id=int(chat_id), text=text)
            except Exception as e:
                logging.error(f"send to {chat_id}: {e}")
    if changed:
        save_subs(subs)


async def send_daily_digest(context: ContextTypes.DEFAULT_TYPE):
    subs = load_subs()
    if not subs["digests"]:
        return
    rates = get_rates()
    if not rates:
        return
    lines = ["☀️ Доброе утро! Курсы валют:\n"]
    for code in DIGEST_CODES:
        if code in rates:
            lines.append(
                f"{flag(code)} 1 {code} = {format_number(rates[code])} RUB"
            )
    lines.append("\n💡 @ваш_бот 100 USD RUB — карточка конвертации")
    text = "\n".join(lines)
    for chat_id in subs["digests"]:
        try:
            await context.bot.send_message(chat_id=int(chat_id), text=text)
        except Exception as e:
            logging.error(f"digest to {chat_id}: {e}")


# ---------- Сборка приложения ----------
async def post_init(app: Application):
    app.job_queue.run_repeating(
        check_subscriptions, interval=CHECK_INTERVAL, first=10
    )
    app.job_queue.run_daily(
        send_daily_digest,
        time=dtime(hour=DIGEST_HOUR, minute=DIGEST_MINUTE, tzinfo=MSK),
    )


def build_ptb_app() -> Application:
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chart", chart_cmd))
    app.add_handler(CommandHandler("convert", convert_cmd))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("mysubs", mysubs))
    app.add_handler(CommandHandler("digest_on", digest_on))
    app.add_handler(CommandHandler("digest_off", digest_off))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.PHOTO, handle_receipt))
    app.add_handler(CallbackQueryHandler(on_fix, pattern="^fix$"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    return app


def build_star_app(ptb_app: Application) -> Starlette:
    WEBHOOK_PATH = "/webhook"

    async def telegram_webhook(request):
        logging.info("→ Webhook request received")
        try:
            data = await request.json()
        except Exception as e:
            logging.exception(f"webhook: не смог прочитать JSON: {e}")
            return Response("bad json", status_code=400)
        update = Update.de_json(data, ptb_app.bot)
        await ptb_app.process_update(update)
        return Response("ok")

    async def card_endpoint(request):
        amount_s = request.path_params["amount"]
        frm = request.path_params["from_code"].upper()
        to = request.path_params["to_code"].upper()
        try:
            amount = float(amount_s.replace(",", "."))
        except ValueError:
            return Response("bad amount", status_code=400)
        rates = get_rates()
        if not rates or frm not in rates or to not in rates:
            return Response("bad currency", status_code=400)
        result = amount * rates[frm] / rates[to]
        try:
            buf = generate_card(frm, amount, to, result)
        except Exception as e:
            logging.exception(f"card endpoint: {e}")
            return Response("card error", status_code=500)
        return Response(
            buf.read(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=600"},
        )

    async def health(request):
        return Response("ok")

    @asynccontextmanager
    async def lifespan(starlette_app):
        await ptb_app.initialize()
        await ptb_app.start()

        url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
        # Сбрасываем возможный старый webhook у Telegram (с другого контейнера),
        # затем ставим свой. drop_pending_updates=False — чтобы доставить
        # сообщения, накопившиеся пока бот был офлайн.
        try:
            await ptb_app.bot.delete_webhook(drop_pending_updates=False)
        except Exception as e:
            logging.warning(f"delete_webhook before set: {e}")

        await ptb_app.bot.set_webhook(
            url=url,
            drop_pending_updates=False,
            allowed_updates=Update.ALL_TYPES,
        )
        logging.info(f"Set webhook to {url}")

        try:
            yield
        finally:
            # НЕ вызываем delete_webhook — иначе при следующем деплое
            # старый контейнер снесёт URL, установленный новым.
            try:
                await ptb_app.stop()
            except Exception:
                pass
            try:
                await ptb_app.shutdown()
            except Exception:
                pass

    return Starlette(
        routes=[
            Route(WEBHOOK_PATH, telegram_webhook, methods=["POST"]),
            Route("/card/{amount}/{from_code}/{to_code}.png", card_endpoint),
            Route("/", health),
        ],
        lifespan=lifespan,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    ptb_app = build_ptb_app()

    if WEBHOOK_URL:
        print(f"Запуск webhook на {WEBHOOK_URL}, порт {PORT}")
        star_app = build_star_app(ptb_app)
        uvicorn.run(star_app, host="0.0.0.0", port=PORT, log_level="info")
    else:
        print("WEBHOOK_URL не задан — запуск polling (только для локальной разработки)")
        ptb_app.run_polling()


if __name__ == "__main__":
    main()