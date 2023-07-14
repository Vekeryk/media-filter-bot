#!/usr/bin/python3.11
from datetime import datetime, timedelta
import io
import logging

from model import load_model, classify
from telegram import ChatPermissions, Message, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from constants import ADMIN_CHAT, ADMIN_LIST, AUTO_CAPTION, TOKEN, USERS, USER_BLACK_LIST, FORWARD_CHAT_BLACK_LIST

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

model = load_model()
IS_TOTAL_CENSORSHIP = False
ALL_PERMISSIONS = ChatPermissions(can_send_messages=True,
                                  can_send_media_messages=True,
                                  can_send_other_messages=True,
                                  can_add_web_page_previews=True,
                                  can_send_polls=True)
BAN_PERMISSIONS = ChatPermissions(can_send_messages=True,
                                  can_send_media_messages=False)

async def unban_user_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_message):
        return

    chat_id = update.effective_message.chat_id
    username = get_username_from_command(update.effective_message)
    user_id = USERS.get(username)
    logging.info(f"User: {username}, {user_id}")
    await update.effective_message.delete()
    await context.bot.restrict_chat_member(chat_id, user_id, ALL_PERMISSIONS)
    await context.bot.send_message(chat_id, f"{username} media was unbunned.")


async def ban_user_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_message):
        return

    chat_id = update.effective_message.chat_id
    username = get_username_from_command(update.effective_message)
    user_id = USERS.get(username)
    logging.info(f"User: {username}, {user_id}")
    await update.effective_message.delete()
    await context.bot.restrict_chat_member(chat_id, user_id, BAN_PERMISSIONS, datetime.now() + timedelta(hours=1))
    await context.bot.send_message(chat_id, f"{username} media was bunned.")


async def sloiler_nsfw_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user_id = message.from_user.id
    username = message.from_user.username
    USERS[username] = user_id

    if not message.photo or message.has_media_spoiler:
        return

    custom_caption = f'From {username}: {message.caption}' if message.caption else f'From {username}'
    forward_from_chat = message.forward_from_chat

    if forward_from_chat and forward_from_chat.id in FORWARD_CHAT_BLACK_LIST or IS_TOTAL_CENSORSHIP:
        await resend_photo_with_spoiler(message, custom_caption, context)
    else:
        await spoiler_with_model_prediction(message, custom_caption, context)

    logging.info(f"Chat {message.chat_id} - All users {USERS}, BLACK_LIST: {FORWARD_CHAT_BLACK_LIST}")


async def spoiler_with_model_prediction(message: Message, custom_caption: str, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await context.bot.get_file(message.photo[-2].file_id)
    logging.info(f"File size: {message.photo[-2].file_size}")
    photo_bytearray = await photo_file.download_as_bytearray()
    photo_bytes_io = io.BytesIO(photo_bytearray)
    try:
        predictions = classify(model, photo_bytes_io)
        logging.info(predictions)
        is_nsfw, prediction_caption = analyse_predictions(predictions)
        if is_nsfw:
            await resend_photo_with_spoiler(message, f"{custom_caption} {prediction_caption}", context)
    except Exception as e:
        logging.error(f"Model error... {str(e)}", exc_info=True)
        await context.bot.send_message(ADMIN_CHAT, "Model error...")


def analyse_predictions(predictions: dict) -> tuple:
    predictions.pop("Neutral")
    if predictions["Drawing"] > 49 and predictions["Hentai"] > 29:
        return True, AUTO_CAPTION.format(f"Drawing={predictions['Drawing']}, Hentai={predictions['Hentai']}")
    predictions.pop("Drawing")
    for name, probability in predictions.items():
        if probability > 49:
            return True, AUTO_CAPTION.format(f"{name}={probability}")
    return False, "Photo is neutral"


async def spoiler_reply_to_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    reply_to_message = update.message.reply_to_message

    if reply_to_message and reply_to_message.photo and reply_to_message.from_user.id != context.bot.id:
        reporter_username = message.from_user.username
        from_caption = f'From {reply_to_message.from_user.username} (spoilered by {reporter_username})'
        custom_caption = f'{from_caption}: {reply_to_message.caption}' if reply_to_message.caption else from_caption
        await resend_photo_with_spoiler(reply_to_message, custom_caption, context)

    await message.delete()


async def resend_photo_with_spoiler(message: Message, custom_caption: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    await message.delete()
    await context.bot.send_photo(message.chat_id, message.photo[-1].file_id, caption=custom_caption, has_spoiler=True)


async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_message.chat_id
    message = update.effective_message
    if is_reply_command_valid(update.effective_message):
        await message.delete()
        await context.bot.delete_message(chat_id, message.reply_to_message.message_id)


async def add_forward_chat_to_black_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_to_message = update.effective_message.reply_to_message
    if is_reply_command_valid(update.effective_message) and reply_to_message.forward_from_chat:
        FORWARD_CHAT_BLACK_LIST.add(reply_to_message.forward_from_chat.id)
        logging.info("Added chat to black list: {FORWARD_CHAT_BLACK_LIST}")
        await spoiler_reply_to_photo(update, context)


async def toggle_total_censorship(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global IS_TOTAL_CENSORSHIP
    chat_id = update.effective_message.chat_id
    if is_admin(update.effective_message):
        IS_TOTAL_CENSORSHIP = not IS_TOTAL_CENSORSHIP
        await context.bot.send_message(chat_id, f"Total censorship set to {IS_TOTAL_CENSORSHIP}")
    else:
        await context.bot.delete_message(chat_id, update.effective_message.message_id)


def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.info(f"Update {update} caused error {context.error}")


def is_reply_command_valid(message: Message) -> bool:
    user_id = message.from_user.id
    reply_to_message = message.reply_to_message
    return user_id in ADMIN_LIST and reply_to_message


def is_admin(message: Message) -> bool:
    user_id = message.from_user.id
    return user_id in ADMIN_LIST


def get_username_from_command(message: Message) -> str:
    return message.text.split(" ")[1].removeprefix("@")


def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(MessageHandler(filters.PHOTO, sloiler_nsfw_photo))
    application.add_handler(CommandHandler("blur", spoiler_reply_to_photo))
    application.add_handler(CommandHandler("add", add_forward_chat_to_black_list))
    application.add_handler(CommandHandler("delete", delete_message))
    application.add_handler(CommandHandler("ban", ban_user_media))
    application.add_handler(CommandHandler("unban", unban_user_media))
    application.add_handler(CommandHandler("censor", toggle_total_censorship))

    application.add_error_handler(error)

    application.run_polling()


if __name__ == "__main__":
    main()
