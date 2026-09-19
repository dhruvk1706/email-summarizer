# email-assistant

This checks your Gmail inbox for new emails, asks Google's Gemini AI to summarize each one, and sends the summary to you on Telegram. You run it periodically (manually or on a schedule) and it tells you what's new in your inbox without you having to open Gmail.

## What you need before starting

1. **A Gmail account** with an "app password" (not your regular Gmail password — Google requires a special password for apps like this to log in).
   - Go to https://myaccount.google.com/apppasswords, generate one, and save it somewhere safe.
2. **A Telegram bot**, so the summaries have somewhere to be sent.
   - Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts, and it'll give you a bot token.
   - Send a message to your new bot, then visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser to find your chat ID (it'll be a number in the response).
3. **A Google Cloud account** with Vertex AI enabled, since that's what runs the Gemini AI model.
   - Create a project, enable the Vertex AI API, create a service account, and download its key as a JSON file.

## Step 1: Install the dependencies

Open a terminal in this folder and run:

```
pip install -r requirements.txt
```

This installs the Python libraries the code needs (Flask for the web server, the Telegram library, etc).

## Step 2: Add your secrets

Create a file named `.env` in this folder (same folder as this README) and paste this in, filling in your own values:

```
GMAIL_IMAP_USER=youremail@gmail.com
GMAIL_APP_PASSWORD=the app password from step 1
TELEGRAM_BOT_TOKEN=the token BotFather gave you
TELEGRAM_CHAT_ID=your chat id number
POLL_TOKEN=make up any random password here — it protects your endpoint from strangers
GOOGLE_CLOUD_PROJECT=your google cloud project id
GOOGLE_CLOUD_LOCATION=e.g. us-central1
TELEGRAM_WEBHOOK_SECRET=make up another random password here — used to reply "full" (see below)
```

Also take the JSON key file you downloaded from Google Cloud in step 3 above, rename it to `service-account.json`, and put it in this same folder.

**Do not share either of these two files with anyone or commit them to git — they contain passwords and keys.**

## Step 3: Run it

```
python server.py
```

This starts a small web server on your computer at port 8080. Leave this running in the terminal.

## Step 4: Check for new emails

While the server is running, open a **new** terminal window (or a browser tab) and visit this address, replacing `<POLL_TOKEN>` with the password you made up in Step 2:

```
http://localhost:8080/poll?token=<POLL_TOKEN>
```

Every time you visit that link (or send a request to it), it checks your inbox for anything new and sends you a summary on Telegram. In real use, you'd point a scheduler (like a cron job or a cloud service) at this address to check automatically every so often, instead of visiting it by hand.

To confirm the server is alive at all, you can visit `http://localhost:8080/` — it should just say the service is running.

## Getting the full email body

Each summary is sent to you on Telegram as a reply-able message. Reply to any summary with the word `full` and the bot replies back with the complete original email body.

For this to work, Telegram needs to know where to send your replies — you register a "webhook" once, pointing at your server's public URL (this only works once your server is deployed somewhere reachable from the internet, e.g. Cloud Run, not `localhost`):

```
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<your-deployed-host>/telegram-webhook&secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Use the same `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET` values from your `.env`. You only need to do this once (or again if your host URL changes).

## Heads up: the first time you run it

The very first time you hit `/poll`, it will **not** send you anything — it just marks your current unread emails as "seen" so you don't get flooded with your entire backlog. Only emails that arrive *after* that first check will get summarized and sent. If you want to reset this and re-trigger that first-run behavior, delete the file called `baseline_established` from this folder.
