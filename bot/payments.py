from __future__ import annotations

import logging

from telebot import TeleBot, types
from telebot.types import Message, PreCheckoutQuery

from billing.payments import activate_paid_plan
from billing.plans import get_plan
from billing.stars import STAR_PRICES
from core.config import settings

logger = logging.getLogger(__name__)


def show_plans(bot: TeleBot, chat_id: int) -> None:
    url = settings.miniapp_url or f"{settings.public_base_url}/dashboard/"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Open XAI Code Agent", web_app=types.WebAppInfo(url=url)))
    bot.send_message(
        chat_id,
        "Open the Mini App to view Starter, Pro, Team and Top-Up plans. Telegram Stars and direct USDT on TON are available there.",
        reply_markup=markup,
    )


def register_payment_handlers(bot: TeleBot) -> None:
    @bot.message_handler(commands=["buy"])
    def buy_command(message: Message) -> None:
        if message.from_user:
            show_plans(bot, message.chat.id)

    @bot.pre_checkout_query_handler(func=lambda query: True)
    def pre_checkout(query: PreCheckoutQuery) -> None:
        try:
            payload = query.invoice_payload or ""
            telegram_id_text, plan_key = payload.split(":", 1)
            plan = get_plan(plan_key)
            expected_stars = STAR_PRICES[plan_key]
            if (
                int(telegram_id_text) != query.from_user.id
                or query.currency != "XTR"
                or query.total_amount != expected_stars
            ):
                bot.answer_pre_checkout_query(query.id, ok=False, error_message="Invalid payment order")
                return
            bot.answer_pre_checkout_query(query.id, ok=True)
        except Exception:
            logger.exception("Pre-checkout validation failed")
            bot.answer_pre_checkout_query(query.id, ok=False, error_message="Payment validation failed")

    @bot.message_handler(content_types=["successful_payment"])
    def successful_payment(message: Message) -> None:
        payment = message.successful_payment
        if not payment or not message.from_user:
            return
        try:
            telegram_id_text, plan_key = payment.invoice_payload.split(":", 1)
            plan = get_plan(plan_key)
            expected_stars = STAR_PRICES[plan_key]
            if (
                int(telegram_id_text) != message.from_user.id
                or payment.currency != "XTR"
                or payment.total_amount != expected_stars
            ):
                raise ValueError("Invalid Stars payment")
            activated = activate_paid_plan(
                message.from_user.id,
                plan_key,
                "telegram_stars",
                payment.telegram_payment_charge_id,
                plan.price_usd_cents,
                asset="XTR",
                raw_payload={
                    "invoice_payload": payment.invoice_payload,
                    "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                    "total_amount": payment.total_amount,
                },
            )
            if activated:
                bot.send_message(
                    message.chat.id,
                    f"Payment successful. {plan.title} is active and {plan.credits} Credits were added.",
                )
            else:
                bot.send_message(message.chat.id, "This payment was already processed.")
        except Exception:
            logger.exception("Telegram Stars activation failed")
            bot.send_message(message.chat.id, "Payment was received, but activation failed. Please contact support.")

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
