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
from PIL import Image, ImageEnhance, ImageFilter
import openai

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
Leave a clear area at the bottom right corner for a SUIMON logo overlay.
Top bar: Name, HP, elemental symbol
Main art: Meme image dynamically styled
Attack boxes: Two attacks with creative names, icons, and power
Footer: Weakness/resistance icons and flavor text above the reserved logo space
Use foil or holographic effects for Legendary cards.
Every card should have a vintage yet realistic feel.
Do NOT place text or important elements in the reserved bottom area for the logo overlay.
Add the official SUIMON logo subtly **embossed** or **engraved** into the card surface — giving it a realistic 3D texture, as though pressed into the card material, not floating above it.
"""

# -----------------------------
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

def add_holographic_logo(card_image, logo_path="suimon_logo.png"):
    """
    Adds a holographic-style logo to the bottom-right corner of a SUIMON card.
    Returns a BytesIO object containing the final image.
    """
    card = card_image.convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    # Resize logo to ~12% of card width
    logo_width = int(card.width * 0.12)
    logo_ratio = logo_width / logo.width
    logo_height = int(logo.height * logo_ratio)
    logo = logo.resize((logo_width, logo_height), Image.LANCZOS)

    # Create a rainbow-like gradient overlay for hologram effect
    gradient = Image.new("RGBA", logo.size)
    for y in range(logo.height):
        for x in range(logo.width):
            # Generate shifting rainbow colors
            r = int(128 + 127 * ((x + y) % logo.width) / logo.width)
            g = int(128 + 127 * ((y) % logo.height) / logo.height)
            b = int(255 - ((x + y) % 128))
            a = int(200)  # Semi-transparent
            gradient.putpixel((x, y), (r, g, b, a))

    # Combine gradient with logo
    holo_logo = Image.alpha_composite(logo, gradient)

    # Optional: emboss or enhance brightness for depth
    holo_logo = holo_logo.filter(ImageFilter.EMBOSS)
    enhancer = ImageEnhance.Brightness(holo_logo)
    holo_logo = enhancer.enhance(1.3)

    # Position logo bottom-right with margin
    margin_x = int(card.width * 0.05)
    margin_y = int(card.height * 0.03)
    position = (card.width - logo_width - margin_x, card.height - logo_height - margin_y)

    # Overlay holographic logo onto card
    card.alpha_composite(holo_logo, dest=position)

    # Save to memory buffer
    img_bytes = io.BytesIO()
    card.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    return img_bytes
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
        final_card_bytes = add_holographic_logo(card_image, SUIMON_LOGO_PATH)

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
