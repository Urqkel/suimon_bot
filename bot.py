import os
import io, math, random
import base64
import pytesseract
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
- Top bar: Place the character name on the left, and always render “HP” followed by the number (e.g. HP100) on the right side.
  The HP text must be completely visible, never cropped, never stylized, and always use a clean card font.
  Place the elemental icon beside the HP number, leaving at least 15% horizontal spacing so they do not touch or overlap.
- Main art: Use the uploaded meme image as the character art, dynamically styled without changing the underlying character in the meme (remove or ignore the word SUIMON if present in the uploaded image). 
- Attack boxes: Include two creative attacks with names, icons, and damage numbers.
- Flavor text: Include EXACTLY ONE short, unique line beneath the attacks (no repetition or duplication).
- Footer: Weakness/resistance icons should be on the left. Leave a clear empty area in the bottom-right corner for an official foil stamp.
- The foil stamp area must stay completely blank — do not draw or add any art or borders there.
- The foil stamp is a subtle circular authenticity mark that will be imprinted later.
- Overall aesthetic: vintage, realistic, collectible, with slight texture and warmth, but without altering any provided logos.
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
    Places the official foil stamp into the card.
    FOIL_SCALE, FOIL_X_OFFSET, FOIL_Y_OFFSET can be set via environment variables.
    """
    card = card_image.convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    # Read env vars or fallback to defaults
    foil_scale = float(os.getenv("FOIL_SCALE", 0.13))
    foil_x_offset = float(os.getenv("FOIL_X_OFFSET", 0.0))  # horizontal adjustment (fraction of width)
    foil_y_offset = float(os.getenv("FOIL_Y_OFFSET", 0.0))  # vertical adjustment (fraction of height)

    # Resize logo
    logo_width = int(card.width * foil_scale)
    ratio = logo_width / logo.width
    logo_height = int(logo.height * ratio)
    logo_resized = logo.resize((logo_width, logo_height), Image.LANCZOS)

    # Compute final position relative to bottom-right corner
    pos_x = int(card.width - logo_width + card.width * foil_x_offset)
    pos_y = int(card.height - logo_height + card.height * foil_y_offset)

    # Composite the logo
    card.alpha_composite(logo_resized, dest=(pos_x, pos_y))

    output = io.BytesIO()
    card.save(output, format="PNG")
    output.seek(0)
    return output

def check_hp_visibility(card_image: Image.Image):
    """
    Runs OCR on the generated card to confirm that 'HP' appears visibly.
    Returns True if 'HP' is found, otherwise False.
    """
    try:
        text = pytesseract.image_to_string(card_image)
        return "HP" in text.upper()
    except Exception:
        return False

def check_flavor_text(card_image: Image.Image):
    """
    Uses OCR to detect and analyze flavor text lines at the bottom of the card.
    Returns True if flavor text appears only once (no duplicates), False otherwise.
    """
    try:
        text = pytesseract.image_to_string(card_image)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        # Find likely flavor text lines (short sentences, not labels like 'Weakness')
        flavor_candidates = [ln for ln in lines if 5 < len(ln) < 80 and "weak" not in ln.lower() and "resist" not in ln.lower()]
        # Remove exact duplicates
        unique_lines = list(dict.fromkeys(flavor_candidates))
        # If duplicates exist, return False
        return len(flavor_candidates) == len(unique_lines)
    except Exception:
        return True  # Fallback to pass silently if OCR fails


# -----------------------------
# Telegram Handlers
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to SUIMON card creator! Use /generate to start creating a SUIMON card 🃏"
    )

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /generate command: allows this user to generate one card.
    """
    context.user_data["can_generate"] = True
    await update.message.reply_text(
        "Send me a meme image, and I’ll craft a unique SUIMON card for you 🃏"
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Only generates a card if this user previously triggered /generate or clicked 'Create another'.
    """
    if not context.user_data.get("can_generate", False):
        await update.message.reply_text(
            "⚠️ Please use /generate or click 'Create another SUIMON card' before sending an image."
        )
        return

    # Reset flag so next image requires a new trigger
    context.user_data["can_generate"] = False

    await update.message.reply_text("🎨 Generating your SUIMON card... please wait a moment!")

    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    meme_bytes_io = io.BytesIO()
    await photo_file.download_to_memory(out=meme_bytes_io)
    meme_bytes_io.seek(0)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        card_image = generate_suimon_card(meme_bytes_io, PROMPT_TEMPLATE)

        # 🩺 Quality checks
        hp_ok = check_hp_visibility(card_image)
        flavor_ok = check_flavor_text(card_image)

        if not hp_ok:
            print("⚠️ Warning: HP text not detected on generated card.")
        if not flavor_ok:
            print("⚠️ Warning: Duplicate flavor text detected on generated card.")

        final_card_bytes = add_foil_stamp(card_image, FOIL_STAMP_PATH)

        keyboard = [[InlineKeyboardButton("🎨 Create another SUIMON card", callback_data="create_another")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        caption = f"Here’s your SUIMON card! 🃏"

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
        # Only allow this user to generate another card
        context.user_data["can_generate"] = True
        await query.message.reply_text(
            "Awesome! Send me a new meme image, and I'll make another SUIMON card for you."
        )

# -----------------------------
# Register Handlers
# -----------------------------
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("generate", generate))
ptb_app.add_handler(MessageHandler(filters.PHOTO, handle_image))
ptb_app.add_handler(CallbackQueryHandler(button_callback))

# -----------------------------
# FastAPI + PTB Integration
# -----------------------------
fastapi_app = FastAPI()
ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()

# -----------------------------
# Register handlers AFTER ptb_app is created
# -----------------------------
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("generate", generate))
ptb_app.add_handler(MessageHandler(filters.PHOTO, handle_image))
ptb_app.add_handler(CallbackQueryHandler(button_callback))

# -----------------------------
# Startup event
# -----------------------------
@fastapi_app.on_event("startup")
async def startup_event():
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(WEBHOOK_URL)

# -----------------------------
# Webhook endpoint
# -----------------------------
@fastapi_app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.update_queue.put(update)
    return {"ok": True}
