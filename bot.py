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
        "<b>/help</b> – Show this help message\n\n"
        "📌 <b>Steps:</b>\n"
        "1️⃣ Send photos\n"
        "2️⃣ Use /makepdf to generate PDF\n"
        "3️⃣ Everything resets automatically after PDF\n"
    )
    update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# ---------- Command handlers ----------
def start(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    update.message.reply_text(
        "Welcome! Send me photos and I'll convert them into a single PDF.\n\n"
        "Use /help to see all commands."
    )

def settings(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    s = user_settings[uid]
    update.message.reply_text(
        f"Settings:\n"
        f"filename: {s['name']}.pdf\n"
        f"watermark: {repr(s['watermark_text'])}\n"
        f"watermark_pos: {s['watermark_pos']}\n"
        f"compress_quality: {s['compress_quality']}\n"
        f"pagesize: {s['pagesize']}\n"
        f"saved_photos: {len(user_photos.get(uid, []))}"
    )

def set_name(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    txt = " ".join(context.args) if context.args else None
    if not txt:
        update.message.reply_text("Usage: /name <filename>")
        return
    safe = "".join(c for c in txt if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe:
        update.message.reply_text("Invalid filename")
        return
    user_settings[uid]['name'] = safe
    update.message.reply_text(f"Filename set to: {safe}.pdf")

def set_watermark(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    txt = update.message.text.partition(" ")[2]
    if not txt:
        user_settings[uid]['watermark_text'] = None
        update.message.reply_text("Watermark cleared.")
        return
    txt = txt.replace("\\n", "\n")
    user_settings[uid]['watermark_text'] = txt
    update.message.reply_text("Watermark updated.")

def set_watermark_pos(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    arg = (context.args[0].lower() if context.args else "")
    if arg not in ("br", "center", "tl"):
        update.message.reply_text("Invalid. Use /watermark_pos <br|center|tl>")
        return
    user_settings[uid]['watermark_pos'] = arg
    update.message.reply_text(f"Watermark position set to: {arg}")

def set_compress(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    arg = (context.args[0] if context.args else "")
    try:
        q = int(arg)
        if q < 1 or q > 95:
            raise ValueError()
    except:
        update.message.reply_text("Usage: /compress <1-95>")
        return
    user_settings[uid]['compress_quality'] = q
    update.message.reply_text(f"Quality set to: {q}")

def set_pagesize(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    arg = (context.args[0].upper() if context.args else "")
    if arg not in PAGE_SIZES:
        update.message.reply_text("Invalid pagesize.")
        return
    user_settings[uid]['pagesize'] = arg
    update.message.reply_text(f"Page size set to: {arg}")

def clear(update: Update, context):
    uid = update.message.from_user.id
    for p in user_photos.get(uid, []):
        safe_remove(p)
        safe_remove(p + ".cmp.jpg")
        safe_remove(p + ".wm.jpg")
    user_photos.pop(uid, None)
    user_settings.pop(uid, None)
    update.message.reply_text("Cleared everything.")

def delete_last(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    lst = user_photos.get(uid, [])
    if not lst:
        update.message.reply_text("No photos to delete.")
        return
    last = lst.pop()
    safe_remove(last)
    safe_remove(last + ".cmp.jpg")
    safe_remove(last + ".wm.jpg")
    update.message.reply_text("Last photo deleted.")

def remove_n(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    if not context.args:
        update.message.reply_text("Usage: /remove <num>")
        return
    try:
        idx = int(context.args[0]) - 1
    except:
        update.message.reply_text("Invalid number.")
        return
    lst = user_photos.get(uid, [])
    if idx < 0 or idx >= len(lst):
        update.message.reply_text("Out of range.")
        return
    removed = lst.pop(idx)
    safe_remove(removed)
    safe_remove(removed + ".cmp.jpg")
    safe_remove(removed + ".wm.jpg")
    update.message.reply_text("Photo removed.")

def move_photo(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    if len(context.args) < 2:
        update.message.reply_text("Usage: /move <from> <to>")
        return
    try:
        a = int(context.args[0]) - 1
        b = int(context.args[1]) - 1
    except:
        update.message.reply_text("Invalid numbers.")
        return
    lst = user_photos.get(uid, [])
    if a < 0 or a >= len(lst) or b < 0 or b > len(lst):
        update.message.reply_text("Out of range.")
        return
    item = lst.pop(a)
    lst.insert(b, item)
    update.message.reply_text("Moved.")

def photo_handler(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    photo = update.message.photo[-1]
    try:
        file = context.bot.get_file(photo.file_id)
    except:
        update.message.reply_text("Download failed.")
        return
    img_path = f"{uid}_{photo.file_id}.jpg"
    try:
        file.download(img_path)
        user_photos[uid].append(img_path)
        update.message.reply_text(f"Saved! Total: {len(user_photos[uid])}")
    except:
        safe_remove(img_path)
        update.message.reply_text("Failed to save.")

def preview(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    lst = user_photos.get(uid, [])
    if not lst:
        update.message.reply_text("No photos to preview.")
        return

    batch = 10
    idx = 0
    try:
        while idx < len(lst):
            chunk = lst[idx:idx+batch]
            media = []
            files = []
            for p in chunk:
                try:
                    f = open(p, "rb")
                    files.append(f)
                    media.append(InputMediaPhoto(f))
                except:
                    continue
            if media:
                context.bot.send_media_group(update.message.chat_id, media)
            for f in files:
                try:
                    f.close()
                except:
                    pass
            idx += batch
    except:
        traceback.print_exc()
        update.message.reply_text("Preview failed.")

def makepdf(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)

    photos = list(user_photos.get(uid, []))
    if not photos:
        update.message.reply_text("No photos found.")
        return

    s = user_settings[uid]
    filename = s.get("name", f"{uid}_output")
    watermark_text = s.get("watermark_text")
    watermark_pos = s.get("watermark_pos", "br")
    quality = s.get("compress_quality", DEFAULT_QUALITY)
    pagesize_key = s.get("pagesize", DEFAULT_PAGESIZE).upper()

    update.message.reply_text("Processing your PDF...")

    temp_images = []
    try:
        for orig in photos:
            cmp_path = compress_image(orig, quality)
            wm_path = apply_watermark_to_image(cmp_path, watermark_text, watermark_pos)
            final = wm_path if os.path.exists(wm_path) else cmp_path
            temp_images.append(final)

        page_w_mm, page_h_mm = PAGE_SIZES.get(pagesize_key, PAGE_SIZES["A4"])
        pdf = FPDF(unit="mm", format=(page_w_mm, page_h_mm))

        for img_path in temp_images:
            try:
                im = Image.open(img_path)
                w_px, h_px = im.size
                orientation = "L" if w_px > h_px else "P"
                pdf.add_page(orientation=orientation)

                max_w = page_w_mm - 20
                render_h = (h_px * max_w) / w_px
                y = (page_h_mm - render_h) / 2
                pdf.image(img_path, x=10, y=max(5, y), w=max_w)

                im.close()
            except:
                continue

        out_pdf = f"{filename}.pdf"
        pdf.output(out_pdf, "F")

        update.message.reply_document(open(out_pdf, "rb"))
        update.message.reply_text("Done!")

    except Exception:
        traceback.print_exc()
        update.message.reply_text("PDF failed.")

    finally:
        for p in user_photos.get(uid, []):
            safe_remove(p)
            safe_remove(p + ".cmp.jpg")
            safe_remove(p + ".wm.jpg")

        for t in temp_images:
            safe_remove(t)

        safe_remove(f"{filename}.pdf")

        user_photos[uid] = []
        user_settings[uid] = {
            "name": f"{uid}_output",
            "watermark_text": None,
            "watermark_pos": "br",
            "compress_quality": DEFAULT_QUALITY,
            "pagesize": DEFAULT_PAGESIZE
        }

# ---------- Main ----------
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not set!")
        return

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

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

    dp.add_handler(MessageHandler(Filters.photo, photo_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
