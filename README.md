# Telegram Photo → PDF Bot (v13 stable)

This bot converts photos sent to it into PDFs. Fully compatible with GitHub Actions.

## Usage
- Send /start to the bot.
- Send any photo.
- The bot will reply with a PDF containing your photo.

## Notes
- Only one photo at a time (can be extended for multiple photos if needed).
- Temporary files are removed after sending.
- Fully safe: token is kept secret using GitHub Secrets.
