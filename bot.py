import os
import io
import asyncio
from fastapi import FastAPI, Request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode
from openai import OpenAI

# ==============================
# CONFIGURATION
# ==============================
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"   # replace with your bot token
WEBHOOK_URL = "https://suimon-bot.onrender.com/telegram_webhook"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
fastapi_app = FastAPI()
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()


# ==============================
# HANDLERS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    await update.message.reply_text(
        "🌊 Welcome to *SUIMON*! Upload a meme or image to summon your unique SUIMON card!",
        parse_mode=ParseMode.MARKDOWN
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ *How to use SUIMON Bot:*\n"
        "1️⃣ Send or upload any meme/image.\n"
        "2️⃣ Wait for your SUIMON digital trading card.\n"
        "3️⃣ Tap 'Create Another Card' to summon again!",
        parse_mode=ParseMode.MARKDOWN
    )


async def generate_suimon_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image upload and generate SUIMON card"""
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        image_bytes = await file.download_as_bytearray()

        await update.message.reply_text("✨ Summoning your SUIMON card... please wait...")

        # Generate SUIMON card via OpenAI image generation
        response = client.images.generate(
            model="gpt-image-1",
           PROMPT_TEMPLATE = """
Create a SUIMON digital trading card using the uploaded meme image as the main character.

Include all design elements: name, element, HP, rarity, two attacks, flavor text, and themed background/frame.
Leave a clear area at the bottom for a SUIMON logo overlay.
Top bar: Name, HP, elemental symbol
Main art: Meme image dynamically styled
Attack boxes: Two attacks with creative names, icons, and power
Footer: Weakness/resistance icons and flavor text above the reserved logo space
Use foil or holographic effects for Rare/Ultra Rare/Legendary cards.
Do NOT place text or important elements in the reserved bottom area.
"""
            size="1024x1536",
            referenced_images=[{"image": image_bytes}],
        )

        image_base64 = response.data[0].b64_json
        image_bytes = io.BytesIO(base64.b64decode(image_base64))
        image_bytes.name = "suimon_card.png"

        # Send result
        keyboard = [[InlineKeyboardButton("🎴 Create Another Card", callback_data="create_another")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_photo(
            photo=InputFile(image_bytes),
            caption="🔥 Your SUIMON has been summoned!",
            reply_markup=reply_markup
        )

    except Exception as e:
        print(f"Error generating SUIMON card: {e}")
        await update.message.reply_text("⚠️ Something went wrong while generating your card!")


async def handle_create_another(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Button callback: start a new summon"""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🌀 Send another meme or image to summon your next SUIMON!")


# ==============================
# ADD HANDLERS TO TELEGRAM APP
# ==============================
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(MessageHandler(filters.PHOTO, generate_suimon_card))
telegram_app.add_handler(MessageHandler(filters.COMMAND, help_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, help_command))
telegram_app.add_handler(MessageHandler(filters.COMMAND, help_command))
telegram_app.add_handler(MessageHandler(filters.ALL, help_command))
telegram_app.add_handler(
    telegram.ext.CallbackQueryHandler(handle_create_another, pattern="create_another")
)


# ==============================
# FASTAPI ROUTES
# ==============================
@fastapi_app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates"""
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
    except Exception as e:
        print(f"Webhook error: {e}")
    return {"ok": True}


@fastapi_app.get("/")
async def home():
    return {"status": "✅ SUIMON bot is running on Render"}


# ==============================
# STARTUP EVENT: SET WEBHOOK
# ==============================
@fastapi_app.on_event("startup")
async def on_startup():
    try:
        await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
        print(f"✅ Webhook set to {WEBHOOK_URL}")
    except Exception as e:
        print(f"❌ Failed to set webhook: {e}")


# ==============================
# RUN SERVER
# ==============================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("bot:fastapi_app", host="0.0.0.0", port=port)
