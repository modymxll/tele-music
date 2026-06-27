import os

class Config:
    # ═══ إعدادات أساسية ═══
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    
    # ═══ إعدادات المالك ═══
    OWNER_ID = int(os.environ.get("OWNER_ID", 0))
    BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
    
    # ═══ قناة الدعم ═══
    SUPPORT_CHANNEL = os.environ.get("SUPPORT_CHANNEL", "https://t.me/")
    
    # ═══ قاعدة البيانات ═══
    MONGO_URI = os.environ.get("MONGO_URI", "")
    
    # ═══ إعدادات الموسيقى ═══
    MAX_QUEUE = int(os.environ.get("MAX_QUEUE", 50))
    DEFAULT_VOLUME = int(os.environ.get("DEFAULT_VOLUME", 100))
    
    # ═══ صورة البداية ═══
    START_IMAGE = os.environ.get(
        "START_IMAGE",
        "https://telegra.ph/file/arabic-music-bot.jpg"
    )
    
    # ═══ إعدادات يوتيوب ═══
    COOKIES_FILE = "cookies.txt"
    
    # ═══ حد الاستخدام ═══
    MAX_DURATION = int(os.environ.get("MAX_DURATION", 3600))  # ساعة واحدة
