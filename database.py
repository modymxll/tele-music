import motor.motor_asyncio
from datetime import datetime, timedelta
from config import Config
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = None
        self.db = None
    
    async def initialize(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(Config.MONGO_URI)
        self.db = self.client["arabic_music_bot"]
        
        # إنشاء الفهارس
        await self.db.users.create_index("user_id", unique=True)
        await self.db.groups.create_index("chat_id", unique=True)
        await self.db.history.create_index([("user_id", 1), ("played_at", -1)])
        await self.db.songs.create_index([("title", "text")])
        
        logger.info("✅ تم الاتصال بقاعدة البيانات")
    
    # ═══════════════════════════════════
    #           إدارة المستخدمين
    # ═══════════════════════════════════
    
    async def add_user(self, user_id: int, name: str, username: str = None):
        await self.db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {"name": name, "username": username, "last_seen": datetime.now()},
                "$setOnInsert": {
                    "user_id": user_id,
                    "joined_at": datetime.now(),
                    "songs_played": 0,
                    "total_duration": 0,
                    "banned": False,
                    "favorites": []
                }
            },
            upsert=True
        )
    
    async def get_all_users(self):
        cursor = self.db.users.find({"banned": {"$ne": True}}, {"user_id": 1})
        return [doc["user_id"] async for doc in cursor]
    
    async def ban_user(self, user_id: int):
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"banned": True}}
        )
    
    async def is_banned(self, user_id: int) -> bool:
        doc = await self.db.users.find_one({"user_id": user_id})
        return doc.get("banned", False) if doc else False
    
    async def get_user_stats(self, user_id: int) -> dict:
        doc = await self.db.users.find_one({"user_id": user_id}) or {}
        
        # ترتيب المستخدم
        rank_count = await self.db.users.count_documents({
            "songs_played": {"$gt": doc.get("songs_played", 0)}
        })
        
        # الأغاني الأكثر استماعاً
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$title", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        top_songs = await self.db.history.aggregate(pipeline).to_list(5)
        
        return {
            "total_songs": doc.get("songs_played", 0),
            "total_duration": doc.get("total_duration", 0),
            "favorites_count": len(doc.get("favorites", [])),
            "rank": rank_count + 1,
            "joined_at": doc.get("joined_at", datetime.now()).strftime("%Y/%m/%d"),
            "top_songs": [{"title": s["_id"], "count": s["count"]} for s in top_songs]
        }
    
    # ═══════════════════════════════════
    #           إدارة المجموعات
    # ═══════════════════════════════════
    
    async def add_group(self, chat_id: int, title: str):
        await self.db.groups.update_one(
            {"chat_id": chat_id},
            {
                "$set": {"title": title, "last_active": datetime.now()},
                "$setOnInsert": {
                    "chat_id": chat_id,
                    "created_at": datetime.now(),
                    "songs_played": 0,
                    "settings": {
                        "volume": Config.DEFAULT_VOLUME,
                        "only_admin": False,
                        "auto_leave": True,
                        "delete_commands": False,
                        "show_thumbnail": True,
                        "quality": "عالية",
                        "repeat": "none"
                    },
                    "djs": []
                }
            },
            upsert=True
        )
    
    async def get_all_groups(self):
        cursor = self.db.groups.find({}, {"chat_id": 1, "title": 1, "members": 1})
        return await cursor.to_list(None)
    
    async def get_group_stats(self, chat_id: int) -> dict:
        doc = await self.db.groups.find_one({"chat_id": chat_id}) or {}
        
        today = datetime.now().replace(hour=0, minute=0, second=0)
        
        today_songs = await self.db.history.count_documents({
            "chat_id": chat_id,
            "played_at": {"$gte": today}
        })
        
        today_users = await self.db.history.distinct("user_id", {
            "chat_id": chat_id,
            "played_at": {"$gte": today}
        })
        
        today_duration_pipeline = [
            {"$match": {"chat_id": chat_id, "played_at": {"$gte": today}}},
            {"$group": {"_id": None, "total": {"$sum": "$duration"}}}
        ]
        today_dur = await self.db.history.aggregate(today_duration_pipeline).to_list(1)
        
        top_songs_pipeline = [
            {"$match": {"chat_id": chat_id}},
            {"$group": {"_id": "$title", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        top_songs = await self.db.history.aggregate(top_songs_pipeline).to_list(5)
        
        top_users_pipeline = [
            {"$match": {"chat_id": chat_id}},
            {"$group": {"_id": "$user_id", "songs": {"$sum": 1}, "name": {"$first": "$user_name"}}},
            {"$sort": {"songs": -1}},
            {"$limit": 3}
        ]
        top_users = await self.db.history.aggregate(top_users_pipeline).to_list(3)
        
        return {
            "total_songs": doc.get("songs_played", 0),
            "active_users": len(today_users),
            "total_duration": doc.get("total_duration", 0),
            "created_at": doc.get("created_at", datetime.now()).strftime("%Y/%m/%d"),
            "today_songs": today_songs,
            "today_users": len(today_users),
            "today_duration": today_dur[0]["total"] if today_dur else 0,
            "top_songs": [{"title": s["_id"], "count": s["count"]} for s in top_songs],
            "top_users": [{"name": u.get("name", "مجهول"), "songs": u["songs"]} for u in top_users]
        }
    
    # ═══════════════════════════════════
    #          إعدادات المجموعة
    # ═══════════════════════════════════
    
    async def get_chat_settings(self, chat_id: int) -> dict:
        doc = await self.db.groups.find_one({"chat_id": chat_id})
        if not doc:
            return {
                "volume": Config.DEFAULT_VOLUME,
                "only_admin": False,
                "auto_leave": True,
                "delete_commands": False,
                "show_thumbnail": True,
                "quality": "عالية",
                "repeat": "none"
            }
        return doc.get("settings", {})
    
    async def update_chat_settings(self, chat_id: int, settings: dict):
        await self.db.groups.update_one(
            {"chat_id": chat_id},
            {"$set": {"settings": settings}},
            upsert=True
        )
    
    # ═══════════════════════════════════
    #           نظام DJ
    # ═══════════════════════════════════
    
    async def add_dj(self, chat_id: int, user_id: int):
        await self.db.groups.update_one(
            {"chat_id": chat_id},
            {"$addToSet": {"djs": user_id}}
        )
    
    async def remove_dj(self, chat_id: int, user_id: int):
        await self.db.groups.update_one(
            {"chat_id": chat_id},
            {"$pull": {"djs": user_id}}
        )
    
    async def is_dj(self, chat_id: int, user_id: int) -> bool:
        doc = await self.db.groups.find_one({"chat_id": chat_id})
        return user_id in doc.get("djs", []) if doc else False
    
    async def get_djs(self, chat_id: int) -> list:
        doc = await self.db.groups.find_one({"chat_id": chat_id})
        if not doc:
            return []
        dj_ids = doc.get("djs", [])
        result = []
        for uid in dj_ids:
            user = await self.db.users.find_one({"user_id": uid})
            if user:
                result.append({"user_id": uid, "name": user.get("name", "مجهول")})
        return result
    
    # ═══════════════════════════════════
    #            المفضلة
    # ═══════════════════════════════════
    
    async def add_favorite(self, user_id: int, song_id: str, title: str):
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$addToSet": {"favorites": {"song_id": song_id, "title": title}}}
        )
    
    async def remove_favorite(self, user_id: int, song_id: str):
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$pull": {"favorites": {"song_id": song_id}}}
        )
    
    async def get_favorites(self, user_id: int) -> list:
        doc = await self.db.users.find_one({"user_id": user_id})
        return doc.get("favorites", []) if doc else []
    
    async def clear_favorites(self, user_id: int):
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"favorites": []}}
        )
    
    # ═══════════════════════════════════
    #          التاريخ والإحصاء
    # ═══════════════════════════════════
    
    async def add_history(self, user_id: int, chat_id: int, title: str, 
                          song_id: str, duration: int, user_name: str):
        await self.db.history.insert_one({
            "user_id": user_id,
            "chat_id": chat_id,
            "title": title,
            "song_id": song_id,
            "duration": duration,
            "user_name": user_name,
            "played_at": datetime.now()
        })
        
        # تحديث إحصائيات المستخدم
        await self.db.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"songs_played": 1, "total_duration": duration},
                "$set": {"last_seen": datetime.now()}
            }
        )
        
        # تحديث إحصائيات المجموعة
        await self.db.groups.update_one(
            {"chat_id": chat_id},
            {
                "$inc": {"songs_played": 1, "total_duration": duration},
                "$set": {"last_active": datetime.now()}
            }
        )
    
    async def get_history(self, user_id: int, limit: int = 10) -> list:
        cursor = self.db.history.find(
            {"user_id": user_id},
            {"title": 1, "played_at": 1}
        ).sort("played_at", -1).limit(limit)
        
        result = []
        async for doc in cursor:
            result.append({
                "title": doc["title"],
                "played_at": doc["played_at"].strftime("%Y/%m/%d %H:%M")
            })
        return result
    
    async def log_command(self, user_id: int, chat_id: int, command: str):
        await self.db.logs.insert_one({
            "user_id": user_id,
            "chat_id": chat_id,
            "command": command,
            "time": datetime.now()
        })
    
    # ═══════════════════════════════════
    #         تقرير شامل للمالك
    # ═══════════════════════════════════
    
    async def get_global_report(self) -> dict:
        total_users = await self.db.users.count_documents({})
        total_groups = await self.db.groups.count_documents({})
        total_songs = await self.db.history.count_documents({})
        
        week_ago = datetime.now() - timedelta(days=7)
        today = datetime.now().replace(hour=0, minute=0, second=0)
        
        weekly_active = await self.db.users.count_documents({
            "last_seen": {"$gte": week_ago}
        })
        active_groups = await self.db.groups.count_documents({
            "last_active": {"$gte": week_ago}
        })
        today_songs = await self.db.history.count_documents({
            "played_at": {"$gte": today}
        })
        week_songs = await self.db.history.count_documents({
            "played_at": {"$gte": week_ago}
        })
        
        # إجمالي مدة التشغيل
        duration_pipeline = [
            {"$group": {"_id": None, "total": {"$sum": "$duration"}}}
        ]
        dur_result = await self.db.history.aggregate(duration_pipeline).to_list(1)
        total_duration = dur_result[0]["total"] if dur_result else 0
        
        # أشهر الأغاني
        top_songs_pipeline = [
            {"$group": {"_id": "$title", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        top_songs = await self.db.history.aggregate(top_songs_pipeline).to_list(5)
        
        # إحصائيات يومية
        daily_stats = []
        for i in range(7):
            day = datetime.now() - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0)
            day_end = day.replace(hour=23, minute=59, second=59)
            
            songs = await self.db.history.count_documents({
                "played_at": {"$gte": day_start, "$lte": day_end}
            })
            users = await self.db.history.distinct("user_id", {
                "played_at": {"$gte": day_start, "$lte": day_end}
            })
            
            daily_stats.append({
                "date": day.strftime("%Y/%m/%d"),
                "songs": songs,
                "users": len(users)
            })
        
        return {
            "total_users": total_users,
            "weekly_active": weekly_active,
            "total_groups": total_groups,
            "active_groups": active_groups,
            "total_songs": total_songs,
            "today_songs": today_songs,
            "week_songs": week_songs,
            "total_duration": total_duration,
            "top_songs": [{"title": s["_id"], "count": s["count"]} for s in top_songs],
            "daily_stats": daily_stats
        }
