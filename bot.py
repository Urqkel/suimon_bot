import os
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from PIL import Image
import io
import openai
import base64

# -----------------------------
# Configuration
# -----------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUIMON_LOGO_PATH = "assets/suimon_logo.png"  # Path in repo
WEBHOOK_URL = "https://suimon-bot.onrender.com/telegram_webhook"  # Your Render domain
PORT = int(os.environ.get("PORT", 10000))

# OpenAI API key
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
    """Generate a SUIMON card from meme image bytes."""
    response = openai.images.generate(
        model="gpt-image-1",
        prompt=prompt_text,
        image=meme_bytes_io,
        size="1024x1024"
    )
    card_data = response.data[0].b64_json
    card_image = Image.open(io.BytesIO(base64.b64decode(card_data)))
    return card_image

def add_logo_to_card(card_image, logo_path, scale=0.18, padding=25):
    """Overlay SUIMON logo on the card."""
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
# Telegram bot handlers
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to SUIMON! Send me a meme image and I'll generate a SUIMON card for you."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user-uploaded images with typing indicator and card generation."""
    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    
    meme_bytes_io = io.BytesIO()
    await photo_file.download_to_memory(out=meme_bytes_io)
    meme_bytes_io.seek(0)

    # Show "typing" while generating
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        card_image = generate_suimon_card(meme_bytes_io, PROMPT_TEMPLATE)
        final_card = add_logo_to_card(card_image, SUIMON_LOGO_PATH)

        # Show "uploading photo"
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")

        output_bytes = io.BytesIO()
        final_card.save(output_bytes, format="PNG")
        output_bytes.seek(0)
        await update.message.reply_photo(photo=output_bytes, caption="Here’s your SUIMON card! 🃏")

    except Exception as e:
        await update.message.reply_text(f"Sorry, something went wrong: {e}")

# -----------------------------
# Webhook setup helper
# -----------------------------
def setup_webhook():
    """Deletes old webhook and sets the correct webhook URL."""
    bot = Bot(token=BOT_TOKEN)
    bot.delete_webhook()
    bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook set to {WEBHOOK_URL}")

# -----------------------------
# Main bot setup
# -----------------------------
def main():
    setup_webhook()  # Ensure webhook is correct

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("SUIMON bot running with webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()
