from __future__ import annotations

import logging

from telebot import TeleBot, types
from telebot.types import CallbackQuery, Message, PreCheckoutQuery

from billing.crypto import make_checkout_token
from billing.payments import activate_paid_plan
from billing.plans import get_plan
from core.config import settings

logger = logging.getLogger(__name__)

# These Star prices target roughly $10 / $20 of developer reward value.
# Telegram's actual buyer price varies by country and purchase platform.
STAR_PRICES = {
    "pro_monthly": 750,
    "pro_quarterly": 1500,
}


def show_plans(bot: TeleBot, chat_id: int) -> None:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("Pro 1 month — 750 Stars", callback_data="buy:pro_monthly:stars"),
        types.InlineKeyboardButton("Pro 3 months — 1500 Stars", callback_data="buy:pro_quarterly:stars"),
    )
    markup.row(types.InlineKeyboardButton("Crypto checkout (external)", callback_data="buy:crypto"))
    bot.send_message(chat_id, "Choose a plan and payment method:", reply_markup=markup)


def _send_stars_invoice(bot: TeleBot, chat_id: int, plan_key: str) -> None:
    plan = get_plan(plan_key)
    stars = STAR_PRICES[plan_key]
    bot.send_invoice(
        chat_id=chat_id,
        title=plan.title,
        description=f"XAI Code Agent: {plan.credits} coding Credits for {plan.duration_days} days.",
        invoice_payload=f"{chat_id}:{plan.key}",
        provider_token="",
        currency="XTR",
        prices=[types.LabeledPrice(label=f"{plan.title} — {plan.credits} Credits", amount=stars)],
        start_parameter=f"xai-{plan.key}",
    )


def _send_crypto_checkout(bot: TeleBot, chat_id: int, plan_key: str) -> None:
    if not settings.public_base_url:
        raise RuntimeError("PUBLIC_BASE_URL is not configured")
    token = make_checkout_token(chat_id, plan_key)
    url = f"{settings.public_base_url}/api/payments/crypto/checkout?token={token}"
    plan = get_plan(plan_key)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"Open crypto checkout — ${plan.price_usd}", url=url))
    bot.send_message(
        chat_id,
        f"External crypto checkout: {plan.title}\nAmount: ${plan.price_usd}\nAccepted assets: USDT or TON\n\nThe crypto payment page opens outside the Telegram Mini App.",
        reply_markup=markup,
    )


def register_payment_handlers(bot: TeleBot) -> None:
    @bot.message_handler(commands=["buy"])
    def buy_command(message: Message) -> None:
        if message.from_user:
            show_plans(bot, message.chat.id)

    @bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("buy:")))
    def buy_callback(call: CallbackQuery) -> None:
        if not call.from_user or not call.data:
            return
        parts = call.data.split(":")
        try:
            if len(parts) == 2 and parts[1] == "crypto":
                bot.answer_callback_query(call.id)
                if call.message:
                    markup = types.InlineKeyboardMarkup()
                    for plan_key, label in (("pro_monthly", "Pro 1 month — $10"), ("pro_quarterly", "Pro 3 months — $20")):
                        markup.add(types.InlineKeyboardButton(label, callback_data=f"buy:{plan_key}:crypto"))
                    bot.send_message(call.message.chat.id, "Choose the plan for external crypto checkout:", reply_markup=markup)
                return
            if len(parts) != 3:
                raise ValueError
            _, plan_key, method = parts
            get_plan(plan_key)
            bot.answer_callback_query(call.id)
            chat_id = call.message.chat.id if call.message else call.from_user.id
            if method == "stars":
                _send_stars_invoice(bot, chat_id, plan_key)
            elif method == "crypto":
                _send_crypto_checkout(bot, chat_id, plan_key)
            else:
                raise ValueError
        except Exception:
            logger.exception("Payment checkout failed")
            try:
                bot.answer_callback_query(call.id, "Payment setup failed", show_alert=True)
            except Exception:
                pass

    @bot.pre_checkout_query_handler(func=lambda query: True)
    def pre_checkout(query: PreCheckoutQuery) -> None:
        try:
            payload = query.invoice_payload or ""
            telegram_id_text, plan_key = payload.split(":", 1)
            if int(telegram_id_text) != query.from_user.id or plan_key not in STAR_PRICES:
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
            if int(telegram_id_text) != message.from_user.id:
                raise ValueError("Telegram user mismatch")
            plan = get_plan(plan_key)
            activated = activate_paid_plan(
                message.from_user.id,
                plan_key,
                "telegram_stars",
                payment.telegram_payment_charge_id,
                plan.price_usd,
                asset="XTR",
                raw_payload={
                    "invoice_payload": payment.invoice_payload,
                    "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                    "total_amount": payment.total_amount,
                },
            )
            if activated:
                bot.send_message(message.chat.id, f"Payment successful. {plan.title} is now active and {plan.credits} Credits were added.")
            else:
                bot.send_message(message.chat.id, "This payment was already processed.")
        except Exception:
            logger.exception("Telegram Stars activation failed")
            bot.send_message(message.chat.id, "Payment was received, but activation failed. Please contact support.")

    @bot.message_handler(commands=["paysupport"])
    def payment_support(message: Message) -> None:
        bot.send_message(message.chat.id, "For payment problems, contact the XAI Code Agent support account configured by the service owner.")

    @bot.message_handler(commands=["terms"])
    def terms_command(message: Message) -> None:
        bot.send_message(message.chat.id, "By purchasing a plan, you agree to the service terms and understand that Credits are usage units for XAI Code Agent features.")
