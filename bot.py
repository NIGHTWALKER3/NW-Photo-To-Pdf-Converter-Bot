#!/usr/bin/env python3
import os
import traceback
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import Update, InputMediaPhoto, ParseMode
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

# --------- Runtime storage ----------
user_photos = {}   # user_id -> [filepaths]
user_settings = {} # user_id -> settings dict

# defaults
DEFAULT_QUALITY = 75
MAX_WIDTH = 1600
DEFAULT_PAGESIZE = "A4"

# Supported page sizes (width_mm, height_mm)
PAGE_SIZES = {
    "A3": (297, 420),
    "A4": (210, 297),
    "A5": (148, 210),
    "LETTER": (215.9, 279.4),
    "LEGAL": (215.9, 355.6),
    "TABLOID": (279.4, 431.8)
}

# ---------- Utilities ----------
def ensure_user(uid):
    if uid not in user_photos:
        user_photos[uid] = []
    if uid not in user_settings:
        user_settings[uid] = {
            "name": f"{uid}_output",
            "watermark_text": None,
            "watermark_pos": "br",
            "compress_quality": DEFAULT_QUALITY,
            "pagesize": DEFAULT_PAGESIZE
        }

def safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except:
        pass

def compress_image(input_path, quality):
    try:
        img = Image.open(input_path)
        img = img.convert("RGB")
        w, h = img.size
        if w > MAX_WIDTH:
            new_h = int(h * (MAX_WIDTH / w))
            img = img.resize((MAX_WIDTH, new_h), Image.LANCZOS)
        out_path = input_path + ".cmp.jpg"
        img.save(out_path, "JPEG", quality=int(quality))
        img.close()
        return out_path
    except:
        return input_path

def apply_watermark_to_image(input_path, watermark_text, pos):
    if not watermark_text:
        return input_path
    try:
        img = Image.open(input_path).convert("RGBA")
        w, h = img.size

        overlay = Image.new("RGBA", img.size, (255,255,255,0))
        draw = ImageDraw.Draw(overlay)

        font_size = max(14, w // 20)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except:
            font = ImageFont.load_default()

        lines = watermark_text.split("\n")
        line_heights = [draw.textsize(line, font=font)[1] for line in lines]
        total_h = sum(line_heights) + (len(lines)-1)*4
        max_w = max(draw.textsize(line, font=font)[0] for line in lines)

        margin = int(w * 0.03)

        if pos == "tl":
            x = margin
            y = margin
            for i, line in enumerate(lines):
                draw.text((x, y + i*(font_size+2)), line, fill=(255,255,255,140), font=font)

        elif pos == "br":
            x = w - max_w - margin
            y = h - total_h - margin
            for i, line in enumerate(lines):
                draw.text((x, y + i*(font_size+2)), line, fill=(255,255,255,140), font=font)

        else:  # center
            txt_img = Image.new("RGBA", (max_w + 20, total_h + 10), (255,255,255,0))
            d2 = ImageDraw.Draw(txt_img)
            for i, line in enumerate(lines):
                d2.text((10, i*(font_size+2)), line, fill=(255,255,255,140), font=font)
            rot = txt_img.rotate(45, expand=1)
            rx, ry = rot.size
            px = (w - rx) // 2
            py = (h - ry) // 2
            overlay.paste(rot, (px, py), rot)

        result = Image.alpha_composite(img, overlay).convert("RGB")
        out_path = input_path + ".wm.jpg"
        result.save(out_path, "JPEG", quality=90)
        img.close()
        result.close()
        return out_path
    except:
        return input_path

# ---------- HELP COMMAND ----------
def help_command(update: Update, context):
    help_text = (
        "<b>📘 How to Use This Bot</b>\n\n"
        "<b>/start</b> – Start the bot\n"
        "<b>/makepdf</b> – Convert your uploaded photos into a single PDF\n"
        "<b>/clear</b> – Clear saved photos & reset settings\n"
        "<b>/name &lt;filename&gt;</b> – Set custom PDF name\n"
        "<b>/watermark &lt;text&gt;</b> – Add watermark\n"
        "<b>/watermark_pos &lt;br|center|tl&gt;</b> – Set watermark position\n"
        "<b>/compress &lt;1–95&gt;</b> – Set compression quality\n"
        "<b>/pagesize &lt;A3|A4|A5|Letter|Legal|Tabloid&gt;</b>\n"
        "<b>/preview</b> – Preview uploaded photos\n"
        "<b>/delete_last</b> – Delete latest photo\n"
        "<b>/remove N</b> – Remove Nth photo\n"
        "<b>/move A B</b> – Move photo position\n"
        "<b>/settings</b> – View current settings\n"
        "<b>/feedback &lt;message&gt;</b> – Send feedback or feature request\n"
        "<b>/help</b> – Show this help message\n\n"
        "📌 <b>Steps:</b>\n"
        "1️⃣ Send photos\n"
        "2️⃣ Use /makepdf to generate PDF\n"
        "3️⃣ Everything resets automatically after PDF\n"
    )
    update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# ---------- FEEDBACK COMMAND ----------
def feedback(update: Update, context):
    """Send feedback or feature request directly to your Telegram account."""
    FEEDBACK_ID = os.getenv("FEEDBACK_ID")
    if not FEEDBACK_ID:
        update.message.reply_text("Feedback feature not configured.")
        return

    msg = " ".join(context.args) if context.args else None
    if not msg:
        update.message.reply_text("Usage: /feedback <your message>")
        return

    try:
        context.bot.send_message(
            chat_id=int(FEEDBACK_ID),
            text=f"Feedback from @{update.message.from_user.username} ({update.message.from_user.id}):\n{msg}"
        )
        update.message.reply_text("✅ Thank you! Your feedback has been sent.")
    except Exception as e:
        update.message.reply_text("❌ Failed to send feedback.")
        print(e)

# ---------- Existing bot command handlers (start, settings, name, watermark, etc.) ----------
# Keep all your existing handlers (start, settings, set_name, set_watermark, set_watermark_pos, set_compress, set_pagesize, clear, delete_last, remove_n, move_photo, photo_handler, preview, makepdf) here exactly as they are

# ---------- Main ----------
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not set!")
        return

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Core commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("settings", settings))
    dp.add_handler(CommandHandler("name", set_name))
    dp.add_handler(CommandHandler("watermark", set_watermark))
    dp.add_handler(CommandHandler("watermark_pos", set_watermark_pos))
    dp.add_handler(CommandHandler("compress", set_compress))
    dp.add_handler(CommandHandler("pagesize", set_pagesize))
    dp.add_handler(CommandHandler("makepdf", makepdf))
    dp.add_handler(CommandHandler("clear", clear))

    dp.add_handler(CommandHandler("delete_last", delete_last))
    dp.add_handler(CommandHandler("remove", remove_n, pass_args=True))
    dp.add_handler(CommandHandler("move", move_photo, pass_args=True))
    dp.add_handler(CommandHandler("preview", preview))
    
    # Feedback command
    dp.add_handler(CommandHandler("feedback", feedback, pass_args=True))

    # Photo handler
    dp.add_handler(MessageHandler(Filters.photo, photo_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
