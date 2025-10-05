import os
import io
import base64
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from PIL import Image
import openai
import uvicorn

# -----------------------------
# Configuration
# -----------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUIMON_LOGO_PATH = "assets/suimon_logo.png"
WEBHOOK_PATH = "/telegram_webhook"
PORT = int(os.environ.get("PORT", 10000))
DOMAIN = os.getenv("RENDER_EXTERNAL_URL", "https://your-render-domain.com")
WEBHOOK_URL = f"{DOMAIN}{WEBHOOK_PATH}"

openai.api_key = OPENAI_API_KEY

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

# -----------------------------
# Helper functions
# -----------------------------
def generate_suimon_card(meme_bytes_io, prompt_text):
    """Generates the SUIMON card image using OpenAI."""
    response = openai.images.generate(
        model="gpt-image-1",
        prompt=prompt_text,
        image=meme_bytes_io,
        size="1024x1024",
    )
    card_data = response.data[0].b64_json
    return Image.open(io.BytesIO(base64.b64decode(card_data)))

def add_logo_to_card(card_image, logo_path, scale=0.18, padding=25):
    """Overlays the SUIMON logo at the bottom of the card."""
    card = card_image.convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")
    card_width, card_height = card.size
    logo_ratio = logo.width / logo.height
    logo_width = int(card_width * scale)
    logo_height = int(logo_width / logo_ratio)
    logo = logo.resize((logo_width, logo_height), Image.ANTIALIAS)
    x_pos = (card_width - logo_width) // 2
    y_pos = card_height - logo_height - padding
    card.paste(logo, (x_pos, y_pos), logo)
    return card

# -----------------------------
# Telegram Handlers
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to SUIMON! Send me a meme image and I'll generate a SUIMON card for you."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    user_mention = update.message.from_user.mention_html() if chat_type in ["group", "supergroup"] else ""

    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    meme_bytes_io = io.BytesIO()
    await photo_file.download_to_memory(out=meme_bytes_io)
    meme_bytes_io.seek(0)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        card_image = generate_suimon_card(meme_bytes_io, PROMPT_TEMPLATE)
        final_card = add_logo_to_card(card_image, SUIMON_LOGO_PATH)

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        output_bytes = io.BytesIO()
        final_card.save(output_bytes, format="PNG")
        output_bytes.seek(0)

        keyboard = [
            [InlineKeyboardButton("🎨 Create another SUIMON card", callback_data="create_another")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        caption_text = f"{user_mention} Here’s your SUIMON card! 🃏" if user_mention else "Here’s your SUIMON card! 🃏"

        await update.message.reply_photo(
            photo=output_bytes,
            caption=caption_text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    except Exception as e:
        await update.message.reply_text(f"Sorry, something went wrong: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "create_another":
        await query.message.reply_text(
            "Awesome! Send me a new meme image, and I'll make another SUIMON card for you."
        )

# -----------------------------
# FastAPI App for Webhook
# -----------------------------
fastapi_app = FastAPI()
ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(MessageHandler(filters.PHOTO, handle_image))
ptb_app.add_handler(CallbackQueryHandler(button_callback))

@fastapi_app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.update_queue.put(update)
    return {"ok": True}

# -----------------------------
# Run server
# -----------------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(ptb_app.bot.set_webhook(WEBHOOK_URL))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=PORT)
