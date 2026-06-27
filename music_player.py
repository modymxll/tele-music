import asyncio
import logging
from pyrogram import Client
from tgcaller import TgCaller

logger = logging.getLogger(__name__)

class MusicPlayer:
    def __init__(self, app: Client, db):
        self.app = app
        self.db = db
        self.call_py = TgCaller(app)

    async def start(self):
        await self.call_py.start()

    async def join_group_call(self, chat_id, stream):
        await self.call_py.join_call(chat_id, audio_config=stream)
