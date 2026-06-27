import asyncio
import logging
import random
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped, AudioImagePiped
from pytgcalls.types.input_stream import InputAudioStream
from pytgcalls.exceptions import NoActiveGroupCall
import yt_dlp
from database import Database
from config import Config
from helpers import format_time, get_thumb, clean_title

logger = logging.getLogger(__name__)

class MusicPlayer:
    def __init__(self, app: Client, db: Database):
        self.app = app
        self.db = db
        self.call_py = PyTgCalls(app)
        self.queues = {}       # chat_id -> list of songs
        self.current = {}      # chat_id -> current song dict
        self.repeat_mode = {}  # chat_id -> "none" | "song" | "queue"
        self.volumes = {}      # chat_id -> volume int
        
        self.call_py.on_stream_end()(self._on_stream_end)
    
    async def start(self):
        await self.call_py.start()
    
    # ═══════════════════════════════════
    #        بحث وتشغيل يوتيوب
    # ═══════════════════════════════════
    
    def _ydl_opts(self, audio_only=True):
        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extract_flat": False,
            "cookiefile": Config.COOKIES_FILE if __import__("os").path.exists(Config.COOKIES_FILE) else None,
        }
        if audio_only:
            opts["postprocessors"] = []
        return opts
    
    async def search_youtube(self, query: str) -> dict | None:
        loop = asyncio.get_event_loop()
        
        def _search():
            with yt_dlp.YoutubeDL(self._ydl_opts()) as ydl:
                try:
                    if query.startswith("http"):
                        info = ydl.extract_info(query, download=False)
                    else:
                        info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                        if info and "entries" in info:
                            info = info["entries"][0] if info["entries"] else None
                    return info
                except Exception as e:
                    logger.error(f"yt-dlp error: {e}")
                    return None
        
        return await loop.run_in_executor(None, _search)
    
    async def search_and_show(self, message: Message, query: str, msg):
        def _search():
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                try:
                    info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                    return info.get("entries", []) if info else []
                except:
                    return []
        
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _search)
        
        if not results:
            await msg.edit("❌ **لم يتم العثور على نتائج!**")
            return
        
        text = f"🔍 **نتائج البحث عن:** `{query}`\n\n"
        buttons = []
        for i, r in enumerate(results[:5], 1):
            title = clean_title(r.get("title", "بدون عنوان"))
            duration = format_time(r.get("duration", 0))
            text += f"{i}. 🎵 **{title}**\n   ⏱ {duration}\n\n"
            buttons.append([InlineKeyboardButton(
                f"▶️ {i}. {title[:35]}",
                callback_data=f"search_play_{r.get('id', '')}"
            )])
        
        buttons.append([InlineKeyboardButton("❌ إغلاق", callback_data="close")])
        await msg.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
    
    async def play_song(self, message: Message, query: str, msg):
        chat_id = message.chat.id
        user = message.from_user
        
        # إضافة المجموعة للقاعدة
        await self.db.add_group(chat_id, message.chat.title or "")
        
        info = await self.search_youtube(query)
        if not info:
            await msg.edit(
                "❌ **لم يتم العثور على الأغنية!**\n\n"
                "💡 جرب كتابة اسم مختلف أو استخدم `/بحث`"
            )
            return
        
        song = {
            "title": clean_title(info.get("title", "بدون عنوان")),
            "url": info.get("url") or info.get("webpage_url"),
            "duration": info.get("duration", 0),
            "thumbnail": info.get("thumbnail", ""),
            "video_id": info.get("id", ""),
            "requested_by": user.first_name,
            "requested_by_id": user.id,
            "chat_id": chat_id
        }
        
        # التحقق من الحد
        if song["duration"] > Config.MAX_DURATION:
            await msg.edit(
                f"❌ **الأغنية طويلة جداً!**\n"
                f"الحد الأقصى: {format_time(Config.MAX_DURATION)}"
            )
            return
        
        if chat_id in self.current:
            # إضافة لقائمة الانتظار
            if chat_id not in self.queues:
                self.queues[chat_id] = []
            
            if len(self.queues[chat_id]) >= Config.MAX_QUEUE:
                await msg.edit(f"❌ **قائمة التشغيل ممتلئة! (الحد: {Config.MAX_QUEUE})**")
                return
            
            self.queues[chat_id].append(song)
            pos = len(self.queues[chat_id])
            
            await msg.edit(
                f"📋 **تمت الإضافة لقائمة الانتظار**\n\n"
                f"🎵 **{song['title']}**\n"
                f"⏱ المدة: {format_time(song['duration'])}\n"
                f"📍 الموضع: #{pos}\n"
                f"👤 بواسطة: {song['requested_by']}"
            )
        else:
            await self._stream_song(chat_id, song, msg)
    
    async def _stream_song(self, chat_id: int, song: dict, msg=None):
        try:
            settings = await self.db.get_chat_settings(chat_id)
            vol = settings.get("volume", Config.DEFAULT_VOLUME)
            self.volumes[chat_id] = vol
            
            thumb = await get_thumb(song.get("thumbnail", ""))
            
            stream = AudioImagePiped(
                song["url"],
                thumb,
                audio_parameters=InputAudioStream()
            ) if thumb else AudioPiped(song["url"])
            
            if chat_id in self.current:
                await self.call_py.change_stream(chat_id, stream)
            else:
                await self.call_py.join_group_call(chat_id, stream)
            
            await self.call_py.change_volume_call(chat_id, vol)
            self.current[chat_id] = song
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⏸ إيقاف", callback_data=f"pause_{chat_id}"),
                    InlineKeyboardButton("⏭ تخطي", callback_data=f"skip_{chat_id}"),
                    InlineKeyboardButton("⏹ إنهاء", callback_data=f"stop_{chat_id}")
                ],
                [
                    InlineKeyboardButton("🔉", callback_data=f"vol_down_{chat_id}"),
                    InlineKeyboardButton(f"🔊 {vol}%", callback_data="vol_show"),
                    InlineKeyboardButton("🔊", callback_data=f"vol_up_{chat_id}")
                ],
                [
                    InlineKeyboardButton("❤️ مفضلة", callback_data=f"fav_{song['video_id']}_{chat_id}"),
                    InlineKeyboardButton("🔂 تكرار", callback_data=f"repeat_{chat_id}"),
                    InlineKeyboardButton("📋 القائمة", callback_data=f"queue_{chat_id}")
                ]
            ])
            
            caption = (
                f"🎵 **يعزف الآن:**\n\n"
                f"**{song['title']}**\n\n"
                f"⏱ المدة: {format_time(song['duration'])}\n"
                f"👤 طلب بواسطة: {song['requested_by']}\n"
                f"📋 في القائمة: {len(self.queues.get(chat_id, []))} أغنية"
            )
            
            if msg:
                if thumb:
                    try:
                        await msg.delete()
                        await self.app.send_photo(
                            chat_id,
                            photo=thumb,
                            caption=caption,
                            reply_markup=keyboard
                        )
                    except Exception:
                        await msg.edit(caption, reply_markup=keyboard)
                else:
                    await msg.edit(caption, reply_markup=keyboard)
            
            # حفظ في التاريخ
            await self.db.add_history(
                song["requested_by_id"],
                chat_id,
                song["title"],
                song["video_id"],
                song["duration"],
                song["requested_by"]
            )
            
        except NoActiveGroupCall:
            if msg:
                await msg.edit("❌ **لا توجد مكالمة صوتية نشطة!**\nابدأ مكالمة صوتية أولاً.")
        except Exception as e:
            logger.error(f"Stream error: {e}")
            if msg:
                await msg.edit(f"❌ **حدث خطأ أثناء التشغيل:**\n`{str(e)[:200]}`")
    
    async def _on_stream_end(self, _, chat_id: int, __):
        mode = self.repeat_mode.get(chat_id, "none")
        
        if mode == "song" and chat_id in self.current:
            # إعادة الأغنية الحالية
            await self._stream_song(chat_id, self.current[chat_id])
        elif mode == "queue" and chat_id in self.current:
            # إضافة الأغنية الحالية لآخر القائمة
            if chat_id not in self.queues:
                self.queues[chat_id] = []
            self.queues[chat_id].append(self.current[chat_id])
            await self._play_next(chat_id)
        else:
            await self._play_next(chat_id)
    
    async def _play_next(self, chat_id: int):
        if chat_id in self.queues and self.queues[chat_id]:
            next_song = self.queues[chat_id].pop(0)
            self.current[chat_id] = next_song
            await self._stream_song(chat_id, next_song)
        else:
            # القائمة فارغة
            if chat_id in self.current:
                del self.current[chat_id]
            
            settings = await self.db.get_chat_settings(chat_id)
            if settings.get("auto_leave", True):
                try:
                    await self.call_py.leave_group_call(chat_id)
                except:
                    pass
            
            try:
                await self.app.send_message(
                    chat_id,
                    "✅ **انتهت قائمة التشغيل!**\nاستخدم /تشغيل لإضافة أغاني جديدة 🎵"
                )
            except:
                pass
    
    # ═══════════════════════════════════
    #         تشغيل ملف صوتي
    # ═══════════════════════════════════
    
    async def play_audio_file(self, message: Message, msg):
        chat_id = message.chat.id
        audio = message.reply_to_message.audio or message.reply_to_message.voice
        
        if not audio:
            await msg.edit("❌ **لم يتم العثور على ملف صوتي!**")
            return
        
        await msg.edit("⬇️ **جاري تحميل الملف...**")
        
        try:
            file_path = await message.reply_to_message.download()
            
            song = {
                "title": getattr(audio, "file_name", None) or "ملف صوتي",
                "url": file_path,
                "duration": getattr(audio, "duration", 0),
                "thumbnail": "",
                "video_id": f"local_{audio.file_id[:10]}",
                "requested_by": message.from_user.first_name,
                "requested_by_id": message.from_user.id,
                "chat_id": chat_id
            }
            
            await self._stream_song(chat_id, song, msg)
        except Exception as e:
            await msg.edit(f"❌ **فشل التحميل:** `{e}`")
    
    # ═══════════════════════════════════
    #            الراديو
    # ═══════════════════════════════════
    
    async def play_radio(self, message: Message, url: str, name: str, msg):
        chat_id = message.chat.id
        
        song = {
            "title": f"📻 {name}",
            "url": url,
            "duration": 0,
            "thumbnail": "",
            "video_id": f"radio_{name}",
            "requested_by": message.from_user.first_name,
            "requested_by_id": message.from_user.id,
            "chat_id": chat_id
        }
        
        try:
            stream = AudioPiped(url)
            if chat_id in self.current:
                await self.call_py.change_stream(chat_id, stream)
            else:
                await self.call_py.join_group_call(chat_id, stream)
            
            self.current[chat_id] = song
            
            await msg.edit(
                f"📻 **يبث الآن:**\n\n"
                f"**{name}**\n\n"
                f"👤 شغّل بواسطة: {song['requested_by']}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("⏹ إيقاف", callback_data=f"stop_{chat_id}"),
                        InlineKeyboardButton("🔊 الصوت", callback_data=f"vol_up_{chat_id}")
                    ]
                ])
            )
        except NoActiveGroupCall:
            await msg.edit("❌ **لا توجد مكالمة صوتية نشطة!**")
        except Exception as e:
            await msg.edit(f"❌ **خطأ في الراديو:** `{e}`")
    
    async def play_youtube(self, message: Message, query: str, msg):
        await self.play_song(message, query, msg)
    
    # ═══════════════════════════════════
    #         دوال التحكم
    # ═══════════════════════════════════
    
    async def pause(self, chat_id: int) -> bool:
        if chat_id not in self.current:
            return False
        try:
            await self.call_py.pause_stream(chat_id)
            return True
        except:
            return False
    
    async def resume(self, chat_id: int) -> bool:
        if chat_id not in self.current:
            return False
        try:
            await self.call_py.resume_stream(chat_id)
            return True
        except:
            return False
    
    async def skip(self, chat_id: int) -> bool:
        if chat_id not in self.queues or not self.queues[chat_id]:
            if chat_id in self.current:
                del self.current[chat_id]
            try:
                await self.call_py.leave_group_call(chat_id)
            except:
                pass
            return False
        await self._play_next(chat_id)
        return True
    
    async def stop(self, chat_id: int):
        self.queues.pop(chat_id, None)
        self.current.pop(chat_id, None)
        try:
            await self.call_py.leave_group_call(chat_id)
        except:
            pass
    
    async def set_volume(self, chat_id: int, volume: int):
        self.volumes[chat_id] = volume
        try:
            await self.call_py.change_volume_call(chat_id, volume)
        except:
            pass
    
    async def toggle_repeat(self, chat_id: int) -> str:
        modes = ["none", "song", "queue"]
        current = self.repeat_mode.get(chat_id, "none")
        idx = modes.index(current)
        new_mode = modes[(idx + 1) % len(modes)]
        self.repeat_mode[chat_id] = new_mode
        await self.db.update_chat_settings(chat_id, {"repeat": new_mode})
        return new_mode
    
    async def shuffle(self, chat_id: int) -> bool:
        if chat_id not in self.queues or not self.queues[chat_id]:
            return False
        random.shuffle(self.queues[chat_id])
        return True
    
    async def get_queue(self, chat_id: int) -> list:
        queue = []
        if chat_id in self.current:
            queue.append(self.current[chat_id])
        queue.extend(self.queues.get(chat_id, []))
        return queue
    
    async def clear_queue(self, chat_id: int):
        self.queues.pop(chat_id, None)
    
    async def join_voice_chat(self, chat_id: int) -> bool:
        try:
            await self.call_py.join_group_call(
                chat_id,
                AudioPiped("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3")
            )
            return True
        except:
            return False
    
    async def leave_voice_chat(self, chat_id: int):
        self.current.pop(chat_id, None)
        self.queues.pop(chat_id, None)
        try:
            await self.call_py.leave_group_call(chat_id)
        except:
            pass
