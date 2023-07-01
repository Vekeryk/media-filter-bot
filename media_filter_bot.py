#!/usr/bin/python3.11
from datetime import datetime, timedelta
import logging
import requests

from telegram import ChatPermissions, Bot
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from constants import ADMIN_LIST, API_URL, BOT_ID, TOKEN, USERS, USER_BLACK_LIST, FORWARD_CHAT_BLACK_LIST

# Enable logging
# logging.basicConfig(
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
# )

bot = Bot(token=TOKEN)
IS_TOTAL_CENSORSHIP = False
ALL_PERMISSIONS = ChatPermissions(can_send_messages=True,
                                  can_send_media_messages=True,
                                  can_send_other_messages=True,
                                  can_add_web_page_previews=True,
                                  can_send_polls=True)


async def unban_user_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_message):
        return

    chat_id = update.effective_message.chat_id
    username = get_username_from_command(update.effective_message)
    await bot.delete_message(chat_id, update.effective_message.message_id)
    await bot.restrict_chat_member(chat_id, USERS.get(username), ALL_PERMISSIONS)
    await bot.send_message(chat_id, f"{username} media was unbunned.")


async def ban_user_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_message):
        return

    chat_id = update.effective_message.chat_id
    username = get_username_from_command(update.effective_message)
    user_id = USERS.get(username)
    await bot.delete_message(chat_id, update.effective_message.message_id)
    await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=True, can_send_media_messages=False), datetime.now() + timedelta(hours=6))
    await bot.send_message(chat_id, f"{username} media was bunned.")


async def blur_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if update.message.reply_to_message:
        message = update.message.reply_to_message

    user_id = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat_id
    USERS[username] = user_id

    if not message.photo and user_id == BOT_ID:
        return

    message_id = message.message_id
    caption = message.caption
    custom_caption = f'Від {username}: {caption}' if caption else f'Від {username}'
    forward_from_chat = message.forward_from_chat

    if update.message.reply_to_message and user_id != BOT_ID:
        await bot.delete_message(chat_id, update.effective_message.message_id)
        await resend_message_with_spoiler(chat_id, message_id, message.photo, custom_caption)
    elif forward_from_chat and forward_from_chat.id in FORWARD_CHAT_BLACK_LIST or IS_TOTAL_CENSORSHIP:
        await resend_message_with_spoiler(chat_id, message_id, message.photo, custom_caption)
    else:
        photo_file = await bot.get_file(message.photo[-2].file_id)
        photo_bytearray = await photo_file.download_as_bytearray()
        try:
            response = requests.post(API_URL, files={'image': ('test.png', photo_bytearray)})
            predictions = list(filter(lambda prediction: prediction["className"] != "Neutral" and prediction["className"] != "Drawing", response.json()))
            print(predictions, response.json())
            for prediction in predictions:
                probability = int(prediction["probability"] * 100)
                if probability > 49:
                    await resend_message_with_spoiler(chat_id, message_id, message.photo,
                                                    f"{custom_caption} (automatically censored with prediction {prediction['className']}={probability})")
        except Exception as e:
            print(f"API error... {str(e)}\n")
            await bot.send_message(chat_id, f"API error...")

    print(f"All users in {chat_id}\n", USERS, "\nBLACK_LIST\n", FORWARD_CHAT_BLACK_LIST)


async def resend_message_with_spoiler(chat_id, message_id, photo, custom_caption) -> None:
    await bot.delete_message(chat_id, message_id)
    await bot.send_photo(chat_id, photo[-1].file_id, caption=custom_caption, has_spoiler=True)


async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_message.chat_id
    message = update.effective_message
    if is_reply_command_valid(update.effective_message):
        await bot.delete_message(chat_id, message.message_id)
        await bot.delete_message(chat_id, message.reply_to_message.message_id)


async def add_forward_chat_to_black_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_to_message = update.effective_message.reply_to_message
    if is_reply_command_valid(update.effective_message) and reply_to_message.forward_from_chat:
        FORWARD_CHAT_BLACK_LIST.add(reply_to_message.forward_from_chat.id)
        print("Added chat to black list:\n", FORWARD_CHAT_BLACK_LIST)
        await blur_photo(update, context)


async def toggle_censorship(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global IS_TOTAL_CENSORSHIP
    chat_id = update.effective_message.chat_id
    if is_admin(update.effective_message):
        IS_TOTAL_CENSORSHIP = not IS_TOTAL_CENSORSHIP
        await bot.send_message(chat_id, f"Total censorship set to {IS_TOTAL_CENSORSHIP}")
    else:
        await bot.delete_message(chat_id, update.effective_message.message_id)


def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Update {update} caused error {context.error}")


def is_reply_command_valid(message):
    user_id = message.from_user.id
    reply_to_message = message.reply_to_message
    return user_id in ADMIN_LIST and reply_to_message


def is_admin(message):
    user_id = message.from_user.id
    return user_id in ADMIN_LIST


def get_username_from_command(message):
    return message.text.split(" ")[1].removeprefix("@")


def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(MessageHandler(filters.PHOTO, blur_photo))
    application.add_handler(CommandHandler("blur", blur_photo))
    application.add_handler(CommandHandler("add", add_forward_chat_to_black_list))
    application.add_handler(CommandHandler("delete", delete_message))
    application.add_handler(CommandHandler("ban", ban_user_media))
    application.add_handler(CommandHandler("unban", unban_user_media))
    application.add_handler(CommandHandler("censor", toggle_censorship))

    application.add_error_handler(error)

    application.run_polling(poll_interval=5)


if __name__ == "__main__":
    main()
