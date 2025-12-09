# Telegram Photo → PDF Bot (v13 stable)

This bot converts photos sent to it into PDFs. Fully compatible with GitHub Actions.

## Setup

1. Create a Telegram bot using BotFather and get the token.
2. In GitHub, go to Settings → Secrets → Actions → New repository secret
   - Name: `BOT_TOKEN`
   - Value: the token from BotFather
3. Push this repo to GitHub.
4. GitHub Actions will install dependencies and run the bot automatically.

## Usage
- Send /start to the bot.
- Send any photo.
- The bot will reply with a PDF containing your photo.

## Notes
- Only one photo at a time (can be extended for multiple photos if needed).
- Temporary files are removed after sending.
- Fully safe: token is kept secret using GitHub Secrets.
