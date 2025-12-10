#!/usr/bin/env python3
import os
import traceback
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import Update, InputMediaPhoto
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

# --------- Runtime storage ----------
user_photos = {}   # user_id -> [filepaths]
user_settings = {} # user_id -> settings dict

# defaults
DEFAULT_QUALITY = 75
MAX_WIDTH = 1600  # px - resize images wider than this
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
            "watermark_pos": "br",  # br, center, tl
            "compress_quality": DEFAULT_QUALITY,
            "pagesize": DEFAULT_PAGESIZE
        }

def safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def compress_image(input_path, quality):
    """Resize if wide and save as JPEG with given quality. Returns new path (or original on failure)."""
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
        return input_path

def apply_watermark_to_image(input_path, watermark_text, pos):
    """Apply watermark_text to image (pos: br, center, tl). Returns new path (or original)."""
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
        except Exception:
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
        else:  # center diagonal
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
    except Exception:
        return input_path

# ---------- Command handlers ----------
def start(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    update.message.reply_text(
        "Welcome! Send me photos and I'll convert them into a single PDF.\n\n"
        "Main commands:\n"
        "/makepdf - Combine saved photos into PDF\n"
        "/clear - Clear saved photos & settings\n"
        "/name <filename> - set output filename (no .pdf)\n"
        "/watermark <text> - set watermark (use \\n for new lines)\n"
        "/watermark_pos <br|center|tl> - watermark position\n"
        "/compress <quality> - JPEG quality 1-95\n"
        "/pagesize <A3|A4|A5|Letter|Legal|Tabloid> - choose page size (default A4)\n"
        "/preview - preview saved photos\n"
        "/delete_last - delete last added photo\n"
        "/remove <num> - remove specific photo (1-based)\n"
        "/move <from> <to> - move photo position\n"
        "/settings - view current settings"
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
        update.message.reply_text("Usage: /name <filename> (without .pdf)")
        return
    safe = "".join(c for c in txt if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe:
        update.message.reply_text("Filename invalid. Use letters, numbers, space, - or _")
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
    update.message.reply_text(f"Watermark set. Use /watermark_pos to change position (current {user_settings[uid]['watermark_pos']}).")

def set_watermark_pos(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    arg = (context.args[0].lower() if context.args else "")
    if arg not in ("br", "center", "tl"):
        update.message.reply_text("Usage: /watermark_pos <br|center|tl>\nbr=bottom-right, center=center-diagonal, tl=top-left")
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
    except Exception:
        update.message.reply_text("Usage: /compress <quality>  (1-95)")
        return
    user_settings[uid]['compress_quality'] = q
    update.message.reply_text(f"Compression quality set to: {q}")

def set_pagesize(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    arg = (context.args[0].upper() if context.args else "")
    if arg not in PAGE_SIZES:
        update.message.reply_text("Usage: /pagesize <A3|A4|A5|Letter|Legal|Tabloid>\nDefault is A4.")
        return
    user_settings[uid]['pagesize'] = arg
    update.message.reply_text(f"Page size set to: {arg}")

def clear(update: Update, context):
    uid = update.message.from_user.id
    # remove files
    for p in user_photos.get(uid, []):
        safe_remove(p)
        safe_remove(p + ".cmp.jpg")
        safe_remove(p + ".wm.jpg")
    user_photos.pop(uid, None)
    user_settings.pop(uid, None)
    update.message.reply_text("Cleared your photos and settings.")

# Photo management commands
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
    update.message.reply_text(f"Deleted last photo. Remaining: {len(lst)}")

def remove_n(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    args = context.args
    if not args:
        update.message.reply_text("Usage: /remove <number>  (1-based index)")
        return
    try:
        idx = int(args[0]) - 1
    except Exception:
        update.message.reply_text("Invalid number.")
        return
    lst = user_photos.get(uid, [])
    if idx < 0 or idx >= len(lst):
        update.message.reply_text("Index out of range.")
        return
    removed = lst.pop(idx)
    safe_remove(removed)
    safe_remove(removed + ".cmp.jpg")
    safe_remove(removed + ".wm.jpg")
    update.message.reply_text(f"Removed photo #{idx+1}. Remaining: {len(lst)}")

def move_photo(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    args = context.args
    if len(args) < 2:
        update.message.reply_text("Usage: /move <from> <to>  (1-based indices)")
        return
    try:
        a = int(args[0]) - 1
        b = int(args[1]) - 1
    except Exception:
        update.message.reply_text("Invalid indices.")
        return
    lst = user_photos.get(uid, [])
    if a < 0 or a >= len(lst) or b < 0 or b > len(lst):
        update.message.reply_text("Index out of range.")
        return
    item = lst.pop(a)
    lst.insert(b, item)
    update.message.reply_text(f"Moved photo from {a+1} to {b+1}.")

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

def preview(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    lst = user_photos.get(uid, [])
    if not lst:
        update.message.reply_text("No photos to preview.")
        return
    # Telegram allows media_group up to 10 per request
    batch_size = 10
    idx = 0
    try:
        while idx < len(lst):
            chunk = lst[idx:idx+batch_size]
            media = []
            files_to_close = []
            for p in chunk:
                try:
                    f = open(p, "rb")
                    files_to_close.append(f)
                    media.append(InputMediaPhoto(f))
                except Exception:
                    continue
            if media:
                context.bot.send_media_group(chat_id=update.message.chat_id, media=media)
            for f in files_to_close:
                try:
                    f.close()
                except Exception:
                    pass
            idx += batch_size
    except Exception:
        traceback.print_exc()
        update.message.reply_text("Failed to send preview.")

def makepdf(update: Update, context):
    uid = update.message.from_user.id
    ensure_user(uid)
    photos = list(user_photos.get(uid, []))
    if not photos:
        update.message.reply_text("No photos found. Send some photos first.")
        return

    s = user_settings[uid]
    filename = s.get("name", f"{uid}_output")
    watermark_text = s.get("watermark_text")
    watermark_pos = s.get("watermark_pos", "br")
    quality = s.get("compress_quality", DEFAULT_QUALITY)
    pagesize_key = s.get("pagesize", DEFAULT_PAGESIZE).upper()
    update.message.reply_text("Processing your PDF... ⏳ This may take a few seconds.")

    temp_images = []  # store processed image paths for cleanup and PDF
    try:
        # process each image: compress -> watermark
        for orig in photos:
            cmp_path = compress_image(orig, quality)
            wm_path = apply_watermark_to_image(cmp_path, watermark_text, watermark_pos)
            # prefer watermark path if exists
            final = wm_path if wm_path and os.path.exists(wm_path) else (cmp_path if cmp_path and os.path.exists(cmp_path) else orig)
            temp_images.append(final)

        # Create PDF
        # get page dimensions for fpdf (mm)
        pg = PAGE_SIZES.get(pagesize_key, PAGE_SIZES[DEFAULT_PAGESIZE])
        page_w_mm, page_h_mm = pg

        pdf = FPDF(unit="mm", format=(page_w_mm, page_h_mm))
        for img_path in temp_images:
            try:
                im = Image.open(img_path)
                w_px, h_px = im.size
                # Determine orientation: if image is wider than tall, use landscape
                orientation = "P"
                if w_px > h_px:
                    orientation = "L"
                # Add page with same orientation
                pdf.add_page(orientation=orientation)
                # Fit image to page margins (set left/right margins 10mm)
                max_w = page_w_mm - 20.0
                # compute height to keep aspect ratio
                render_w = max_w
                render_h = (h_px * render_w) / w_px
                # center vertically if space
                y = (page_h_mm - render_h) / 2.0
                pdf.image(img_path, x=10, y=max(5, y), w=render_w)
                im.close()
            except Exception:
                continue

        out_pdf = f"{filename}.pdf"
        pdf.output(out_pdf, "F")
        # send pdf
        update.message.reply_document(open(out_pdf, "rb"))
        update.message.reply_text("Done. PDF sent.")
    except Exception:
        traceback.print_exc()
        update.message.reply_text("Failed to create PDF.")
    finally:
        # cleanup originals and temp images
        for p in user_photos.get(uid, []):
            safe_remove(p)
            safe_remove(p + ".cmp.jpg")
            safe_remove(p + ".wm.jpg")
        # also remove processed temp images and pdf
        for t in temp_images:
            safe_remove(t)
        safe_remove(f"{s.get('name', uid+'_output')}.pdf")
        user_photos[uid] = []

# ---------- Main ----------
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not set in environment!")
        return

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # core commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("settings", settings))
    dp.add_handler(CommandHandler("name", set_name))
    dp.add_handler(CommandHandler("watermark", set_watermark))
    dp.add_handler(CommandHandler("watermark_pos", set_watermark_pos))
    dp.add_handler(CommandHandler("compress", set_compress))
    dp.add_handler(CommandHandler("pagesize", set_pagesize))
    dp.add_handler(CommandHandler("makepdf", makepdf))
    dp.add_handler(CommandHandler("clear", clear))

    # management & preview
    dp.add_handler(CommandHandler("delete_last", delete_last))
    dp.add_handler(CommandHandler("remove", remove_n, pass_args=True))
    dp.add_handler(CommandHandler("move", move_photo, pass_args=True))
    dp.add_handler(CommandHandler("preview", preview))

    # photo handler
    dp.add_handler(MessageHandler(Filters.photo, photo_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
