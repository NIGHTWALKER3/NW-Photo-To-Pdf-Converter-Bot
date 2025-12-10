import os
import logging
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------
# GLOBAL STORAGE
# -------------------------------
user_photos = {}
user_settings = {}

DEFAULT_QUALITY = 85
DEFAULT_PAGESIZE = "A4"


# -------------------------------
# SAFE REMOVE
# -------------------------------
def safe_remove(f):
    try:
        if f and os.path.isfile(f):
            os.remove(f)
    except:
        pass


# -------------------------------
# COMPRESSION
# -------------------------------
def compress_image(in_path, quality=85):
    out_path = in_path + ".cmp.jpg"
    try:
        img = Image.open(in_path)
        img.save(out_path, "JPEG", optimize=True, quality=quality)
        return out_path
    except Exception as e:
        logger.error(f"Compress error: {e}")
        return None


# -------------------------------
# WATERMARK
# -------------------------------
def apply_watermark(img_path, text, position="br"):
    if not text:
        return img_path

    try:
        img = Image.open(img_path).convert("RGBA")
        watermark_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark_layer)

        font = ImageFont.load_default()
        text_w, text_h = draw.textsize(text, font)

        margin = 20
        if position == "br":
            x = img.width - text_w - margin
            y = img.height - text_h - margin
        elif position == "bl":
            x = margin
            y = img.height - text_h - margin
        elif position == "tr":
            x = img.width - text_w - margin
            y = margin
        else:  # tl
            x = margin
            y = margin

        draw.text((x, y), text, font=font, fill=(255, 255, 255, 180))
        combined = Image.alpha_composite(img, watermark_layer)

        out_path = img_path + ".wm.jpg"
        combined.convert("RGB").save(out_path, "JPEG")
        return out_path

    except Exception as e:
        logger.error(f"Watermark error: {e}")
        return None


# -------------------------------
# HANDLERS
# -------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Initialize user settings
    user_settings.setdefault(uid, {
        "name": f"{uid}_output",
        "watermark_text": None,
        "watermark_pos": "br",
        "compress_quality": DEFAULT_QUALITY,
        "pagesize": DEFAULT_PAGESIZE
    })

    await update.message.reply_text(
        "👋 Welcome!\nSend photos & use /makepdf when done."
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    count = len(user_photos.get(uid, []))

    # Delete stored files
    for p in user_photos.get(uid, []):
        safe_remove(p)
        safe_remove(p + ".cm.jpg")
        safe_remove(p + ".wm.jpg")

    user_photos[uid] = []

    await update.message.reply_text(f"🧹 Cleared {count} photos.")


async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Usage: /name filename")
        return

    new_name = "_".join(context.args)
    user_settings.setdefault(uid, {})
    user_settings[uid]["name"] = new_name

    await update.message.reply_text(f"📄 PDF filename set to: {new_name}")


async def set_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Usage: /watermark text_here")
        return

    wm_text = " ".join(context.args)
    user_settings.setdefault(uid, {})
    user_settings[uid]["watermark_text"] = wm_text

    await update.message.reply_text(f"💧 Watermark set to: {wm_text}")


async def set_watermark_pos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not context.args or context.args[0] not in ["tl", "tr", "bl", "br"]:
        await update.message.reply_text("Usage: /watermark_pos tl/tr/bl/br")
        return

    pos = context.args[0]
    user_settings.setdefault(uid, {})
    user_settings[uid]["watermark_pos"] = pos

    await update.message.reply_text(f"📌 Watermark position set to: {pos}")


async def compress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Usage: /compress 10-100")
        return

    try:
        q = int(context.args[0])
        if q < 10 or q > 100:
            raise ValueError
    except:
        await update.message.reply_text("❌ Enter number 10–100")
        return

    user_settings.setdefault(uid, {})
    user_settings[uid]["compress_quality"] = q

    await update.message.reply_text(f"📦 Compression set to {q}")


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = user_settings.get(uid, {})

    await update.message.reply_text(
        f"⚙ **Your Settings**\n"
        f"Filename: {s['name']}\n"
        f"Watermark: {s['watermark_text']}\n"
        f"Position: {s['watermark_pos']}\n"
        f"Quality: {s['compress_quality']}\n"
        f"Page size: {s['pagesize']}"
    )


# -------------------------------
# PHOTO UPLOAD
# -------------------------------
async def save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_photos.setdefault(uid, [])

    photo = update.message.photo[-1]
    f_id = photo.file_id
    new_path = f"{uid}_{uuid4()}.jpg"

    file = await context.bot.get_file(f_id)
    await file.download_to_drive(new_path)

    user_photos[uid].append(new_path)
    await update.message.reply_text("📸 Photo saved!")


# -------------------------------
# MAKE PDF
# -------------------------------
async def makepdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    photos = user_photos.get(uid, [])

    if not photos:
        await update.message.reply_text("❌ No photos found.")
        return

    s = user_settings[uid]
    compress_q = s["compress_quality"]
    wm_text = s["watermark_text"]
    wm_pos = s["watermark_pos"]
    filename = s["name"]

    temp_pages = []

    try:
        for p in photos:
            processed = p

            # Compress
            processed = compress_image(processed, compress_q)

            # Watermark
            processed = apply_watermark(processed, wm_text, wm_pos)

            temp_pages.append(processed)

        # Convert to PDF
        images = [Image.open(x).convert("RGB") for x in temp_pages]
        pdf_path = f"{filename}.pdf"

        images[0].save(pdf_path, save_all=True, append_images=images[1:])

        await update.message.reply_document(open(pdf_path, "rb"))
        await update.message.reply_text("✅ PDF Created!")

    except Exception as e:
        logger.error(str(e))
        await update.message.reply_text("❌ Error creating PDF.")

    finally:
        # Remove temp images
        for p in photos:
            safe_remove(p)
            safe_remove(p + ".cmp.jpg")
            safe_remove(p + ".wm.jpg")

        for t in temp_pages:
            safe_remove(t)

        safe_remove(f"{filename}.pdf")

        # RESET USER DATA AFTER PDF
        user_photos[uid] = []
        user_settings[uid] = {
            "name": f"{uid}_output",
            "watermark_text": None,
            "watermark_pos": "br",
            "compress_quality": DEFAULT_QUALITY,
            "pagesize": DEFAULT_PAGESIZE
        }


# -------------------------------
# MAIN
# -------------------------------
async def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("makepdf", makepdf))
    app.add_handler(CommandHandler("name", set_name))
    app.add_handler(CommandHandler("watermark", set_watermark))
    app.add_handler(CommandHandler("watermark_pos", set_watermark_pos))
    app.add_handler(CommandHandler("compress", compress))
    app.add_handler(CommandHandler("settings", settings))

    app.add_handler(MessageHandler(filters.PHOTO, save_photo))

    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
