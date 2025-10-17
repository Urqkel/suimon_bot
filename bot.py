import os
import io, math, random
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
from PIL import Image, ImageEnhance, ImageFilter
import openai

# -----------------------------
# Configuration
# -----------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FOIL_STAMP_PATH = "Assets/Foil_Stamp.png"
WEBHOOK_PATH = "/telegram_webhook"
PORT = int(os.environ.get("PORT", 10000))
DOMAIN = os.getenv("RENDER_EXTERNAL_URL", "https://your-render-domain.com")
WEBHOOK_URL = f"{DOMAIN}{WEBHOOK_PATH}"

openai.api_key = OPENAI_API_KEY

PROMPT_TEMPLATE = """
Create a SUIMON digital trading card using the uploaded meme image as the main character.

Design guidelines:
- Always invent a unique, creative character name that matches the personality or vibe of the uploaded image.
- NEVER use the word "SUIMON" as the character name.
- Maintain a balanced layout with well-spaced elements.
- Include all standard card elements: name, HP, element, two attacks, flavor text, and themed background/frame.

Layout & spacing rules:
- Top bar: Place the character name on the left, HP text on the right, and the elemental symbol beside the HP.
  Always ensure the HP number and symbol are fully visible and never overlap or touch.
  Maintain at least 15% horizontal spacing between HP text and symbol edges.
- Main art: Use the uploaded meme image as the main character, stylized dynamically.
- Attack boxes: Include two attacks with creative names, icons, and power.
- Flavor text: Include EXACTLY ONE short line of unique flavor text beneath the attacks.
  Do not repeat or restate the same flavor text line anywhere on the card.
- Footer: Weakness/resistance icons should appear on the left side, and leave a blank space in the bottom-right corner for the official foil stamp overlay.
- The foil stamp area must remain completely empty and unobstructed.
- The foil stamp is embossed into the card surface — pressed into the material, not floating above it.
- Overall feel: vintage, realistic, collectible, with subtle foil lighting or embossed textures.
"""

# -----------------------------
# Helper functions
# -----------------------------
def generate_suimon_card(image_bytes_io, prompt_text):
    """
    Generate a SUIMON card using the uploaded meme image as the base for the character.
    Returns the generated card as a Pillow Image object.
    """
    image_bytes_io.seek(0)
    img = Image.open(image_bytes_io)
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    img_bytes_io = io.BytesIO()
    img.save(img_bytes_io, format="PNG")
    img_bytes_io.name = "meme.png"
    img_bytes_io.seek(0)

    full_prompt = f"Use the uploaded image as the main character for a SUIMON card. {prompt_text}"

    response = openai.images.edit(
        model="gpt-image-1",
        image=img_bytes_io,
        prompt=full_prompt,
        size="1024x1536"
    )

    card_b64 = response.data[0].b64_json
    return Image.open(io.BytesIO(base64.b64decode(card_b64)))


def add_foil_stamp(card_image: Image.Image, logo_path="Assets/Foil_Stamp.png"):
    """
    Adds an embossed foil stamp overlay to the bottom-right corner of the card.
    Ensures it does not overlap text and appears pressed into the surface.
    """
    card = card_image.convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    foil_scale = float(os.getenv("FOIL_SCALE", 0.13))
    foil_margin = float(os.getenv("FOIL_MARGIN", 0.05))

    # Resize foil
    logo_width = int(card.width * foil_scale)
    ratio = logo_width / logo.width
    logo_height = int(logo.height * ratio)
    logo_resized = logo.resize((logo_width, logo_height), Image.LANCZOS)

    # Adjust position slightly upward to avoid text overlap
    pos_x = int(card.width - logo_width - card.width * foil_margin)
    pos_y = int(card.height - logo_height - card.height * (foil_margin + 0.015))

    # Create embossed effect
    embossed = logo_resized.filter(ImageFilter.EMBOSS)
    embossed = ImageEnhance.Brightness(embossed).enhance(1.1)
    embossed = ImageEnhance.Contrast(embossed).enhance(1.3)

    # Blend slightly darker to simulate press depth
    darker = ImageEnhance.Brightness(logo_resized).enhance(0.85)
    card.alpha_composite(darker, dest=(pos_x, pos_y))
    card.alpha_composite(embossed, dest=(pos_x, pos_y))

    output = io.BytesIO()
    card.save(output, format="PNG")
    output.seek(0)
    return output

# -----------------------------
# Telegram Handlers
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to SUIMON card creator! Send me a meme and I’ll craft a unique collectible SUIMON card for you 🃏"
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎨 Generating your SUIMON card... please wait a moment!")

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
        final_card_bytes = add_foil_stamp(card_image, FOIL_STAMP_PATH)

        keyboard = [[InlineKeyboardButton("🎨 Create another SUIMON card", callback_data="create_another")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        caption = f"{user_mention} Here’s your SUIMON card! 🃏" if user_mention else "Here’s your SUIMON card! 🃏"

        await update.message.reply_photo(
            photo=final_card_bytes,
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    except Exception as e:
        await update.message.reply_text(f"Sorry, something went wrong: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "create_another":
        await query.message.reply_text("Awesome! Send me a new meme image, and I'll make another SUIMON card for you.")

# -----------------------------
# FastAPI + PTB Integration
# -----------------------------
fastapi_app = FastAPI()
ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(MessageHandler(filters.PHOTO, handle_image))
ptb_app.add_handler(CallbackQueryHandler(button_callback))

@fastapi_app.on_event("startup")
async def startup_event():
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(WEBHOOK_URL)

@fastapi_app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.update_queue.put(update)
    return {"ok": True}

