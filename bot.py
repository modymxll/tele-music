import os
import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import Config
from database import Database
from music_player import MusicPlayer
from helpers import format_time, get_thumb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Client(
    "arabic_music_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

db = Database()
player = MusicPlayer(app, db)

# ═══════════════════════════════════════
#            أوامر البداية
# ═══════════════════════════════════════

@app.on_message(filters.command(["start", "بداية"]) & filters.private)
async def start_cmd(client, message: Message):
    user = message.from_user
    await db.add_user(user.id, user.first_name, user.username)
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 أضفني للمجموعة", url=f"https://t.me/{Config.BOT_USERNAME}?startgroup=true"),
            InlineKeyboardButton("📖 المساعدة", callback_data="help_main")
        ],
        [
            InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats"),
            InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")
        ],
        [
            InlineKeyboardButton("🌐 قناة الدعم", url=Config.SUPPORT_CHANNEL)
        ]
    ])
    
    await message.reply_photo(
        photo=Config.START_IMAGE,
        caption=f"""
🎵 **أهلاً بك يا {user.first_name}!**

أنا **بوت الموسيقى العربي** 🎶
أقوى بوت موسيقى بالعربي على تيليجرام!

**✨ مميزاتي:**
• 🎵 تشغيل موسيقى عالية الجودة
• 📻 راديو مباشر 24/7  
• 🎤 البحث بالعربي والإنجليزي
• 📋 قوائم تشغيل شخصية
• 🔊 تحكم كامل بالصوت
• 📊 إحصائيات وتقارير للمشرفين
• ❤️ المفضلة والتاريخ

**أضفني لمجموعتك وابدأ الاستماع!** 🚀
        """,
        reply_markup=keyboard
    )

@app.on_message(filters.command(["start", "بداية"]) & filters.group)
async def start_group(client, message: Message):
    await message.reply(
        "🎵 **مرحباً! أنا بوت الموسيقى العربي**\n\n"
        "اكتب /مساعدة لرؤية جميع الأوامر\n"
        "أو اكتب /تشغيل + اسم الأغنية لبدء الاستماع! 🎶"
    )

# ═══════════════════════════════════════
#            تشغيل الموسيقى
# ═══════════════════════════════════════

@app.on_message(filters.command(["تشغيل", "play", "p"]) & filters.group)
async def play_music(client, message: Message):
    chat_id = message.chat.id
    user = message.from_user
    
    await db.log_command(user.id, chat_id, "تشغيل")
    
    if len(message.command) < 2 and not message.reply_to_message:
        await message.reply(
            "❌ **يجب كتابة اسم الأغنية!**\n\n"
            "**مثال:** `/تشغيل حمزة نمرة - أفكار`\n"
            "أو قم بالرد على رسالة صوتية"
        )
        return
    
    query = " ".join(message.command[1:]) if len(message.command) > 1 else ""
    
    if message.reply_to_message and message.reply_to_message.audio:
        msg = await message.reply("🔍 **جاري تحضير الأغنية...**")
        await player.play_audio_file(message, msg)
        return
    
    msg = await message.reply(
        f"🔍 **جاري البحث عن:** `{query}`\n"
        "⏳ لحظة من فضلك..."
    )
    
    await player.play_song(message, query, msg)

@app.on_message(filters.command(["بحث", "search"]) & filters.group)
async def search_music(client, message: Message):
    if len(message.command) < 2:
        await message.reply("❌ **اكتب اسم الأغنية للبحث!**\nمثال: `/بحث فيروز`")
        return
    
    query = " ".join(message.command[1:])
    msg = await message.reply(f"🔍 **جاري البحث عن:** `{query}`")
    await player.search_and_show(message, query, msg)

@app.on_message(filters.command(["يوتيوب", "youtube", "yt"]) & filters.group)
async def youtube_play(client, message: Message):
    if len(message.command) < 2:
        await message.reply("❌ **أرسل رابط يوتيوب أو اسم الأغنية!**")
        return
    
    query = " ".join(message.command[1:])
    msg = await message.reply("🎬 **جاري معالجة يوتيوب...**")
    await player.play_youtube(message, query, msg)

# ═══════════════════════════════════════
#         تحكم بالتشغيل
# ═══════════════════════════════════════

@app.on_message(filters.command(["إيقاف", "وقفة", "pause"]) & filters.group)
async def pause_music(client, message: Message):
    if not await is_admin_or_dj(client, message):
        await message.reply("❌ **فقط المشرفون وأعضاء DJ يمكنهم الإيقاف المؤقت!**")
        return
    result = await player.pause(message.chat.id)
    await message.reply("⏸ **تم الإيقاف المؤقت للأغنية**" if result else "❌ **لا توجد أغنية تعزف الآن!**")

@app.on_message(filters.command(["استمرار", "resume"]) & filters.group)
async def resume_music(client, message: Message):
    if not await is_admin_or_dj(client, message):
        await message.reply("❌ **فقط المشرفون وأعضاء DJ يمكنهم الاستمرار!**")
        return
    result = await player.resume(message.chat.id)
    await message.reply("▶️ **استمر التشغيل**" if result else "❌ **لا يوجد شيء موقوف!")

@app.on_message(filters.command(["تخطي", "skip", "التالي"]) & filters.group)
async def skip_music(client, message: Message):
    if not await is_admin_or_dj(client, message):
        await message.reply("❌ **فقط المشرفون وأعضاء DJ يمكنهم التخطي!**")
        return
    result = await player.skip(message.chat.id)
    await message.reply("⏭ **تم التخطي للأغنية التالية**" if result else "❌ **قائمة التشغيل فارغة!**")

@app.on_message(filters.command(["إيقاف_كامل", "end", "stop"]) & filters.group)
async def stop_music(client, message: Message):
    if not await is_admin(client, message):
        await message.reply("❌ **فقط المشرفون يمكنهم الإيقاف الكامل!**")
        return
    await player.stop(message.chat.id)
    await message.reply("⏹ **تم إيقاف التشغيل وتفريغ قائمة الانتظار**")

@app.on_message(filters.command(["صوت", "volume", "vol"]) & filters.group)
async def change_volume(client, message: Message):
    if not await is_admin_or_dj(client, message):
        await message.reply("❌ **فقط المشرفون وأعضاء DJ يمكنهم تغيير الصوت!**")
        return
    
    if len(message.command) < 2:
        settings = await db.get_chat_settings(message.chat.id)
        vol = settings.get("volume", 100)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔉 -10", callback_data=f"vol_down_{message.chat.id}"),
                InlineKeyboardButton(f"🔊 {vol}%", callback_data="vol_show"),
                InlineKeyboardButton("🔊 +10", callback_data=f"vol_up_{message.chat.id}")
            ],
            [
                InlineKeyboardButton("🔇 0%", callback_data=f"vol_set_0_{message.chat.id}"),
                InlineKeyboardButton("📢 50%", callback_data=f"vol_set_50_{message.chat.id}"),
                InlineKeyboardButton("🔊 100%", callback_data=f"vol_set_100_{message.chat.id}")
            ]
        ])
        await message.reply(f"🔊 **مستوى الصوت الحالي: {vol}%**", reply_markup=keyboard)
        return
    
    try:
        vol = int(message.command[1])
        if not 0 <= vol <= 200:
            raise ValueError
    except ValueError:
        await message.reply("❌ **الصوت يجب أن يكون بين 0 و 200!**")
        return
    
    await player.set_volume(message.chat.id, vol)
    await db.update_chat_settings(message.chat.id, {"volume": vol})
    await message.reply(f"🔊 **تم تغيير الصوت إلى {vol}%**")

# ═══════════════════════════════════════
#            قائمة الانتظار
# ═══════════════════════════════════════

@app.on_message(filters.command(["قائمة", "queue", "q"]) & filters.group)
async def show_queue(client, message: Message):
    queue = await player.get_queue(message.chat.id)
    
    if not queue:
        await message.reply("📋 **قائمة التشغيل فارغة!**\nاستخدم /تشغيل لإضافة أغاني")
        return
    
    text = "📋 **قائمة التشغيل:**\n\n"
    for i, song in enumerate(queue[:10], 1):
        if i == 1:
            text += f"🎵 **{i}. {song['title']}** ← يعزف الآن\n"
        else:
            text += f"{'  '}{i}. {song['title']}\n"
    
    if len(queue) > 10:
        text += f"\n_و {len(queue) - 10} أغاني أخرى..._"
    
    text += f"\n\n⏱ **الوقت الكلي:** {format_time(sum(s.get('duration', 0) for s in queue))}"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔀 خلط", callback_data=f"shuffle_{message.chat.id}"),
            InlineKeyboardButton("🗑 تفريغ", callback_data=f"clear_queue_{message.chat.id}")
        ]
    ])
    await message.reply(text, reply_markup=keyboard)

@app.on_message(filters.command(["تكرار", "repeat", "loop"]) & filters.group)
async def toggle_repeat(client, message: Message):
    if not await is_admin_or_dj(client, message):
        await message.reply("❌ **فقط المشرفون وأعضاء DJ!**")
        return
    
    mode = await player.toggle_repeat(message.chat.id)
    modes = {
        "none": "❌ التكرار: إيقاف",
        "song": "🔂 تكرار الأغنية الحالية",
        "queue": "🔁 تكرار قائمة التشغيل"
    }
    await message.reply(f"**{modes.get(mode, 'تم التغيير')}**")

@app.on_message(filters.command(["خلط", "shuffle"]) & filters.group)
async def shuffle_queue(client, message: Message):
    if not await is_admin_or_dj(client, message):
        await message.reply("❌ **فقط المشرفون وأعضاء DJ!**")
        return
    result = await player.shuffle(message.chat.id)
    await message.reply("🔀 **تم خلط قائمة التشغيل عشوائياً!**" if result else "❌ **القائمة فارغة!**")

# ═══════════════════════════════════════
#         المفضلة والتاريخ
# ═══════════════════════════════════════

@app.on_message(filters.command(["مفضلة", "favorites", "fav"]) & filters.private)
async def show_favorites(client, message: Message):
    user_id = message.from_user.id
    favs = await db.get_favorites(user_id)
    
    if not favs:
        await message.reply(
            "⭐ **قائمة المفضلة فارغة!**\n\n"
            "أضف أغاني للمفضلة بالضغط على ❤️ أثناء التشغيل"
        )
        return
    
    text = "⭐ **قائمة مفضلتك:**\n\n"
    buttons = []
    for i, song in enumerate(favs[:15], 1):
        text += f"{i}. 🎵 {song['title']}\n"
        buttons.append([InlineKeyboardButton(f"▶️ {song['title'][:30]}", callback_data=f"play_fav_{song['song_id']}")])
    
    buttons.append([InlineKeyboardButton("🗑 مسح الكل", callback_data="clear_favorites")])
    await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_message(filters.command(["تاريخ", "history"]) & filters.private)
async def show_history(client, message: Message):
    user_id = message.from_user.id
    history = await db.get_history(user_id)
    
    if not history:
        await message.reply("📜 **لا يوجد تاريخ استماع بعد!**")
        return
    
    text = "📜 **آخر ما استمعت إليه:**\n\n"
    for i, song in enumerate(history[:10], 1):
        text += f"{i}. 🎵 {song['title']}\n   ⏰ {song['played_at']}\n\n"
    
    await message.reply(text)

# ═══════════════════════════════════════
#            الراديو المباشر
# ═══════════════════════════════════════

@app.on_message(filters.command(["راديو", "radio"]) & filters.group)
async def radio_cmd(client, message: Message):
    radios = {
        "1": ("إذاعة القرآن الكريم", "https://stream.radiojar.com/0tpy1h0kxtzuv"),
        "2": ("إذاعة MBC FM", "https://live.mbcfm.com/mbcfm"),
        "3": ("إذاعة روتانا", "https://stream.rotana.net/live"),
        "4": ("إذاعة نغم FM", "https://radio.nagham.fm/stream"),
    }
    
    if len(message.command) < 2:
        buttons = []
        for num, (name, _) in radios.items():
            buttons.append([InlineKeyboardButton(f"📻 {name}", callback_data=f"radio_{num}_{message.chat.id}")])
        buttons.append([InlineKeyboardButton("❌ إغلاق", callback_data="close")])
        
        await message.reply(
            "📻 **اختر إذاعة:**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
    
    num = message.command[1]
    if num in radios:
        name, url = radios[num]
        if not await is_admin_or_dj(client, message):
            await message.reply("❌ **فقط المشرفون وأعضاء DJ يمكنهم تشغيل الراديو!**")
            return
        msg = await message.reply(f"📻 **جاري تشغيل {name}...**")
        await player.play_radio(message, url, name, msg)

# ═══════════════════════════════════════
#       إدارة الغرفة الصوتية
# ═══════════════════════════════════════

@app.on_message(filters.command(["انضمام", "join"]) & filters.group)
async def join_vc(client, message: Message):
    if not await is_admin(client, message):
        await message.reply("❌ **فقط المشرفون يمكنهم الانضمام للمكالمة!**")
        return
    result = await player.join_voice_chat(message.chat.id)
    if result:
        await message.reply("✅ **تم الانضمام للمكالمة الصوتية!**")
    else:
        await message.reply("❌ **لا توجد مكالمة صوتية نشطة في المجموعة!**")

@app.on_message(filters.command(["مغادرة", "leave"]) & filters.group)
async def leave_vc(client, message: Message):
    if not await is_admin(client, message):
        await message.reply("❌ **فقط المشرفون يمكنهم المغادرة!**")
        return
    await player.leave_voice_chat(message.chat.id)
    await message.reply("👋 **تم مغادرة المكالمة الصوتية**")

# ═══════════════════════════════════════
#         نظام DJ والأدوار
# ═══════════════════════════════════════

@app.on_message(filters.command(["إضافة_dj", "add_dj"]) & filters.group)
async def add_dj(client, message: Message):
    if not await is_admin(client, message):
        await message.reply("❌ **فقط المشرفون يمكنهم تعيين DJ!**")
        return
    
    if not message.reply_to_message:
        await message.reply("❌ **قم بالرد على مستخدم لتعيينه DJ!**")
        return
    
    target = message.reply_to_message.from_user
    await db.add_dj(message.chat.id, target.id)
    await message.reply(f"🎧 **تم تعيين {target.first_name} كـ DJ في هذه المجموعة!**")

@app.on_message(filters.command(["إزالة_dj", "remove_dj"]) & filters.group)
async def remove_dj(client, message: Message):
    if not await is_admin(client, message):
        await message.reply("❌ **فقط المشرفون يمكنهم إزالة DJ!**")
        return
    
    if not message.reply_to_message:
        await message.reply("❌ **قم بالرد على مستخدم لإزالة صلاحية DJ!**")
        return
    
    target = message.reply_to_message.from_user
    await db.remove_dj(message.chat.id, target.id)
    await message.reply(f"✅ **تم إزالة صلاحية DJ من {target.first_name}!**")

@app.on_message(filters.command(["قائمة_dj", "dj_list"]) & filters.group)
async def list_dj(client, message: Message):
    djs = await db.get_djs(message.chat.id)
    if not djs:
        await message.reply("🎧 **لا يوجد DJ في هذه المجموعة!**")
        return
    
    text = "🎧 **قائمة DJ:**\n\n"
    for dj in djs:
        text += f"• {dj['name']} (#{dj['user_id']})\n"
    await message.reply(text)

# ═══════════════════════════════════════
#      إحصائيات وتقارير للأونر
# ═══════════════════════════════════════

@app.on_message(filters.command(["إحصائيات", "stats"]) & filters.group)
async def group_stats(client, message: Message):
    if not await is_admin(client, message):
        await message.reply("❌ **فقط المشرفون يمكنهم رؤية الإحصائيات!**")
        return
    
    stats = await db.get_group_stats(message.chat.id)
    
    text = f"""
📊 **إحصائيات المجموعة**
━━━━━━━━━━━━━━━━

🎵 **الأغاني المُشغَّلة:** {stats['total_songs']:,}
👥 **المستخدمون النشطون:** {stats['active_users']:,}
⏱ **وقت التشغيل:** {format_time(stats['total_duration'])}
📅 **منذ:** {stats['created_at']}

**📈 اليوم:**
• أغاني: {stats['today_songs']}
• مستخدمون: {stats['today_users']}
• وقت: {format_time(stats['today_duration'])}

**🏆 الأغاني الأكثر تشغيلاً:**
"""
    for i, song in enumerate(stats['top_songs'][:5], 1):
        text += f"{i}. {song['title']} ({song['count']} مرة)\n"
    
    text += f"\n**👑 المستخدمون الأكثر نشاطاً:**\n"
    for i, user in enumerate(stats['top_users'][:3], 1):
        text += f"{i}. {user['name']} ({user['songs']} أغنية)\n"
    
    await message.reply(text)

@app.on_message(filters.command(["تقرير", "report"]) & filters.private)
async def owner_report(client, message: Message):
    if message.from_user.id != Config.OWNER_ID:
        return
    
    report = await db.get_global_report()
    
    text = f"""
📈 **تقرير شامل - {datetime.now().strftime('%Y/%m/%d')}**
━━━━━━━━━━━━━━━━━━━━

🤖 **البوت:**
• إجمالي المستخدمين: {report['total_users']:,}
• مستخدمون نشطون (7 أيام): {report['weekly_active']:,}
• إجمالي المجموعات: {report['total_groups']:,}
• مجموعات نشطة: {report['active_groups']:,}

🎵 **الموسيقى:**
• إجمالي الأغاني: {report['total_songs']:,}
• اليوم: {report['today_songs']:,}
• هذا الأسبوع: {report['week_songs']:,}
• إجمالي وقت التشغيل: {format_time(report['total_duration'])}

🔥 **الأكثر شيوعاً:**
"""
    for i, song in enumerate(report['top_songs'][:5], 1):
        text += f"{i}. {song['title']} ({song['count']:,} مرة)\n"
    
    text += "\n📊 **نشاط آخر 7 أيام:**\n"
    for day in report['daily_stats']:
        text += f"• {day['date']}: {day['songs']} أغنية, {day['users']} مستخدم\n"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 تصدير Excel", callback_data="export_excel"),
            InlineKeyboardButton("📨 إرسال للقناة", callback_data="send_report_channel")
        ]
    ])
    await message.reply(text, reply_markup=keyboard)

@app.on_message(filters.command(["إحصائياتي", "mystats"]) & filters.private)
async def my_stats(client, message: Message):
    user_id = message.from_user.id
    stats = await db.get_user_stats(user_id)
    
    text = f"""
📊 **إحصائياتك الشخصية**
━━━━━━━━━━━━━━

🎵 **أغانٍ استمعت إليها:** {stats['total_songs']:,}
⏱ **إجمالي وقت الاستماع:** {format_time(stats['total_duration'])}
⭐ **المفضلة:** {stats['favorites_count']}
🏆 **المرتبة:** #{stats['rank']}

**🎶 أكثر ما استمعت إليه:**
"""
    for i, song in enumerate(stats['top_songs'][:5], 1):
        text += f"{i}. {song['title']} ({song['count']} مرة)\n"
    
    text += f"\n📅 **عضو منذ:** {stats['joined_at']}"
    await message.reply(text)

# ═══════════════════════════════════════
#            إعدادات المجموعة
# ═══════════════════════════════════════

@app.on_message(filters.command(["إعدادات", "settings"]) & filters.group)
async def group_settings(client, message: Message):
    if not await is_admin(client, message):
        await message.reply("❌ **فقط المشرفون يمكنهم تغيير الإعدادات!**")
        return
    
    settings = await db.get_chat_settings(message.chat.id)
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"{'✅' if settings.get('only_admin') else '❌'} تشغيل للمشرفين فقط",
                callback_data=f"toggle_admin_only_{message.chat.id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if settings.get('auto_leave') else '❌'} مغادرة تلقائية عند الفراغ",
                callback_data=f"toggle_auto_leave_{message.chat.id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if settings.get('delete_commands') else '❌'} حذف أوامر التشغيل",
                callback_data=f"toggle_del_cmd_{message.chat.id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if settings.get('show_thumbnail') else '❌'} عرض الصورة المصغرة",
                callback_data=f"toggle_thumb_{message.chat.id}"
            )
        ],
        [
            InlineKeyboardButton("🔊 الجودة", callback_data=f"quality_{message.chat.id}"),
            InlineKeyboardButton("❌ إغلاق", callback_data="close")
        ]
    ])
    
    await message.reply(
        f"⚙️ **إعدادات المجموعة**\n\n"
        f"🔊 الصوت: {settings.get('volume', 100)}%\n"
        f"🎵 الجودة: {settings.get('quality', 'عالية')}",
        reply_markup=keyboard
    )

# ═══════════════════════════════════════
#            المساعدة
# ═══════════════════════════════════════

@app.on_message(filters.command(["مساعدة", "help"]))
async def help_cmd(client, message: Message):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 التشغيل", callback_data="help_play"),
            InlineKeyboardButton("⚙️ التحكم", callback_data="help_control")
        ],
        [
            InlineKeyboardButton("📋 القوائم", callback_data="help_queue"),
            InlineKeyboardButton("🎧 الراديو", callback_data="help_radio")
        ],
        [
            InlineKeyboardButton("👑 الإدارة", callback_data="help_admin"),
            InlineKeyboardButton("📊 الإحصائيات", callback_data="help_stats")
        ],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="help_main")]
    ])
    
    await message.reply(
        "📖 **مرحباً بك في المساعدة!**\n\n"
        "اختر القسم الذي تريد معرفة أوامره:",
        reply_markup=keyboard
    )

# ═══════════════════════════════════════
#       أوامر المالك (Owner)
# ═══════════════════════════════════════

@app.on_message(filters.command(["إذاعة_عامة", "broadcast"]) & filters.user(Config.OWNER_ID))
async def broadcast(client, message: Message):
    if not message.reply_to_message:
        await message.reply("❌ **قم بالرد على رسالة لإذاعتها!**")
        return
    
    msg = await message.reply("📨 **جاري الإذاعة...**")
    users = await db.get_all_users()
    sent = failed = 0
    
    for user_id in users:
        try:
            await message.reply_to_message.forward(user_id)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    
    await msg.edit(f"✅ **تمت الإذاعة!**\n📤 نجح: {sent}\n❌ فشل: {failed}")

@app.on_message(filters.command(["حظر_مستخدم", "ban_user"]) & filters.user(Config.OWNER_ID))
async def ban_user(client, message: Message):
    if len(message.command) < 2:
        await message.reply("❌ **أرسل معرف المستخدم!**")
        return
    try:
        user_id = int(message.command[1])
        await db.ban_user(user_id)
        await message.reply(f"🔨 **تم حظر المستخدم #{user_id}**")
    except:
        await message.reply("❌ **معرف غير صحيح!**")

@app.on_message(filters.command(["مجموعاتي", "my_groups"]) & filters.user(Config.OWNER_ID))
async def owner_groups(client, message: Message):
    groups = await db.get_all_groups()
    text = f"📊 **إجمالي المجموعات: {len(groups)}**\n\n"
    for g in groups[:20]:
        text += f"• {g['title']} | {g['members']} عضو\n"
    await message.reply(text)

# ═══════════════════════════════════════
#          Callback Handlers
# ═══════════════════════════════════════

@app.on_callback_query()
async def callbacks(client, callback: CallbackQuery):
    data = callback.data
    user = callback.from_user
    
    if data == "close":
        await callback.message.delete()
    
    elif data == "help_main":
        await callback.message.edit_text(
            "🎵 **بوت الموسيقى العربي**\n\n"
            "أقوى بوت موسيقى عربي على تيليجرام!\n\n"
            "اختر قسماً للمساعدة:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🎵 التشغيل", callback_data="help_play"),
                    InlineKeyboardButton("⚙️ التحكم", callback_data="help_control")
                ],
                [
                    InlineKeyboardButton("📋 القوائم", callback_data="help_queue"),
                    InlineKeyboardButton("🎧 الراديو", callback_data="help_radio")
                ],
                [
                    InlineKeyboardButton("👑 الإدارة", callback_data="help_admin"),
                    InlineKeyboardButton("📊 الإحصائيات", callback_data="help_stats")
                ]
            ])
        )
    
    elif data == "help_play":
        await callback.message.edit_text(
            "🎵 **أوامر التشغيل:**\n\n"
            "• `/تشغيل [اسم أغنية]` - تشغيل أغنية\n"
            "• `/بحث [اسم]` - البحث عن أغنية\n"
            "• `/يوتيوب [رابط/اسم]` - تشغيل من يوتيوب\n"
            "• `/راديو` - تشغيل راديو مباشر\n\n"
            "💡 **نصيحة:** يمكنك أيضاً إرسال ملف صوتي مباشرة!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="help_main")]])
        )
    
    elif data == "help_control":
        await callback.message.edit_text(
            "⚙️ **أوامر التحكم:**\n\n"
            "• `/إيقاف` - إيقاف مؤقت\n"
            "• `/استمرار` - استمرار التشغيل\n"
            "• `/تخطي` - تخطي الأغنية الحالية\n"
            "• `/إيقاف_كامل` - إيقاف وتفريغ القائمة\n"
            "• `/صوت [0-200]` - تغيير مستوى الصوت\n"
            "• `/تكرار` - تفعيل/إيقاف التكرار",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="help_main")]])
        )
    
    elif data == "help_queue":
        await callback.message.edit_text(
            "📋 **أوامر القوائم:**\n\n"
            "• `/قائمة` - عرض قائمة الانتظار\n"
            "• `/خلط` - خلط القائمة عشوائياً\n"
            "• `/مفضلة` - قائمة مفضلتك\n"
            "• `/تاريخ` - سجل الاستماع",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="help_main")]])
        )
    
    elif data == "help_admin":
        await callback.message.edit_text(
            "👑 **أوامر الإدارة:**\n\n"
            "• `/إعدادات` - إعدادات المجموعة\n"
            "• `/إضافة_dj` - تعيين DJ\n"
            "• `/إزالة_dj` - إزالة DJ\n"
            "• `/قائمة_dj` - عرض قائمة DJ\n"
            "• `/انضمام` - انضمام للمكالمة\n"
            "• `/مغادرة` - مغادرة المكالمة",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="help_main")]])
        )
    
    elif data == "help_stats":
        await callback.message.edit_text(
            "📊 **أوامر الإحصائيات:**\n\n"
            "• `/إحصائيات` - إحصائيات المجموعة\n"
            "• `/إحصائياتي` - إحصائياتك الشخصية\n\n"
            "**للمالك فقط:**\n"
            "• `/تقرير` - تقرير شامل\n"
            "• `/إذاعة_عامة` - إذاعة لجميع المستخدمين\n"
            "• `/مجموعاتي` - قائمة جميع المجموعات",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="help_main")]])
        )
    
    elif data.startswith("vol_"):
        parts = data.split("_")
        chat_id = int(parts[-1])
        if not await is_admin_or_dj_callback(client, callback, chat_id):
            await callback.answer("❌ ليس لديك صلاحية!", show_alert=True)
            return
        
        settings = await db.get_chat_settings(chat_id)
        vol = settings.get("volume", 100)
        
        if parts[1] == "up":
            vol = min(200, vol + 10)
        elif parts[1] == "down":
            vol = max(0, vol - 10)
        elif parts[1] == "set":
            vol = int(parts[2])
        
        await player.set_volume(chat_id, vol)
        await db.update_chat_settings(chat_id, {"volume": vol})
        await callback.answer(f"✅ الصوت: {vol}%")
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔉 -10", callback_data=f"vol_down_{chat_id}"),
                InlineKeyboardButton(f"🔊 {vol}%", callback_data="vol_show"),
                InlineKeyboardButton("🔊 +10", callback_data=f"vol_up_{chat_id}")
            ],
            [
                InlineKeyboardButton("🔇 0%", callback_data=f"vol_set_0_{chat_id}"),
                InlineKeyboardButton("📢 50%", callback_data=f"vol_set_50_{chat_id}"),
                InlineKeyboardButton("🔊 100%", callback_data=f"vol_set_100_{chat_id}")
            ]
        ])
        await callback.message.edit_reply_markup(keyboard)
    
    elif data.startswith("toggle_"):
        parts = data.split("_")
        setting = "_".join(parts[1:-1])
        chat_id = int(parts[-1])
        
        settings = await db.get_chat_settings(chat_id)
        key_map = {
            "admin": "only_admin",
            "auto": "auto_leave",
            "del": "delete_commands",
            "thumb": "show_thumbnail"
        }
        key = key_map.get(parts[1], parts[1])
        settings[key] = not settings.get(key, False)
        await db.update_chat_settings(chat_id, settings)
        await callback.answer("✅ تم التحديث!")
    
    elif data.startswith("shuffle_"):
        chat_id = int(data.split("_")[1])
        await player.shuffle(chat_id)
        await callback.answer("🔀 تم الخلط!")
    
    elif data.startswith("clear_queue_"):
        chat_id = int(data.split("_")[2])
        await player.clear_queue(chat_id)
        await callback.answer("🗑 تم تفريغ القائمة!")
        await callback.message.edit_text("📋 **قائمة التشغيل فارغة الآن!**")
    
    elif data == "my_stats":
        stats = await db.get_user_stats(user.id)
        await callback.message.edit_text(
            f"📊 **إحصائياتك:**\n\n"
            f"🎵 أغانٍ: {stats.get('total_songs', 0)}\n"
            f"⏱ وقت: {format_time(stats.get('total_duration', 0))}\n"
            f"⭐ مفضلة: {stats.get('favorites_count', 0)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_start")]])
        )
    
    await callback.answer()

# ═══════════════════════════════════════
#            دوال مساعدة
# ═══════════════════════════════════════

async def is_admin(client, message: Message) -> bool:
    if message.from_user.id == Config.OWNER_ID:
        return True
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ["creator", "administrator"]
    except:
        return False

async def is_admin_or_dj(client, message: Message) -> bool:
    if await is_admin(client, message):
        return True
    settings = await db.get_chat_settings(message.chat.id)
    if not settings.get("only_admin", False):
        return True
    return await db.is_dj(message.chat.id, message.from_user.id)

async def is_admin_or_dj_callback(client, callback: CallbackQuery, chat_id: int) -> bool:
    if callback.from_user.id == Config.OWNER_ID:
        return True
    try:
        member = await client.get_chat_member(chat_id, callback.from_user.id)
        if member.status in ["creator", "administrator"]:
            return True
    except:
        pass
    return await db.is_dj(chat_id, callback.from_user.id)

# ═══════════════════════════════════════
#            تشغيل البوت
# ═══════════════════════════════════════

async def main():
    await db.initialize()
    logger.info("✅ قاعدة البيانات جاهزة")
    
    await app.start()
    me = await app.get_me()
    logger.info(f"✅ البوت يعمل: @{me.username}")
    
    await app.idle()

if __name__ == "__main__":
    asyncio.run(main())
