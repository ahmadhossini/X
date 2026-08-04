import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import config

bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="Markdown")

# دیتابیس حافظه‌ای
user_group_messages = {}  # {user_id: count}
user_pv_messages = {}     # {user_id: count}
user_referrals = {}       # {user_id: total_invites}
group_settings = {}       # {chat_id: {"anti_link": True, "welcome": True}}

# ------------------- توابع کمکی -------------------

def check_subscription(user_id):
    """بررسی عضویت کاربر در کانال اسپانسر"""
    if not config.SPONSOR_CHANNEL or config.SPONSOR_CHANNEL == "@YourChannel":
        return True
    try:
        member = bot.get_chat_member(config.SPONSOR_CHANNEL, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception:
        pass
    return False

# ------------------- بخش گروه (مدیریت + ضد لینک + محدودیت) -------------------

@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'])
def group_handler(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # تنظیمات پیش‌فرض
    if chat_id not in group_settings:
        group_settings[chat_id] = {"anti_link": True, "welcome": True}

    settings = group_settings[chat_id]
    text = message.text or message.caption or ""

    # ۱. ضد لینک
    if settings["anti_link"] and ("http://" in text or "https://" in text or "t.me/" in text or "@" in text):
        try:
            bot.delete_message(chat_id, message.message_id)
            return
        except Exception:
            pass

    # ۲. شمارش پیام‌های گروه
    current_count = user_group_messages.get(user_id, 0) + 1
    user_group_messages[user_id] = current_count

    # اگر از ۱۰ پیام رایگان رد شد
    if current_count > config.FREE_GROUP_LIMIT:
        try:
            bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

        bot_info = bot.get_me()
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🤖 ورود به پی‌وی و چت با هوش مصنوعی", url=f"https://t.me/{bot_info.username}?start=from_group"))

        msg_text = (
            f"⚠️ کاربر [{message.from_user.first_name}](tg://user?id={user_id})، سقف ۱۰ پیام رایگان شما در گروه تمام شد!\n\n"
            f"🧠 برای استفاده از **هوش مصنوعی پیشرفته XAI MASTER** و گفتگو بدون محدودیت، وارد پی‌وی ربات بشید 👇"
        )
        bot.send_message(chat_id, msg_text, reply_markup=markup)

# خوشامدگویی اعضای جدید
@bot.message_handler(content_types=['new_chat_members'])
def welcome_member(message):
    chat_id = message.chat.id
    if group_settings.get(chat_id, {}).get("welcome", True):
        for new_user in message.new_chat_members:
            bot.send_message(
                chat_id,
                f"سلام {new_user.first_name} عزیز! 🌹\nبه گروه خوش آمدی. برای استفاده از هوش مصنوعی ربات حتماً سری به پی‌وی ما بزن!"
            )

# ------------------- بخش پی‌وی (هوش مصنوعی + اشتراک + رفرال) -------------------

@bot.message_handler(commands=['start'], func=lambda message: message.chat.type == 'private')
def start_pv(message):
    user_id = message.from_user.id
    bot_info = bot.get_me()
    text_args = message.text.split()

    # پردازش کد دعوت (Referral)
    if len(text_args) > 1 and text_args[1].startswith("ref_"):
        try:
            inviter_id = int(text_args[1].replace("ref_", ""))
            if inviter_id != user_id and user_id not in user_pv_messages:
                user_referrals[inviter_id] = user_referrals.get(inviter_id, 0) + 1
                user_pv_messages[inviter_id] = user_pv_messages.get(inviter_id, 0) - config.REFERRAL_BONUS
        except Exception:
            pass

    # بررسی جوین بودن در کانال اسپانسر
    if not check_subscription(user_id):
        channel_clean = config.SPONSOR_CHANNEL.replace('@', '')
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📢 عضویت در کانال اسپانسر", url=f"https://t.me/{channel_clean}"))
        markup.add(InlineKeyboardButton("✅ تایید عضویت", callback_data="check_sub"))

        bot.send_message(
            user_id,
            "⚠️ برای استفاده از ربات XAI MASTER، ابتدا باید در کانال اسپانسر ما عضو شوید:",
            reply_markup=markup
        )
        return

    # منوی اصلی پی‌وی
    main_menu = InlineKeyboardMarkup(row_width=2)
    main_menu.add(InlineKeyboardButton("🧠 گفتگو با هوش مصنوعی", callback_data="ai_chat"))
    main_menu.add(
        InlineKeyboardButton("💎 خرید اشتراک", callback_data="buy_vip"),
        InlineKeyboardButton("🔗 لینک دعوت (شارژ)", callback_data="get_ref")
    )

    bot.send_message(
        user_id,
        "🤖 **به ربات XAI MASTER خوش آمدید!**\n\n"
        "من بهت کمک می‌کنم گروه‌هات رو هوشمندانه مدیریت کنی و به پیشرفته‌ترین هوش مصنوعی دسترسی داشته باشی.",
        reply_markup=main_menu
    )

# چت متنی هوش مصنوعی در پی‌وی
@bot.message_handler(func=lambda message: message.chat.type == 'private')
def pv_ai_handler(message):
    user_id = message.from_user.id

    if not check_subscription(user_id):
        bot.send_message(user_id, "❌ لطفاً ابتدا در کانال اسپانسر عضو شوید.")
        return

    pv_count = user_pv_messages.get(user_id, 0)

    # اگر ظرفیت رایگان پی‌وی تمام شد
    if pv_count >= config.FREE_PV_LIMIT:
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 خرید اشتراک نامحدود", callback_data="buy_vip"))
        channel_clean = config.SPONSOR_CHANNEL.replace('@', '')
        markup.add(InlineKeyboardButton("📢 کانال اسپانسر", url=f"https://t.me/{channel_clean}"))

        bot.send_message(
            user_id,
            "🚫 **ظرفیت پیام‌های رایگان هوش مصنوعی شما به پایان رسید!**\n\n"
            "برای ادامه استفاده می‌توانید یکی از راه‌های زیر را انتخاب کنید:\n"
            "1️⃣ خرید اشتراک نامحدود 💎\n"
            f"2️⃣ دعوت دوستان با لینک اختصاصی (هر دعوت = {config.REFERRAL_BONUS} پیام رایگان):\n`{ref_link}`\n"
            "3️⃣ عضویت در کانال‌های اسپانسر ما",
            reply_markup=markup
        )
        return

    # ثبت تعداد پیام
    user_pv_messages[user_id] = pv_count + 1
    remains = config.FREE_PV_LIMIT - user_pv_messages[user_id]

    bot.send_message(
        user_id,
        f"🧠 **[XAI AI]:** پاسخ شما به «{message.text}»\n\n(باقی‌مانده اعتبار رایگان: {max(0, remains)} پیام)"
    )

# ------------------- کلیک روی دکمه‌ها -------------------

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id

    if call.data == "check_sub":
        if check_subscription(user_id):
            bot.answer_callback_query(call.id, "✅ عضویت شما تایید شد!")
            bot.send_message(user_id, "حالا می‌توانید از ربات استفاده کنید. دستور /start را بفرستید.")
        else:
            bot.answer_callback_query(call.id, "❌ هنوز در کانال عضو نشده‌اید!", show_alert=True)

    elif call.data == "get_ref":
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        invites = user_referrals.get(user_id, 0)

        bot.send_message(
            user_id,
            f"🔗 **لینک دعوت اختصاصی شما:**\n`{ref_link}`\n\n"
            f"👥 تعداد افراد دعوت شده: **{invites} نفر**\n"
            f"🎁 به ازای هر ورود، {config.REFERRAL_BONUS} پیام هوش مصنوعی هدیه می‌گیرید!"
        )

    elif call.data == "buy_vip":
        admin = config.ADMIN_USERNAME.replace('@', '')
        bot.send_message(
            user_id,
            "💎 **پلان‌های اشتراک ویژه‌ XAI MASTER:**\n\n"
            "🔹 اشتراک ۱ ماهه: ۵۰,۰۰۰ تومان\n"
            "🔹 اشتراک ۳ ماهه: ۱۲۰,۰۰۰ تومان\n"
            "🔹 اشتراک دائمی: ۲۵۰,۰۰۰ تومان\n\n"
            f"📞 برای خرید به آیدی پشتیبانی پیام دهید: @{admin}"
        )

if __name__ == "__main__":
    print("🤖 XAI MASTER Bot running with TeleBot...")
    bot.infinity_polling()
