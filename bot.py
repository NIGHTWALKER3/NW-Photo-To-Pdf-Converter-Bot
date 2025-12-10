#!/usr/bin/env python3
import os
import io
import traceback
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import Update
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

# ---------- per-user runtime storage ----------
user_photos = {}           # user_id -> list of image file paths
user_settings = {}         # user_id -> dict: {name, watermark_text, watermark_pos, compress_quality}

# defaults
DEFAULT_QUALITY = 75
MAX_WIDTH = 1280  # resize images to this width (if wider)

# ---------- utility functions ----------
def ensure_user(user_id):
    if user_id not in user_photos:
        user_photos[user_id] = []
    if user_id not in user_settings:
        user_settings[user_id] = {
            "name": f"{user_id}_output",      # default filename (without .pdf)
            "watermark_text": None,
            "watermark_pos": "br",           # 'br' (bottom-right), 'center', 'tl'
            "compress_quality": DEFAULT_QUALITY
        }

def safe_remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def compress_image(input_path, quality):
    """
    Compress and resize image using Pillow.
    Returns path to new temporary image.
    """
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
    except Exception:
        # if compression fails, fallback to original
        return input_path

def apply_watermark_to_image(input_path, watermark_text, pos):
    """
    Apply watermark text to the image and return path to the watermarked temp image.
    pos: 'br' | 'center' | 'tl'
    """
    if not watermark_text:
        return input_path

    try:
        img = Image.open(input_path).convert("RGBA")
        w, h = img.size

        # Create transparent overlay
        txt = Image.new("RGBA", img.size, (255,255,255,0))
        draw = ImageDraw.Draw(txt)

        # Choose font size relative to image width
        font_size = max(14, w // 20)
        try:
            # try common ttf - may not exist in runner
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        # split text to fit if needed
        lines = watermark_text.split("\\n")
        # measure total text block size
        line_sizes = [draw.textsize(line, font=font) for line in lines]
        text_w = max(sz[0] for sz in line_sizes)
        text_h = sum(sz[1] for sz in line_sizes) + (len(lines)-1)*4

        margin = int(w * 0.03)

        if pos == "br":
            x = w - text_w - margin
            y = h - text_h - margin
            for i, line in enumerate(lines):
                draw.text((x, y + i*(font_size+2)), line, fill=(255,255,255,120), font=font)
        elif pos == "tl":
            x = margin
            y = margin
            for i, line in enumerate(lines):
                draw.text((x, y + i*(font_size+2)), line, fill=(255,255,255,120), font=font)
        else:  # center diagonal
            # place text centered, rotated
            # build a text image
            txt_img = Image.new("RGBA", (text_w + 20, text_h + 10), (255,255,255,0))
            d2 = ImageDraw.Draw(txt_img)
            for i, line in enumerate(lines):
                d2.text((10, i*(font_size+2)), line, fill=(255,255,255,120), font=font)
            # rotate
            rot = txt_img.rotate(45, expand=1)
            # compute center
            rx, ry = rot.size
            px = (w - rx) // 2
            py = (h - ry) // 2
            txt.paste(rot, (px, py), rot)

        # Composite and save
        watermarked = Image.alpha_composite(img, txt).convert("RGB")
        out_path = input_path + ".wm.jpg"
        watermarked.save(out_path, "JPEG", quality=90)
        img.close()
        watermarked.close()
        return out_path
    except Exception:
        return input_path

# ---------- command handlers ----------
def start(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    update.message.reply_text(
        "Welcome! Send me photos and I'll convert them into a single PDF.\n"
        "Commands:\n"
        "/makepdf - combine photos into PDF\n"
        "/clear - clear saved photos\n"
        "/name <filename> - set output PDF filename (without .pdf)\n"
        "/watermark <text> - set your watermark text (use \\n for new line)\n"
        "/watermark_pos <br|center|tl> - set watermark position (bottom-right, center-diagonal, top-left)\n"
        "/compress <quality> - set JPEG quality (1-95), default 75\n"
        "/settings - show current settings\n    "
    )

def settings(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    s = user_settings[uid]
    update.message.reply_text(
        f"Settings:\n"
        f"filename: {s['name']}\n"
        f"watermark: {repr(s['watermark_text'])}\n"
        f"watermark_pos: {s['watermark_pos']}\n"
        f"compress_quality: {s['compress_quality']}\n"
        f"saved_photos: {len(user_photos.get(uid, []))}"
    )

def set_name(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    txt = " ".join(context.args) if context.args else None
    if not txt:
        update.message.reply_text("Usage: /name <filename>  (without .pdf)")
        return
    safe = "".join(c for c in txt if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe:
        update.message.reply_text("Filename invalid. Use letters, numbers, space, - or _")
        return
    user_settings[uid]["name"] = safe
    update.message.reply_text(f"Filename set to: {safe}.pdf")

def set_watermark(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    txt = update.message.text.partition(" ")[2]
    if not txt:
        user_settings[uid]["watermark_text"] = None
        update.message.reply_text("Watermark cleared. No watermark will be used.")
        return
    # allow \n in command by replacing literal \n with newline if user typed that
    txt = txt.replace("\\n", "\n")
    user_settings[uid]["watermark_text"] = txt
    update.message.reply_text(f"Watermark set. Current position: {user_settings[uid]['watermark_pos']}")

def set_watermark_pos(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    arg = (context.args[0].lower() if context.args else "").strip()
    if arg not in ("br", "center", "tl"):
        update.message.reply_text("Usage: /watermark_pos <br|center|tl>\nbr=bottom-right, center=center-diagonal, tl=top-left")
        return
    user_settings[uid]["watermark_pos"] = arg
    update.message.reply_text(f"Watermark position set to: {arg}")

def set_compress(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    arg = (context.args[0] if context.args else "")
    try:
        q = int(arg)
        if q < 1 or q > 95:
            raise ValueError()
    except Exception:
        update.message.reply_text("Usage: /compress <quality>\nProvide integer 1-95 (default 75).")
        return
    user_settings[uid]["compress_quality"] = q
    update.message.reply_text(f"Compression quality set to: {q}")

def clear(update: Update, context):
    uid = update.message.from_user.id
    user_photos.pop(uid, None)
    user_settings.pop(uid, None)
    update.message.reply_text("Your saved photos and settings have been cleared.")

def photo_handler(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    photo = update.message.photo[-1]
    try:
        file = context.bot.get_file(photo.file_id)
    except Exception:
        update.message.reply_text("Failed to download photo.")
        return

    img_path = f"{uid}_{photo.file_id}.jpg"
    try:
        file.download(img_path)
        user_photos[uid].append(img_path)
        update.message.reply_text(f"Photo saved! Total photos: {len(user_photos[uid])}")
    except Exception:
        safe_remove(img_path)
        update.message.reply_text("Failed to save photo.")

def makepdf(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    photos = list(user_photos.get(uid, []))
    if not photos:
        update.message.reply_text("No photos found. Send photos first.")
        return

    settings = user_settings[uid]
    filename = settings.get("name", f"{uid}_output")
    watermark_text = settings.get("watermark_text")
    watermark_pos = settings.get("watermark_pos", "br")
    quality = settings.get("compress_quality", DEFAULT_QUALITY)

    update.message.reply_text("Processing your PDF... ⏳ This may take a few seconds.")

    temp_images = []
    try:
        # compress and apply watermark per image, store temp paths
        for p in photos:
            cmp = compress_image(p, quality)
            wm = apply_watermark_to_image(cmp, watermark_text, watermark_pos)
            # if compress created a new file, keep for cleanup
            temp_images.append(wm)
            # if compression produced a separate file, track that too for cleanup
            if cmp != p and cmp not in temp_images:
                temp_images.append(cmp)

        # create PDF with FPDF
        pdf_path = f"{filename}.pdf"
        pdf = FPDF()
        for img_path in photos:
            # use the processed version
            proc = img_path + ".cmp.jpg" if (img_path + ".cmp.jpg") in temp_images else img_path
            proc = proc + ".wm.jpg" if (proc + ".wm.jpg") in temp_images else proc
            # As a safe fallback, loop through temp_images and pick the one that startswith original id
            chosen = None
            for t in temp_images:
                if t.startswith(str(uid)) and t.endswith(".wm.jpg") and t.startswith(os.path.splitext(img_path)[0]):
                    chosen = t
                    break
            if chosen is None:
                # fallback: choose proc path if exists else original
                chosen = proc if os.path.exists(proc) else img_path

            # Add page sized to image
            try:
                im = Image.open(chosen)
                w_px, h_px = im.size
                # Convert pixels to mm for FPDF (assuming 96 dpi)
                # Use a simpler approach: fit image width to 190mm page width with aspect ratio
                page_w_mm = 190.0
                # compute width/height mm roughly
                pdf_w = page_w_mm
                pdf_h = (h_px * page_w_mm) / w_px
                pdf.add_page()
                # Save a copy scaled for FPDF use (FPDF.image expects a file)
                # We'll just pass the file and let fpdf scale by width
                pdf.image(chosen, x=10, y=10, w=190)
                im.close()
            except Exception:
                # if image open fails, skip
                continue

        pdf.output(pdf_path, "F")

        # send PDF
        update.message.reply_document(open(pdf_path, "rb"))
    except Exception as e:
        traceback.print_exc()
        update.message.reply_text("Failed to create PDF. Error occurred.")
    finally:
        # cleanup: remove original and temp images and pdf
        for p in user_photos.get(uid, []):
            safe_remove(p)
            safe_remove(p + ".cmp.jpg")
            safe_remove(p + ".wm.jpg")
        safe_remove(filename + ".pdf")
        # reset user's photo list
        user_photos[uid] = []

# ---------- main ----------
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not set in environment!")
        return

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("settings", settings))
    dp.add_handler(CommandHandler("name", set_name))
    dp.add_handler(CommandHandler("watermark", set_watermark))
    dp.add_handler(CommandHandler("watermark_pos", set_watermark_pos))
    dp.add_handler(CommandHandler("compress", set_compress))
    dp.add_handler(CommandHandler("makepdf", makepdf))
    dp.add_handler(CommandHandler("clear", clear))
    dp.add_handler(MessageHandler(Filters.photo, photo_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

#By NIGHTWALKER 
