import os
import io
import base64
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
from openai import OpenAI

# -----------------------------
# Configuration
# -----------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUIMON_LOGO_PATH = "assets/suimon_logo.png"
WEBHOOK_PATH = "/telegram_webhook"
PORT = int(os.environ.get("PORT", 10000))
DOMAIN = os.getenv("RENDER_EXTERNAL_URL", "https://suimon-bot.onrender.com")
WEBHOOK_URL = f"{DOMAIN}{WEBHOOK_PATH}"

if not BOT_TOKEN or not OPENAI_API_KEY:
    raise ValueError("❌ Missing TELEGRAM_BOT_TOKEN or OPENAI_API_KEY in environment!")

client = OpenAI(api_key=OPENAI_API_KEY)

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
    """Generate SUIMON card image using OpenAI"""
    meme_bytes_io.seek(0)
    meme_b64 = base64.b64encode(meme_bytes_io.read()).decode("utf-8")

    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt_text,
        size="1024x1536",
        referenced_images=[{"image": meme_b64}],
    )

    card_data = response.data[0].b64_json
    return Image.open(io.BytesIO(base64.b64decode(card_data)))


def add_logo_to_card(card_image, logo_path, scale=0.18, padding=25):
    """Overlay SUIMON logo at bottom of generated card"""
    card = card_image.convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    card_width, card_height = card.size
    logo_ratio = logo.width / logo.height
    logo_width = int(card_width * scale)
    logo_height = int(logo_width / logo_ratio)

    logo = logo.resize((logo_width, logo_height), Image.LANCZOS)
    x_pos = (card_width - logo_width) // 2
    y_pos = card_height - logo_height - padding

    card.paste(logo, (x_pos, y_pos), logo)
    return card


# -----------------------------
# Telegram Handlers
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌊 Welcome to the SUIMON card bot! Send a SUIMON meme and I'll generate a digital trading card for you!"
    )


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    user_mention = (
        update.message.from_user.mention_html()
        if chat_type in ["group", "supergroup"]
        else ""
    )

    photo = update.message.photo[-1]
    file = await photo.get_file()
    meme_bytes_io = io.BytesIO()
    await file.download_to_memory(out=meme_bytes_io)
    meme_bytes_io.seek(0)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        card_image = generate_suimon_card(meme_bytes_io, PROMPT_TEMPLATE)
        final_card = add_logo_to_card(card_image, SUIMON_LOGO_PATH)

        output_bytes = io.BytesIO()
        final_card.save(output_bytes, format="PNG")
        output_bytes.seek(0)

        keyboard = [
            [InlineKeyboardButton("🎴 Create Another Card", callback_data="create_another")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = (
            f"{user_mention} Here’s your SUIMON card! 🃏"
            if user_mention
            else "Here’s your SUIMON card! 🃏"
        )

        await update.message.reply_photo(
            photo=output_bytes,
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    except Exception as e:
        print(f"Error generating card: {e}")
        await update.message.reply_text("⚠️ Sorry, something went wrong while generating your SUIMON card!")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "create_another":
        await query.message.reply_text("✨ Send another meme or image to summon your next SUIMON!")


# -----------------------------
# FastAPI + PTB
# -----------------------------
fastapi_app = FastAPI()
ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(MessageHandler(filters.PHOTO, handle_image))
ptb_app.add_handler(CallbackQueryHandler(button_callback))


@fastapi_app.get("/")
async def root():
    return {"status": "✅ SUIMON bot is running on Render"}


@fastapi_app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.update_queue.put(update)
    return {"ok": True}


@fastapi_app.on_event("startup")
async def on_startup():
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook set to {WEBHOOK_URL}")


@fastapi_app.on_event("shutdown")
async def on_shutdown():
    await ptb_app.stop()
    await ptb_app.shutdown()
    print("🛑 SUIMON bot stopped cleanly.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:fastapi_app", host="0.0.0.0", port=PORT)
