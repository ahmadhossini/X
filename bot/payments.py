from __future__ import annotations

from telebot import TeleBot, types
from telebot.types import Message

from core.config import settings


def show_plans(bot: TeleBot, chat_id: int) -> None:
    url = settings.miniapp_url or f"{settings.public_base_url}/dashboard/"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Open XAI Code Agent", web_app=types.WebAppInfo(url=url)))
    bot.send_message(
        chat_id,
        "Open the Mini App to view Starter, Pro, Team and Top-Up plans. Payments are made with USDT on TON.",
        reply_markup=markup,
    )


def register_payment_handlers(bot: TeleBot) -> None:
    @bot.message_handler(commands=["buy"])
    def buy_command(message: Message) -> None:
        if message.from_user:
            show_plans(bot, message.chat.id)

    @bot.message_handler(commands=["paysupport"])
    def payment_support(message: Message) -> None:
        bot.send_message(
            message.chat.id,
            "For payment problems, contact the XAI Code Agent support account configured by the service owner.",
        )

    @bot.message_handler(commands=["terms"])
    def terms_command(message: Message) -> None:
        bot.send_message(
            message.chat.id,
            "By purchasing a plan, you agree to the service terms and understand that Credits are usage units for XAI Code Agent features.",
        )
