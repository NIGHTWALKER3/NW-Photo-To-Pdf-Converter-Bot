import os
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import Update
from fpdf import FPDF

# Start command
def start(update: Update, context):
    update.message.reply_text("Send me any photo and I will convert it into a PDF for you! 📄🖼️")

# Photo handler
def photo_handler(update: Update, context):
    photo = update.message.photo[-1]
    file = context.bot.get_file(photo.file_id)

    image_path = "image.jpg"
    pdf_path = "output.pdf"

    file.download(image_path)

    pdf = FPDF()
    pdf.add_page()
    pdf.image(image_path, x=10, y=10, w=180)
    pdf.output(pdf_path, "F")

    update.message.reply_document(open(pdf_path, "rb"))

    os.remove(image_path)
    os.remove(pdf_path)

# Main function
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not set in environment!")
        return

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.photo, photo_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
