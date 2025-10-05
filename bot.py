import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
from openai import OpenAI
import io
import asyncio

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://suimon-bot.onrender.com/telegram_webhook")

client = OpenAI(api_key=OPENAI_API_KEY)
fastapi_app = FastAPI()
logging.basicConfig(level=logging.INFO)

# --- BOT INITIALIZATION ---
application = Application.builder().token(BOT_TOKEN).build()

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome to the SUIMON Card Creator! Send me an image to create your card.")


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_bytes = await file.download_as_bytearray()

        await update.message.reply_text("⚙️ Creating your SUIMON card... please wait a moment!")

        # Upload image to OpenAI
        uploaded_image = client.images.upload(file=io.BytesIO(file_bytes))

        # Generate SUIMON card
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

        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            image=[uploaded_image.id],  # ✅ correct parameter
            size="1024x1536"
        )

        image_url = result.data[0].url

        keyboard = [
            [InlineKeyboardButton("✨ Create another card", callback_data="create_another")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_photo(
            photo=image_url,
            caption="🎴 Your SUIMON card is ready!",
            reply_markup=reply_markup
        )

    except Exception as e:
        logging.error(f"Error generating card: {e}")
        await update.message.reply_text(f"❌ Error generating card: {e}")


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_another":
        await query.message.reply_text("🖼️ Send another image to create your next SUIMON card!")


# --- REGISTER HANDLERS ---
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.PHOTO, handle_image))
application.add_handler(CallbackQueryHandler(handle_button))

# --- FASTAPI WEBHOOK ENDPOINT ---
@fastapi_app.post("/telegram_webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse({"ok": True})


# --- STARTUP EVENT ---
@fastapi_app.on_event("startup")
async def startup():
    webhook_info = await application.bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await application.bot.set_webhook(WEBHOOK_URL)
        logging.info(f"Webhook set to {WEBHOOK_URL}")
    logging.info("SUIMON bot running with webhook...")


# --- ENTRY POINT ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=10000)
