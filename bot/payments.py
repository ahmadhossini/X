from __future__ import annotations

import logging

from telebot import TeleBot, types
from telebot.types import Message, PreCheckoutQuery

from billing.payments import activate_paid_plan
from billing.plans import get_plan
from billing.stars import STAR_PRICES
from bot.locales import t
from core.config import settings
from database.models import User
from database.session import SessionLocal
from sqlalchemy import select

logger = logging.getLogger(__name__)


PAYMENT_TEXTS = {
    "en": {
        "open": "Open XAI Code Agent",
        "plans": "Open the Mini App to view Starter, Pro, Team and Top-Up plans. Telegram Stars and direct USDT on TON are available there.",
        "invalid": "Invalid payment order",
        "validation_failed": "Payment validation failed",
        "success": "Payment successful. {plan} is active and {credits} Credits were added.",
        "already": "This payment was already processed.",
        "activation_failed": "Payment was received, but activation failed. Please contact support.",
        "support": "For payment problems, contact the XAI Code Agent support account configured by the service owner.",
        "terms": "By purchasing a plan, you agree to the service terms and understand that Credits are usage units for XAI Code Agent features.",
    },
    "hi": {
        "open": "XAI Code Agent खोलें",
        "plans": "Starter, Pro, Team और Top-Up प्लान देखने के लिए Mini App खोलें। वहाँ Telegram Stars और TON पर सीधे USDT से भुगतान उपलब्ध है।",
        "invalid": "भुगतान ऑर्डर मान्य नहीं है।",
        "validation_failed": "भुगतान सत्यापन विफल रहा।",
        "success": "भुगतान सफल रहा। {plan} सक्रिय है और {credits} Credits जोड़ दिए गए हैं।",
        "already": "यह भुगतान पहले ही संसाधित किया जा चुका है।",
        "activation_failed": "भुगतान प्राप्त हुआ, लेकिन सक्रिय नहीं किया जा सका। कृपया सहायता से संपर्क करें।",
        "support": "भुगतान की समस्या के लिए सेवा मालिक द्वारा निर्धारित XAI Code Agent सहायता खाते से संपर्क करें।",
        "terms": "प्लान खरीदकर आप सेवा की शर्तों से सहमत होते हैं और समझते हैं कि Credits XAI Code Agent सुविधाओं के उपयोग की इकाइयाँ हैं।",
    },
    "fa": {
        "open": "باز کردن XAI Code Agent",
        "plans": "برای دیدن پلن‌های Starter، Pro، Team و Top-Up، Mini App را باز کنید. پرداخت با Telegram Stars و USDT روی TON در آنجا در دسترس است.",
        "invalid": "سفارش پرداخت نامعتبر است.",
        "validation_failed": "اعتبارسنجی پرداخت ناموفق بود.",
        "success": "پرداخت موفق بود. پلن {plan} فعال شد و {credits} اعتبار اضافه شد.",
        "already": "این پرداخت قبلاً پردازش شده است.",
        "activation_failed": "پرداخت دریافت شد، اما فعال‌سازی انجام نشد. لطفاً با پشتیبانی تماس بگیرید.",
        "support": "برای مشکلات پرداخت، با حساب پشتیبانی XAI Code Agent که توسط مالک سرویس تنظیم شده است تماس بگیرید.",
        "terms": "با خرید پلن، با شرایط سرویس موافقت می‌کنید و می‌پذیرید که Credits واحدهای استفاده از قابلیت‌های XAI Code Agent هستند.",
    },
}


def _language(telegram_id: int) -> str:
    with SessionLocal() as db:
        language = db.scalar(select(User.language).where(User.telegram_id == telegram_id))
    return language if language in PAYMENT_TEXTS else "en"


def _text(telegram_id: int, key: str, **kwargs: object) -> str:
    language = _language(telegram_id)
    return PAYMENT_TEXTS[language][key].format(**kwargs)


def show_plans(bot: TeleBot, chat_id: int) -> None:
    url = settings.miniapp_url or f"{settings.public_base_url}/dashboard/"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(_text(chat_id, "open"), web_app=types.WebAppInfo(url=url)))
    bot.send_message(chat_id, _text(chat_id, "plans"), reply_markup=markup)


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
                bot.answer_pre_checkout_query(query.id, ok=False, error_message=_text(query.from_user.id, "invalid"))
                return
            bot.answer_pre_checkout_query(query.id, ok=True)
        except Exception:
            logger.exception("Pre-checkout validation failed")
            bot.answer_pre_checkout_query(query.id, ok=False, error_message=_text(query.from_user.id, "validation_failed"))

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
                bot.send_message(message.chat.id, _text(message.from_user.id, "success", plan=plan.title, credits=plan.credits))
            else:
                bot.send_message(message.chat.id, _text(message.from_user.id, "already"))
        except Exception:
            logger.exception("Telegram Stars activation failed")
            bot.send_message(message.chat.id, _text(message.from_user.id, "activation_failed"))

    @bot.message_handler(commands=["paysupport"])
    def payment_support(message: Message) -> None:
        if message.from_user:
            bot.send_message(message.chat.id, _text(message.from_user.id, "support"))

    @bot.message_handler(commands=["terms"])
    def terms_command(message: Message) -> None:
        if message.from_user:
            bot.send_message(message.chat.id, _text(message.from_user.id, "terms"))
