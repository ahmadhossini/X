import os

# فقط توکن ربات از BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "8941277153:AAFGVvZmUu0lTfW4D9FU0b4t8qIGimhjEac")

# کانال اسپانسر (با @)
SPONSOR_CHANNEL = os.getenv("SPONSOR_CHANNEL", "@XProxy_Net")

# آیدی تلگرام ادمین برای پشتیبانی خرید اشتراک
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "6822309164")

# محدودیت‌های رایگان
FREE_GROUP_LIMIT = 10  # تعداد پیام رایگان در گروه
FREE_PV_LIMIT = 10     # تعداد پیام رایگان هوش مصنوعی در پی‌وی
REFERRAL_BONUS = 5     # تعداد پیام اضافه به ازای هر دعوت
