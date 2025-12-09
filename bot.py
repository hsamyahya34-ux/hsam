#!/usr/bin/env python3
# bot.py — النسخة المحسنة مع API
import logging
import os
import glob
import re
import asyncio
import nest_asyncio
import random
import time
from threading import Thread
from flask import Flask
import requests
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# تطبيق nest_asyncio لمنع مشاكل event loop
nest_asyncio.apply()

# --------------------------- إعدادات أساسية (اضبط المتغيرات البيئية) ---------------------------
TOKEN = os.environ.get("BOT_TOKEN", "8483853992:AAE5vAQA3bN5OrgTVz7TJyWfF-1KTg75jZk")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Softwarespace1")
SHORTIO_API_KEY = "pk_OK1zkt4OTxMgNPFj"  # 🔑 API Key الخاص بك
SHORTIO_DOMAIN = "w7BgsG.short.gy"  # 🌐 النطاق الخاص بك
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", 49))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
KEEP_ALIVE = os.environ.get("KEEP_ALIVE", "false").lower() in ("1", "true", "yes")
# ---------------------------------------------------------------------------------------------

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Logger
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# --------------------------- API لإنشاء روابط عبر short.io ---------------------------
def create_shortio_link(original_url, title="Video Download"):
    """إنشاء رابط قصير عبر short.io API"""
    try:
        headers = {
            "Authorization": SHORTIO_API_KEY,
            "Content-Type": "application/json"
        }

        data = {
            "domain": SHORTIO_DOMAIN,
            "originalURL": original_url,
            "title": title,
            "tags": ["telegram-bot", "video-download"]
        }

        response = requests.post(
            "https://api.short.io/links",
            json=data,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            short_url = result.get("shortURL")
            logger.info(f"✅ تم إنشاء رابط عبر API: {short_url}")
            return short_url
        else:
            logger.error(f"❌ خطأ في API: {response.status_code} - {response.text}")
            return original_url

    except Exception as e:
        logger.error(f"❌ فشل في إنشاء الرابط: {e}")
        return original_url


# --------------------------- إنشاء روابط ربحية متعددة عبر API ---------------------------
def generate_profit_links(user_id, count=3):
    """إنشاء روابط ربحية متعددة باستخدام API"""
    profit_sites = [
        "https://fast-down.com/premium",
        "https://turbo-load.com/boost",
        "https://speed-dl.com/pro",
        "https://premium-download.net/vip",
        "https://express-dl.com/turbo"
    ]

    profit_links = []

    for i in range(count):
        base_site = random.choice(profit_sites)
        # إنشاء رابط فريد مع تتبع
        unique_url = f"{base_site}?ref=user_{user_id}{int(time.time())}{i}"

        # إنشاء رابط قصير عبر API
        short_link = create_shortio_link(unique_url, f"Profit_Link_{user_id}_{i}")
        profit_links.append(short_link)

    return profit_links


# --------------------------- اختصار الرابط الربحي مع دعم API ---------------------------
def shorten_url(url: str) -> str:
    """اختصار الرابط مع优先使用 API"""
    # أولاً جرب API الخاص بـ short.io
    api_link = create_shortio_link(url, "Profit_Link")
    if api_link and api_link != url:
        return api_link

    # إذا فشل API، جرب الخدمات الأخرى
    services = [
        f"https://is.gd/create.php?format=simple&url={url}",
        f"https://tinyurl.com/api-create.php?url={url}",
    ]

    for api in services:
        try:
            r = requests.get(api, timeout=10)
            if r.status_code == 200 and r.text.strip().startswith('http'):
                return r.text.strip()
        except Exception as e:
            logger.warning(f"Shorten failed with {api}: {e}")
            continue

    return url  # الرابط الأصلي إذا فشل الجميع


# اختصار الرابط الربحي الأساسي
PROFIT_LINK = os.environ.get("PROFIT_LINK", "https://fc.lc/YOUR_CUSTOM_PROFIT_LINK")
SHORT_PROFIT = shorten_url(PROFIT_LINK)
logger.info(f"💰 رابط الربح: {SHORT_PROFIT}")


# ---------------------------------------------------------------------------------------------

# --------------------------- استخراج الروابط من النص ---------------------------
def extract_urls(text: str) -> list:
    """استخراج جميع الروابط من النص"""
    url_pattern = r'https?://[^\s]+'
    return re.findall(url_pattern, text)


# ---------------------------------------------------------------------------------------------

# --------------------------- دوال مساعدة محسنة لإيجاد الملف الناتج ---------------------------
def find_downloaded_file(info_dict):
    """نسخة محسنة للعثور على الملف"""
    video_id = info_dict.get("id")
    title = str(info_dict.get("title", "")).replace("/", " ").strip()[:50]

    # البحث بجميع الأنماط الممكنة
    patterns = []
    if video_id:
        patterns.append(os.path.join(DOWNLOAD_DIR, f"{video_id}.*"))

    if title:
        patterns.append(os.path.join(DOWNLOAD_DIR, f"{title}"))

    patterns.append(os.path.join(DOWNLOAD_DIR, "*"))

    for pattern in patterns:
        if pattern:
            files = glob.glob(pattern)
            # تصفية الملفات المرشحة (استبعاد الملفات الجزئية)
            video_files = [f for f in files if not f.endswith('.part') and os.path.isfile(f)]
            if video_files:
                # ترتيب حسب الحجم (الأكبر أولاً) ووقت التعديل
                video_files.sort(key=lambda x: (os.path.getsize(x), os.path.getmtime(x)), reverse=True)
                return video_files[0]

    return None


# ---------------------------------------------------------------------------------------------

# --------------------------- فحص اشتراك المستخدم بالقناة ---------------------------
async def is_user_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """يفحص إن كان المستخدم عضو في القناة المحددة"""
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning(f"check subscription error for {user_id}: {e}")
        return False


# ---------------------------------------------------------------------------------------------

# --------------------------- أوامر البوت المحسنة ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب"""
    welcome_text = f"""
مرحباً 👋 {update.effective_user.first_name}!

🎥 *بوت تحميل الفيديو* من اليوتيوب، تيك توك، إنستغرام وغيرها

⚡ *الميزات:*
• تحميل الفيديو من معظم المنصات
• جودة تصل إلى 720p 
• إرسال مباشر مع عدة روابط تسريع

📋 *الشروط:*
• اشترك في قناتنا أولاً: {CHANNEL_USERNAME}
• الحد الأقصى لحجم الفيديو: {MAX_FILE_SIZE_MB}MB

🚀 *أرسل رابط الفيديو الآن!*
    """
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 قناتنا", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check")]
    ])
    await update.message.reply_text(welcome_text, reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المساعدة"""
    help_text = f"""
📖 *أوامر البوت:*
/start - بدء استخدام البوت  
/help - عرض هذه المساعدة
/status - حالة البوت والاستخدام
/links - الحصول على روابط تسريع

🎥 *المنصات المدعومة:*
• اليوتيوب • تيك توك • إنستغرام
• تويتر • فيسبوك • وغيرها

⚡ *معلومات تقنية:*
• الحد الأقصى: {MAX_FILE_SIZE_MB}MB
• الجودة: حتى 720p
• روابط تسريع عبر API

📢 *قناتنا:* {CHANNEL_USERNAME}
    """
    await update.message.reply_text(help_text)


async def links_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الحصول على روابط تسريع إضافية"""
    user_id = update.effective_user.id
    profit_links = generate_profit_links(user_id, 5)

    links_text = "🔗 *روابط تسريع التحميل الإضافية:*\n\n"
    for i, link in enumerate(profit_links, 1):
        links_text += f"{i}. {link}\n"

    links_text += "\n🎯 *احفظ هذه الروابط لتحميل أسرع!*"

    # أزرار سريعة للروابط الأولى
    keyboard_buttons = []
    for i, link in enumerate(profit_links[:3], 1):
        keyboard_buttons.append([InlineKeyboardButton(f"⚡ الرابط {i}", url=link)])

    keyboard = InlineKeyboardMarkup(keyboard_buttons)

    await update.message.reply_text(links_text, reply_markup=keyboard)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حالة البوت"""
    import psutil
    import datetime

    disk_usage = psutil.disk_usage('/')
    memory = psutil.virtual_memory()

    status_text = f"""
📊 *حالة البوت:*

💾 *التخزين:*
• المستخدم: {disk_usage.used / (1024 ** 3):.1f}GB
• الحر: {disk_usage.free / (1024 ** 3):.1f}GB

🖥 *الذاكرة:*
• المستخدمة: {memory.percent}%

🔗 *API:*
• short.io: ✅ نشط

⏰ *الوقت:*
• {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ *البوت يعمل بشكل طبيعي*
    """
    await update.message.reply_text(status_text)


async def check_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر التحقق من الاشتراك"""
    query = update.callback_query
    await query.answer()

    if await is_user_subscribed(query.from_user.id, context):
        await query.edit_message_text(
            "✅ *تم التحقق بنجاح!*\n\n"
            "يمكنك الآن إرسال رابط الفيديو وسأحمله لك فوراً. 🚀",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎥 إرسال رابط فيديو", switch_inline_query_current_chat="")]
            ])
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 تحقق مرة أخرى", callback_data="check")]
        ])
        await query.edit_message_text(
            "🚫 *لازلت غير مشترك*\n\n"
            f"يجب الاشتراك في {CHANNEL_USERNAME} أولاً لاستخدام البوت.",
            reply_markup=keyboard
        )


# --------------------------- دالة إرسال الفيديو مع عدة أزرار ربحية ---------------------------
async def send_video_with_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, video_path: str,
                                  caption: str = None):
    """إرسال الفيديو مع عدة أزرار ربحية عبر API"""
    try:
        await update.message.reply_chat_action("upload_video")

        # إنشاء روابط ربحية متعددة عبر API
        user_id = update.effective_user.id
        profit_links = generate_profit_links(user_id, 3)

        # إنشاء أزرار متعددة
        keyboard_buttons = []
        for i, link in enumerate(profit_links, 1):
            keyboard_buttons.append([InlineKeyboardButton(f"⚡ تسريع {i}", url=link)])

        keyboard_buttons.append([InlineKeyboardButton("📢 قناتنا", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)

        base_caption = caption or "🎥 تم تحميل الفيديو بنجاح"
        final_caption = f"{base_caption}\n\n🔗 *اختر أحد روابط التسريع أعلاه*\n{CHANNEL_USERNAME}"

        with open(video_path, "rb") as vid:
            size = os.path.getsize(video_path)

            if size <= MAX_FILE_SIZE_BYTES:
                await update.message.reply_video(
                    video=vid,
                    caption=final_caption,
                    reply_markup=keyboard,
                    read_timeout=300,
                    write_timeout=300,
                    connect_timeout=300,
                    pool_timeout=300,
                    supports_streaming=True
                )
            else:
                await update.message.reply_document(
                    document=vid,
                    caption=f"📦 {final_caption}\nالحجم: {size / (1024 * 1024):.1f}MB",
                    reply_markup=keyboard,
                    read_timeout=300,
                    write_timeout=300
                )

        logger.info(f"تم إرسال الفيديو مع {len(profit_links)} روابط للمستخدم {update.effective_user.id}")
        return True

    except TelegramError as te:
        logger.error(f"خطأ في رفع التليجرام: {te}")
        await update.message.reply_text(f"❌ تم تحميل الملف، لكن فشل إرساله:\n{str(te)[:200]}")
        return False
    except Exception as e:
        logger.exception(f"خطأ غير متوقع في الإرسال: {e}")
        await update.message.reply_text(f"❌ خطأ أثناء إرسال الفيديو:\n{str(e)[:200]}")
        return False


# ---------------------------------------------------------------------------------------------

# --------------------------- الدالة الرئيسية المحسنة لتحميل الفيديو ---------------------------
async def handle_download_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة طلبات التحميل"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    text = (update.message.text or "").strip()

    # استخراج الروابط من النص
    urls = extract_urls(text)
    if not urls:
        return await update.message.reply_text(
            "❌ لم أجد أي رابط فيديو في رسالتك.\nأرسل رابط صالح مثل:\nhttps://www.youtube.com/...")

    url = urls[0]  # استخدام أول رابط

    # 1) تحقق اشتراك القناة
    if not await is_user_subscribed(user_id, context):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check")]
        ])
        return await update.message.reply_text(
            f"🚫 *يجب الاشتراك في القناة أولاً*\n\n"
            f"اشترك في {CHANNEL_USERNAME} ثم اضغط تحقق.",
            reply_markup=keyboard
        )

    # إعلام المستخدم ببدء التحميل
    msg = await update.message.reply_text("⏳ *جاري التحضير...*\nقد يستغرق من 10-60 ثانية حسب الجودة والحجم.")

    # إعداد خيارات yt-dlp محسنة
    ydl_opts = {
        "format": "best[height<=720]/best[height<=480]/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "extractaudio": False,
        "keepvideo": True,
        "writethumbnail": False,
        "ignoreerrors": True,
        "geo_bypass": True,
        "geo_bypass_country": "US",
        "extractor_retries": 5,
        "http_chunk_size": 10485760,
    }

    filename = None
    try:
        await msg.edit_text("📥 *جاري تحميل الفيديو...*\nيعتمد الوقت على سرعة الخادم المصدر.")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # الحصول على المعلومات أولاً
            info = ydl.extract_info(url, download=False)
            info_used = (info["entries"][0] if isinstance(info, dict) and info.get("entries") else info) or {}
            title = info_used.get("title", "فيديو")
            duration = info_used.get("duration", 0)

            # التحقق من المدة (لنحمّل مقاطع أقل من 30 دقيقة)
            if duration > 1800:  # 30 دقيقة
                return await msg.edit_text("❌ *المقطع طويل جداً*\n\nيمكنني تحميل مقاطع حتى 30 دقيقة فقط.")

            await msg.edit_text(f"🎬 *جاري تحميل:* {title[:50]}...\n⏱ المدة: {duration // 60}:{duration % 60:02d}")

            # التحميل الفعلي
            ydl.download([url])

        # العثور على الملف الناتج
        filename = find_downloaded_file(info_used)

        if not filename or not os.path.exists(filename):
            logger.error("بعد التحميل لم يتم إيجاد ملف صالح.")
            return await msg.edit_text("❌ *تم التحميل ولكن لم أجد الملف*\nجرب رابط آخر أو تواصل مع الدعم.")

        file_size = os.path.getsize(filename) / (1024 * 1024)  # بالـ MB

        if file_size > MAX_FILE_SIZE_MB:
            await msg.edit_text(f"⚠ *الملف كبير جداً* ({file_size:.1f}MB)\nجاري إرساله كمستند...")
        else:
            await msg.edit_text(f"✅ *تم التحميل بنجاح!* ({file_size:.1f}MB)\nجاري الإرسال الآن...")

        # إرسال الفيديو مع عدة أزرار ربحية عبر API
        caption = f"🎬 {title}\n💾 {file_size:.1f}MB"
        success = await send_video_with_buttons(update, context, filename, caption=caption)

        if success:
            await msg.delete()  # حذف رسالة التحميل بعد النجاح
        else:
            await msg.edit_text("❌ *فشل في إرسال الفيديو*\nحاول مرة أخرى أو جرب رابط مختلف.")

        # تنظيف الملفات
        try:
            os.remove(filename)
            logger.info(f"تم حذف الملف: {filename}")

            # تنظيف الملفات القديمة (أكبر من 1 ساعة)
            cleanup_old_files()

        except Exception as e_rm:
            logger.warning(f"لم أستطع حذف الملف {filename}: {e_rm}")

    except yt_dlp.utils.DownloadError as de:
        logger.error(f"خطأ في التحميل: {de}")
        error_msg = str(de)
        if "Private video" in error_msg:
            await msg.edit_text("❌ *الفيديو خاص*\nلا يمكنني تحميل الفيديوهات الخاصة.")
        elif "Copyright" in error_msg:
            await msg.edit_text("❌ *محمي بحقوق الطبع*\nلا يمكنني تحميل هذا الفيديو.")
        elif "Unsupported URL" in error_msg:
            await msg.edit_text("❌ *رابط غير مدعوم*\nهذا النوع من الروابط غير مدعوم حالياً.")
        else:
            await msg.edit_text(f"❌ *فشل التحميل:*\n{error_msg[:300]}")

    except Exception as e:
        logger.exception(f"خطأ غير متوقع: {e}")
        await msg.edit_text(f"❌ *حدث خطأ غير متوقع:*\n{str(e)[:300]}")


# ---------------------------------------------------------------------------------------------

# --------------------------- تنظيف الملفات القديمة ---------------------------
def cleanup_old_files():
    """حذف الملفات الأقدم من ساعة واحدة"""
    try:
        import time
        current_time = time.time()
        for filename in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(file_path):
                # حذف الملفات الأقدم من ساعة
                if current_time - os.path.getmtime(file_path) > 3600:
                    os.remove(file_path)
                    logger.info(f"تم تنظيف الملف القديم: {filename}")
    except Exception as e:
        logger.warning(f"خطأ في التنظيف: {e}")


# ---------------------------------------------------------------------------------------------

# --------------------------- Keep-alive (محسن لـ Replit) ---------------------------
def start_keep_alive():
    if not KEEP_ALIVE:
        return

    app = Flask("keepalive")

    @app.route("/")
    def home():
        return f"""
        <html>
            <head>
                <title>Video Download Bot</title>
                <meta http-equiv="refresh" content="30">
            </head>
            <body>
                <h1>✅ Bot is Running</h1>
                <p>Video Download Bot is alive and working!</p>
                <p>Channel: {CHANNEL_USERNAME}</p>
                <p>API: short.io ✅</p>
            </body>
        </html>
        """

    def run():
        app.run(host="0.0.0.0", port=3000)

    t = Thread(target=run)
    t.daemon = True
    t.start()
    logger.info("Keep-alive server started on port 3000")


# ---------------------------------------------------------------------------------------------

# --------------------------- تشغيل البوت ---------------------------
def main():
    if not TOKEN:
        logger.error("BOT_TOKEN غير موجود! ضع TOKEN في المتغيرات البيئية BOT_TOKEN")
        return

    start_keep_alive()

    # إعداد التطبيق
    app = Application.builder().token(TOKEN).build()

    # إضافة handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("links", links_command))
    app.add_handler(CallbackQueryHandler(check_button, pattern="^check$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_download_request))

    logger.info("✅ البوت يعمل الآن...")
    logger.info(f"📢 القناة: {CHANNEL_USERNAME}")
    logger.info(f"🔗 API: short.io نشط")

    # تنظيف الملفات عند البدء
    cleanup_old_files()

    # التشغيل
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()