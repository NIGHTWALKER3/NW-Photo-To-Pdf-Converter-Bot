import os
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from PIL import Image

user_photos = {}
default_settings = {
    "pdf_name": "output",
    "watermark": None,
    "watermark_pos": "center",
    "compress": 95,
    "pagesize": "A4"
}
user_settings = {}


# ---------------------- Start Command ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_photos[user_id] = []
    user_settings[user_id] = default_settings.copy()

    await update.message.reply_text(
        "👋 Welcome to **NW PDF Converter Bot**!\n\n"
        "Send photos and I will convert them into a clean PDF.\n\n"
        "Use /makepdf when you're ready.\n"
        "Use /settings to view your current configuration."
    )


# ---------------------- Photo Handler ----------------------
async def save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_photos:
        user_photos[user_id] = []
        user_settings[user_id] = default_settings.copy()

    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"/tmp/{user_id}_{len(user_photos[user_id]) + 1}.jpg"
    await file.download_to_drive(file_path)

    user_photos[user_id].append(file_path)

    await update.message.reply_text(
        f"📸 Photo saved! Total photos: {len(user_photos[user_id])}"
    )


# ---------------------- Make PDF ----------------------
async def makepdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_photos or len(user_photos[user_id]) == 0:
        await update.message.reply_text("❗ You have not uploaded any photos yet.")
        return

    settings = user_settings.get(user_id, default_settings.copy())
    pdf_filename = settings["pdf_name"] + ".pdf"
    pdf_path = f"/tmp/{pdf_filename}"

    image_list = []
    for img_path in user_photos[user_id]:
        img = Image.open(img_path).convert("RGB")
        image_list.append(img)

    # Save PDF
    image_list[0].save(
        pdf_path,
        save_all=True,
        append_images=image_list[1:]
    )

    # Send PDF
    await update.message.reply_document(document=open(pdf_path, "rb"))

    # 🔥 Auto-Reset everything
    user_photos[user_id] = []
    user_settings[user_id] = default_settings.copy()

    await update.message.reply_text(
        "✅ PDF created successfully!\n"
        "🔄 All photos & settings cleared.\n"
        "Start fresh anytime!"
    )


# ---------------------- Set PDF Name ----------------------
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if len(context.args) == 0:
        await update.message.reply_text("Usage: /name filename")
        return

    user_settings[user_id]["pdf_name"] = context.args[0]
    await update.message.reply_text(f"📄 PDF name set to: {context.args[0]}")


# ---------------------- Set Watermark ----------------------
async def watermark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if len(context.args) == 0:
        await update.message.reply_text("Usage: /watermark YourText")
        return

    user_settings[user_id]["watermark"] = " ".join(context.args)
    await update.message.reply_text("💧 Watermark saved!")


# ---------------------- Set Watermark Position ----------------------
async def watermark_pos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if len(context.args) == 0:
        await update.message.reply_text("Choose: center, topleft, bottomright")
        return

    user_settings[user_id]["watermark_pos"] = context.args[0]
    await update.message.reply_text(f"📌 Watermark position: {context.args[0]}")


# ---------------------- Compression ----------------------
async def compress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if len(context.args) == 0:
        await update.message.reply_text("Usage: /compress 10-95")
        return

    quality = int(context.args[0])
    user_settings[user_id]["compress"] = quality
    await update.message.reply_text(f"🗜 Compression set to {quality}")


# ---------------------- Page Size ----------------------
async def pagesize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if len(context.args) == 0:
        await update.message.reply_text("Usage: /pagesize A4")
        return

    size = context.args[0]
    user_settings[user_id]["pagesize"] = size

    await update.message.reply_text(f"📐 Page size set to {size}")


# ---------------------- Clear Photos ----------------------
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_photos[user_id] = []
    await update.message.reply_text("🧹 All photos cleared!")


# ---------------------- Settings ----------------------
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    s = user_settings.get(user_id, default_settings.copy())

    msg = (
        "⚙ **Your Current Settings:**\n\n"
        f"📄 File Name: {s['pdf_name']}\n"
        f"💧 Watermark: {s['watermark']}\n"
        f"📌 Watermark Position: {s['watermark_pos']}\n"
        f"🗜 Compression: {s['compress']}\n"
        f"📐 Page Size: {s['pagesize']}\n"
    )
    await update.message.reply_text(msg)


# ---------------------- Main ----------------------
async def main():
    bot_token = os.getenv("BOT_TOKEN")
    app = Application.builder().token(bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("makepdf", makepdf))
    app.add_handler(CommandHandler("name", name))
    app.add_handler(CommandHandler("watermark", watermark))
    app.add_handler(CommandHandler("watermark_pos", watermark_pos))
    app.add_handler(CommandHandler("compress", compress))
    app.add_handler(CommandHandler("pagesize", pagesize))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("settings", settings))

    app.add_handler(MessageHandler(filters.PHOTO, save_photo))

    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
