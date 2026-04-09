
import asyncio
import logging
import re
import time

from telegram import BotCommand, BotCommandScopeChat, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    ADMIN_USERS, ALLOWED_USERS, MAX_INPUT_CHARS, MIN_INTERVAL_SEC,
    STREAM_REPLIES, TELEGRAM_TOKEN, TRIGGER_WORD,
)
from rag import CharacterChat

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

chat_engine: CharacterChat = None 
_last_msg_ts: dict[int, float] = {}

ERROR_MESSAGES = {
    "rate_limit": "…дай подумать минутку.",
    "auth":       "…",
    "timeout":    "…что-то я задумался. Повтори?",
    "context":    "Слишком много всего. Давай начнём заново.",
    "default":    "…не могу сейчас ответить.",
}


def classify_error(e: Exception) -> str:
    msg = str(e).lower()
    if any(x in msg for x in ("rate_limit", "rate limit", "429", "too many")):
        return "rate_limit"
    if any(x in msg for x in ("auth", "401", "403", "api key", "unauthorized", "forbidden")):
        return "auth"
    if any(x in msg for x in ("timeout", "timed out", "deadline")):
        return "timeout"
    if any(x in msg for x in ("context length", "too many tokens", "max token", "context_length")):
        return "context"
    return "default"


def is_allowed(user_id: int) -> bool:
    return not ALLOWED_USERS or user_id in ALLOWED_USERS


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USERS


def rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    last = _last_msg_ts.get(user_id, 0.0)
    if now - last < MIN_INTERVAL_SEC:
        return True
    _last_msg_ts[user_id] = now
    return False


# ── Группы ───────

def _strip_mentions(text: str, bot_username: str | None) -> str:
    """Убирает @username бота и триггерное слово, возвращает очищенный текст."""
    clean = text
    if bot_username:
        clean = re.sub(rf"@{re.escape(bot_username)}\b", "", clean, flags=re.IGNORECASE)
    if TRIGGER_WORD:
        clean = re.sub(re.escape(TRIGGER_WORD), "", clean, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", clean).strip()


def _is_targeted(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """В приватах — всегда да. В группах — только при явной адресации."""
    chat = update.effective_chat
    if chat.type == "private":
        return True

    rtm = update.message.reply_to_message
    if rtm and rtm.from_user and rtm.from_user.id == context.bot.id:
        return True

    low = text.lower()
    bot_username = (context.bot.username or "").lower()
    if bot_username and f"@{bot_username}" in low:
        return True
    if TRIGGER_WORD and TRIGGER_WORD.lower() in low:
        return True
    return False


# ── Admin-команды ─────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """На /start в привате — просто короткая приветственная реплика в образе."""
    if update.effective_chat.type != "private":
        return
    if not is_allowed(update.effective_user.id):
        return
    user_id = str(update.effective_user.id)
    try:
        text = await chat_engine.reply(user_id, "Привет")
        await _send_long(update, text)
    except Exception as e:
        err = classify_error(e)
        await update.message.reply_text(ERROR_MESSAGES[err])


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chat_engine.clear_history(str(update.effective_user.id))
    await update.message.reply_text("История очищена.")


async def cmd_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    user_id = str(update.effective_user.id)
    available = chat_engine.available_characters()
    if not context.args:
        current = chat_engine.get_user_character(user_id)
        lines = [f"Текущий: *{current}*", "", "Доступные:"]
        lines += [f"• `{cid}`" for cid in available]
        lines += ["", "Смена: `/character <id>`"]
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return
    target = context.args[0].strip()
    try:
        chat_engine.set_user_character(user_id, target)
    except ValueError as e:
        await update.message.reply_text(f"{e}")
        return
    await update.message.reply_text(
        f"Переключено на *{target}*. История сброшена.", parse_mode="Markdown"
    )


async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    user_id = str(update.effective_user.id)
    query = " ".join(context.args) if context.args else "тест"
    result = chat_engine.debug_context(user_id, query)
    if len(result) > 4000:
        result = result[:4000] + "\n\n... (обрезано)"
    await update.message.reply_text(f"Контекст для «{query}»:\n\n{result}")


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        f"Твой user_id: `{update.effective_user.id}`", parse_mode="Markdown"
    )


# ── Основной обработчик ──────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_allowed(user.id):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    if not _is_targeted(update, context, text):
        return

    clean = _strip_mentions(text, context.bot.username)
    if not clean:
        return

    if len(clean) > MAX_INPUT_CHARS:
        clean = clean[:MAX_INPUT_CHARS]

    if rate_limited(user.id):
        return 

    user_id = str(user.id)
    username = user.username or user.first_name or user_id
    logger.info(f"[{update.effective_chat.type}/{username}] → {clean[:200]}")

    await update.message.chat.send_action(ChatAction.TYPING)

    cid = chat_engine.get_user_character(user_id)
    photo = chat_engine.character(cid).match_photo(clean)

    try:
        if STREAM_REPLIES:
            await _reply_stream(update, user_id, clean)
        else:
            response = await chat_engine.reply(user_id, clean)
            await _send_long(update, response)
    except Exception as e:
        err = classify_error(e)
        logger.error(f"[{username}] ОШИБКА ({err}): {e}")
        await update.message.reply_text(ERROR_MESSAGES[err])
        return

    if photo:
        try:
            with open(photo.file, "rb") as f:
                await update.message.reply_photo(photo=f, caption=photo.caption or None)
            logger.info(f"[{username}] photo → {photo.file}")
        except Exception as e:
            logger.error(f"Не смог отправить фото {photo.file}: {e}")


async def _send_long(update: Update, text: str):
    while text:
        chunk, text = text[:4096], text[4096:]
        await update.message.reply_text(chunk)


async def _reply_stream(update: Update, user_id: str, user_text: str):
    """Стриминг с edit_text: один раз в ~1.2 с, сплит по 4000 символов."""
    buffer = ""
    sent_msg = await update.message.reply_text("…")
    last_edit = time.monotonic()
    EDIT_INTERVAL = 1.2
    TG_LIMIT = 4000

    async for delta in chat_engine.reply_stream(user_id, user_text):
        buffer += delta
        now = time.monotonic()
        if len(buffer) >= TG_LIMIT:
            try:
                await sent_msg.edit_text(buffer[:TG_LIMIT])
            except Exception:
                pass
            buffer = buffer[TG_LIMIT:]
            sent_msg = await update.message.reply_text(buffer or "…")
            last_edit = now
            continue
        if now - last_edit >= EDIT_INTERVAL and buffer:
            try:
                await sent_msg.edit_text(buffer)
                last_edit = now
            except Exception:
                pass

    if buffer:
        try:
            await sent_msg.edit_text(buffer)
        except Exception:
            await update.message.reply_text(buffer)


# ── Запуск ───────────────────────────────────────────────

async def _post_init(app: Application):
    await app.bot.set_my_commands([]) 
    for admin_id in ADMIN_USERS:
        try:
            await app.bot.set_my_commands(
                [
                    BotCommand("clear", "Очистить историю"),
                    BotCommand("character", "Выбрать персонажа"),
                    BotCommand("debug", "RAG-контекст"),
                    BotCommand("whoami", "Мой user_id"),
                ],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as e:
            logger.warning(f"set_my_commands для {admin_id} не сработал: {e}")


def main():
    global chat_engine

    if not TELEGRAM_TOKEN:
        print("Ошибка: укажи TELEGRAM_TOKEN в .env")
        return

    print("Загружаю RAG движок...")
    chat_engine = CharacterChat()
    print(
        f"База: {chat_engine.total_chunks()} чанков, "
        f"персонажи: {chat_engine.available_characters()}"
    )

    print("Запускаю бота...")
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("character", cmd_character))
    app.add_handler(CommandHandler("debug", cmd_debug))
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
