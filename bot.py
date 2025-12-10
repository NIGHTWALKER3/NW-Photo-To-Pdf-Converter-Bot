import os
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFont
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
from telegram import ParseMode

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
    except:
        return in_path


# -------------------------------
# WATERMARK
# -------------------------------
def apply_watermark(img_path, text, position="br"):
    if not text:
        return img_path

    try:
        img = Image.open(img_path).convert("RGBA")
        watermark = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark)
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
        else:
            x = margin
            y = margin

        draw.text((x, y), text, fill=(255, 255, 255, 180), font=font)
        combined = Image.alpha_composite(img, watermark)

        out_path = img_path + ".wm.jpg"
        combined.convert("RGB").save(out_path, "JPEG")
        return out_path

    except:
        return img_path


# -------------------------------
# START
# -------------------------------
def start(update, context):
    uid = update.effective_user.id

    user_settings[uid] = {
        "name": f"{uid}_output",
        "watermark_text": None,
        "watermark_pos": "br",
        "compress_quality": DEFAULT_QUALITY,
        "pagesize": DEFAULT_PAGESIZE
    }

    update.message.reply_text("👋 Welcome! Send photos & use /makepdf.")


# -------------------------------
# CLEAR
# -------------------------------
def clear(update, context):
    uid = update.effective_user.id
    photos = user_photos.get(uid, [])

    for p in photos:
        safe_remove(p)
        safe_remove(p + ".cmp.jpg")
        safe_remove(p + ".wm.jpg")

    user_photos[uid] = []
    update.message.reply_text("🧹 Photos cleared.")


# -------------------------------
# NAME
# -------------------------------
def set_name(update, context):
    uid = update.effective_user.id
    if not context.args:
        update.message.reply_text("Usage: /name filename")
        return

    user_settings[uid]["name"] = "_".join(context.args)
    update.message.reply_text(f"📄 Filename set to: {user_settings[uid]['name']}")


# -------------------------------
# WATERMARK & POSITION
# -------------------------------
def set_watermark(update, context):
    uid = update.effective_user.id
    if not context.args:
        update.message.reply_text("Usage: /watermark text")
        return

    user_settings[uid]["watermark_text"] = " ".join(context.args)
    update.message.reply_text("💧 Watermark updated!")


def set_watermark_pos(update, context):
    uid = update.effective_user.id
    if not context.args or context.args[0] not in ["tl", "tr", "bl", "br"]:
        update.message.reply_text("Usage: /watermark_pos tl/tr/bl/br")
        return

    user_settings[uid]["watermark_pos"] = context.args[0]
    update.message.reply_text("📌 Watermark position updated!")


# -------------------------------
# COMPRESSION
# -------------------------------
def compress(update, context):
    uid = update.effective_user.id
    if not context.args:
        update.message.reply_text("Usage: /compress 10-100")
        return

    try:
        q = int(context.args[0])
        if q < 10 or q > 100:
            raise ValueError
    except:
        update.message.reply_text("Enter a value between 10–100.")
        return

    user_settings[uid]["compress_quality"] = q
    update.message.reply_text(f"📦 Compression set to {q}")


# -------------------------------
# SETTINGS
# -------------------------------
def settings(update, context):
    uid = update.effective_user.id
    s = user_settings[uid]

    msg = (
        f"⚙️ **Your Settings**\n"
        f"Filename: {s['name']}\n"
        f"Watermark: {s['watermark_text']}\n"
        f"Position: {s['watermark_pos']}\n"
        f"Quality: {s['compress_quality']}\n"
    )
    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# -------------------------------
# SAVE PHOTO
# -------------------------------
def save_photo(update, context):
    uid = update.effective_user.id
    user_photos.setdefault(uid, [])

    file_id = update.message.photo[-1].file_id
    file = context.bot.get_file(file_id)

    filename = f"{uid}_{uuid4()}.jpg"
    file.download(filename)

    user_photos[uid].append(filename)
    update.message.reply_text("📸 Photo saved!")


# -------------------------------
# CREATE PDF
# -------------------------------
def makepdf(update, context):
    uid = update.effective_user.id
    photos = user_photos.get(uid, [])

    if not photos:
        update.message.reply_text("❌ No photos found.")
        return

    s = user_settings[uid]
    final_pages = []

    try:
        for p in photos:
            processed = compress_image(p, s["compress_quality"])
            processed = apply_watermark(processed, s["watermark_text"], s["watermark_pos"])
            final_pages.append(processed)

        images = [Image.open(x).convert("RGB") for x in final_pages]

        pdf_name = f"{s['name']}.pdf"
        images[0].save(pdf_name, save_all=True, append_images=images[1:])

        update.message.reply_document(open(pdf_name, "rb"))
        update.message.reply_text("✅ PDF created!")

    except Exception as e:
        update.message.reply_text("❌ Error creating PDF.")
        print(e)

    finally:
        for p in photos:
            safe_remove(p)
            safe_remove(p + ".cmp.jpg")
            safe_remove(p + ".wm.jpg")

        safe_remove(pdf_name)

        # FULL AUTO RESET AFTER PDF
        user_photos[uid] = []
        user_settings[uid] = {
            "name": f"{uid}_output",
            "watermark_text": None,
            "watermark_pos": "br",
            "compress_quality": DEFAULT_QUALITY,
            "pagesize": DEFAULT_PAGESIZE
        }


# -------------------------------
# BOT RUN
# -------------------------------
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("clear", clear))
    dp.add_handler(CommandHandler("makepdf", makepdf))
    dp.add_handler(CommandHandler("name", set_name))
    dp.add_handler(CommandHandler("watermark", set_watermark))
    dp.add_handler(CommandHandler("watermark_pos", set_watermark_pos))
    dp.add_handler(CommandHandler("compress", compress))
    dp.add_handler(CommandHandler("settings", settings))

    dp.add_handler(MessageHandler(Filters.photo, save_photo))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
