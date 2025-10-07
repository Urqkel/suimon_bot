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

Include all design elements: name, element, HP, rarity, two attacks, flavor text, and themed background/frame.
Leave a clear area at the bottom right corner for an official foil stamp overlay.
Top bar: Name, HP, elemental symbol
Main art: Meme image dynamically styled
Attack boxes: Two attacks with creative names, icons, and power
Footer: Weakness/resistance icons and flavor text above the reserved logo space
Every card should have a vintage yet realistic feel.
Leave a clear area at the bottom right corner for an official foil stamp overlay.
Do NOT add or draw any logo, badge, circle, or placeholder in the bottom-right area. 
Leave that space completely blank — the official SUIMON foil stamp will be added later by the system.
The foil stamp is embossed into the card surface — giving it a realistic 3D texture, as though pressed into the card material, not floating above it.
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

def add_embossed_logo_to_memory(card_image: Image.Image, logo_path=FOIL_STAMP_PATH):
    """
    Adds the official SUIMON foil stamp to the bottom-right corner of the card.
    Includes realistic embossing, metallic tone, and a light reflection streak.
    Returns the composited card as BytesIO.
    """
    from PIL import ImageChops

    # ---- Step 1: Prepare base images ----
    card = card_image.convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    # Circular crop (to ensure perfectly round logo)
    size = min(logo.size)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    logo_cropped = logo.crop((
        (logo.width - size)//2, (logo.height - size)//2,
        (logo.width + size)//2, (logo.height + size)//2
    ))
    logo_cropped.putalpha(mask)

    # ---- Step 2: Resize and positioning ----
    logo_width = int(card.width * 0.14)
    logo_ratio = logo_width / logo_cropped.width
    logo_height = int(logo_cropped.height * logo_ratio)
    logo_resized = logo_cropped.resize((logo_width, logo_height), Image.LANCZOS)

    margin_x = int(card.width * 0.035)
    margin_y = int(card.height * 0.035)
    pos = (card.width - logo_width - margin_x, card.height - logo_height - margin_y)

    # ---- Step 3: Metallic reflection pass ----
    foil_overlay = Image.new("RGBA", logo_resized.size)
    for x in range(logo_resized.width):
        for y in range(logo_resized.height):
            r, g, b, a = logo_resized.getpixel((x, y))
            if a > 0:
                shift = int(30 * (x / logo_resized.width))
                foil_overlay.putpixel(
                    (x, y),
                    (min(255, r + shift), min(255, g + shift), min(255, b + 50), int(a * 0.4))
                )
            else:
                foil_overlay.putpixel((x, y), (0, 0, 0, 0))

    logo_reflective = ImageChops.screen(logo_resized, foil_overlay)
    logo_reflective.putalpha(210)

    # ---- Step 4: Add subtle light streak for realism ----
    glint = Image.new("RGBA", logo_reflective.size, (0, 0, 0, 0))
    glint_draw = ImageDraw.Draw(glint)

    # Diagonal light streak (top-left to bottom-right)
    for i in range(-logo_reflective.width, logo_reflective.width, 4):
        brightness = int(60 - abs(i) * 0.3)
        if brightness > 0:
            glint_draw.line(
                [(i, 0), (i + logo_reflective.height, logo_reflective.height)],
                fill=(255, 255, 255, brightness),
                width=3
            )

    logo_final = ImageChops.screen(logo_reflective, glint)

    # ---- Step 5: Soft embossing for tactile feel ----
    embossed = logo_final.filter(ImageFilter.EMBOSS)
    logo_embossed = Image.blend(logo_final, embossed, 0.35)

    # ---- Step 6: Composite cleanly onto the card ----
    composited = card.copy()
    composited.alpha_composite(logo_embossed, dest=pos)

    # ---- Step 7: Export to memory ----
    output = io.BytesIO()
    composited.save(output, format="PNG")
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
        final_card_bytes = add_embossed_logo_to_memory(card_image, FOIL_STAMP_PATH)

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
