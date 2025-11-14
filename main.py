import json
import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi import FastAPI, Request
from aiogram.types import Update

from scheduler import start_scheduler

# ======================================
# 🔧 CONFIG
# ======================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8383092549:AAE3UGGknaeylE-bd9RxVuTsFc2bIWPVQiE")

GROUP_COMPLAINTS_ID = -1003211230484
GROUP_SOLUTIONS_ID = -1003284967767
GROUP_LEADERS_ID = -1003284967767

GOOGLE_SHEET_ID = "1XP4m-yo3_-Y2QPP49af2VmNFcvwXxB9ig1wVWV2gujk"
SERVICE_ACCOUNT_FILE = "service_account.json"

TIMEZONE = "Asia/Tashkent"

# Railway domain
WEBHOOK_HOST = os.getenv("RAILWAY_PUBLIC_DOMAIN")
WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else None

# ======================================
# 🔧 LOGGING
# ======================================
logging.basicConfig(level=logging.INFO)

# ======================================
# 🤖 BOT & DISPATCHER
# ======================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# save gs key file
if os.getenv("SERVICE_ACCOUNT_JSON"):
    with open(SERVICE_ACCOUNT_FILE, "w") as f:
        f.write(os.getenv("SERVICE_ACCOUNT_JSON"))

# --------------------------------------
# Import routers
# --------------------------------------
from handlers import complaints, callbacks, statistics

dp.include_router(complaints.router)
dp.include_router(callbacks.router)
dp.include_router(statistics.router)

# --------------------------------------
# Bot shared memory (unchanged)
# --------------------------------------
bot.data = {"cancelled": {}}
bot.solution_waiting = {}
bot._sent_ids = set()
bot._called_ids = set()
bot.solution_messages = {}

bot.config = {
    "GROUP_COMPLAINTS_ID": GROUP_COMPLAINTS_ID,
    "GROUP_SOLUTIONS_ID": GROUP_SOLUTIONS_ID,
    "GROUP_LEADERS_ID": GROUP_LEADERS_ID,
    "GOOGLE_SHEET_ID": GOOGLE_SHEET_ID,
    "SERVICE_ACCOUNT_FILE": SERVICE_ACCOUNT_FILE,
    "TIMEZONE": TIMEZONE,
    "ADMINS": [1450296021, 420533161]
}

# ======================================
# 🌐 FASTAPI SERVER (WEBHOOK)
# ======================================
app = FastAPI()


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    body = await request.json()
    update = Update(**body)
    await dp.feed_update(bot, update)
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "running", "webhook": WEBHOOK_URL}


# ======================================
# 🚀 STARTUP EVENT
# ======================================
@app.on_event("startup")
async def on_startup():
    # Remove old webhook & set new one
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

    # Start scheduler
    try:
        start_scheduler(bot)
    except Exception as e:
        logging.warning(f"Scheduler not started: {e}")

    logging.info("🚀 Bot webhook started successfully!")


# ======================================
# ▶️ Local run (uvicorn)
# ======================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
