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
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
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
- Top bar: Place the character name on the left, HP text on the right, and the elemental symbol beside the HP, ensuring they do not overlap.
- Leave at least 10% horizontal spacing between the HP number and any icons or symbols.
- Main art: Use the uploaded meme image as the character art, dynamically styled.
- Attack boxes: Two attacks with creative names, icons, and power.
- Flavor text directly beneath attacks.
- Footer: Weakness/resistance icons located to the left of the reserved foil stamp space.
- Leave a blank area in the bottom-right corner for an official foil stamp overlay (do not draw over it or create a border, it must be blank space).
- The foil stamp is embossed into the card surface — giving it a realistic 3D texture, as though pressed into the card material, not floating above it.
- Overall feel: vintage, realistic, collectible, with subtle foil lighting or embossed textures.
"""

#
# Helper functions
# -----------------------------
def generate_suimon_card(image_bytes_io, prompt_text):
    """
    Generate a SUIMON card using the uploaded meme image as the base for the character.
    Supports JPEG and PNG.
    Returns the card image as a Pillow object.
    """
    image_bytes_io.seek(0)

    # Ensure the file is PNG (best for edit API)
    img = Image.open(image_bytes_io)
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Save to BytesIO with a name attribute to pass correct mimetype
    img_bytes_io = io.BytesIO()
    img.save(img_bytes_io, format="PNG")
    img_bytes_io.name = "meme.png"  # important for API to detect correct mimetype
    img_bytes_io.seek(0)

    # Full prompt
    full_prompt = f"Use the uploaded image as the main character for a SUIMON card. {prompt_text}"

    response = openai.images.edit(
        model="gpt-image-1",
        image=img_bytes_io,  # pass BytesIO with name
        prompt=full_prompt,
        size="1024x1536"
    )

    card_b64 = response.data[0].b64_json
    return Image.open(io.BytesIO(base64.b64decode(card_b64)))

def add_foil_stamp(card_image: Image.Image, logo_path="Assets/Foil_Stamp.png"):
    """
    Adds a foil stamp overlay to the bottom-right corner of the card.
    Uses environment variables FOIL_SCALE and FOIL_MARGIN for positioning.
    """
    card = card_image.convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    # 🔧 Adjustable parameters
    foil_scale = float(os.getenv("FOIL_SCALE", 0.14))   # default 14% of card width
    foil_margin = float(os.getenv("FOIL_MARGIN", 0.04)) # default 4% from edges

    # Resize based on card width
    logo_width = int(card.width * foil_scale)
    logo_ratio = logo_width / logo.width
    logo_height = int(logo.height * logo_ratio)
    logo_resized = logo.resize((logo_width, logo_height), Image.LANCZOS)

    # Position at bottom-right corner
    pos_x = int(card.width - logo_width - card.width * foil_margin)
    pos_y = int(card.height - logo_height - card.height * foil_margin)

    # Composite onto card (preserves transparency)
    card.alpha_composite(logo_resized, dest=(pos_x, pos_y))

    # Save to memory
    output = io.BytesIO()
    card.save(output, format="PNG")
    output.seek(0)
    return output
    
# -----------------------------
# Telegram Handlers
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to SUIMON card creator! Send me a Suimon meme and I'll generate a unique card for you."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Notify user the card is being generated
    await update.message.reply_text(
        "🎨 Your SUIMON card is being generated! This may take a few minutes..."
    )

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

        keyboard = [
            [InlineKeyboardButton("🎨 Create another SUIMON card", callback_data="create_another")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        caption_text = f"{user_mention} Here’s your SUIMON card! 🃏" if user_mention else "Here’s your SUIMON card! 🃏"

        await update.message.reply_photo(
            photo=final_card_bytes,
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
# FastAPI + PTB
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
