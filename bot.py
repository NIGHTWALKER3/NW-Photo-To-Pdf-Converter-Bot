import os
from PIL import Image
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler

TEMP_DIR = "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me photos (one or many). When finished, send /makepdf to get a single PDF.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Usage:\n1) Send photos (any order).\n2) Send /makepdf — I'll reply with a PDF.\n3) Send /clear to remove saved photos.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = os.path.join(user_dir, f"{file.file_id}.jpg")
    await file.download_to_drive(file_path)

    await update.message.reply_text("Saved photo. Send more or /makepdf when ready.")

async def make_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    pdf_path = os.path.join(user_dir, "output.pdf")

    if not os.path.isdir(user_dir):
        await update.message.reply_text("No photos found. Send some photos first.")
        return

    images = []
    for fname in sorted(os.listdir(user_dir)):
        if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            img = Image.open(os.path.join(user_dir, fname)).convert('RGB')
            images.append(img)

    if not images:
        await update.message.reply_text("No photos found. Send some photos first.")
        return

    images[0].save(pdf_path, save_all=True, append_images=images[1:])
    await update.message.reply_document(document=open(pdf_path, 'rb'))

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    if os.path.isdir(user_dir):
        for f in os.listdir(user_dir):
            try:
                os.remove(os.path.join(user_dir, f))
            except Exception:
                pass
        await update.message.reply_text("Cleared your saved photos.")
    else:
        await update.message.reply_text("Nothing to clear.")

async def main():
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        raise RuntimeError('BOT_TOKEN environment variable not set')

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('makepdf', make_pdf))
    app.add_handler(CommandHandler('clear', clear))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())