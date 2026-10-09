# RSS to Telegram Auto-Poster

Checks an RSS feed on a schedule and posts every new item to one or more Telegram channels or groups, with the title, a short summary and the article's picture. It runs for free on GitHub Actions, so you don't need a server.

## What it does

- Reads an RSS feed and posts only items it hasn't posted before
- Each post has a bold title, a summary (HTML removed, trimmed to 600 characters) and an image
- Finds the image from the feed's media tags, or the first picture in the item, or the article page's preview image
- Posts to several channels or groups at once
- Remembers what it has posted in `seen.json`, so nothing is sent twice
- Posts no link to the original article

## How it works

A GitHub Actions workflow runs `bot.py` every 30 minutes. The script reads the feed, compares it with `seen.json`, posts anything new, and the workflow saves the updated `seen.json` back to the repo.

On the **first run** the bot records the items already in the feed and posts nothing, so your channel isn't flooded.

## Files

| File | Purpose |
|---|---|
| `bot.py` | The bot |
| `requirements.txt` | Python packages (`feedparser`, `requests`) |
| `.github/workflows/post.yml` | The schedule and run steps |
| `seen.json` | Created automatically; list of posted items |

## Setup

1. Message **@BotFather** on Telegram, send `/newbot`, and copy the token.
2. Add the bot to each channel or group as an **admin** with permission to post.
3. Find each chat ID. For a public channel use `@channelname`. For a private channel or group use the number that starts with `-100`.
4. In the repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add:

   | Name | Value |
   |---|---|
   | `BOT_TOKEN` | the token from BotFather |
   | `CHAT_ID` | one or more IDs separated by commas, for example `@channel1,@channel2` |
   | `FEED_URL` | the full RSS link, including `https://` |

5. Make sure the workflow file is at `.github/workflows/post.yml`.
6. Go to **Actions → Post RSS updates → Run workflow**. The first run only records the current items.
7. To test a real post, open `seen.json`, delete one entry, commit, and run the workflow again.

## Configuration

Set these as environment variables (in the `env:` section of the workflow for Actions).

| Variable | Required | Default | What it does |
|---|---|---|---|
| `BOT_TOKEN` | yes | | Telegram bot token |
| `CHAT_ID` | yes | | Chat ID or several, separated by commas |
| `FEED_URL` | yes | | RSS feed link |
| `RUN_ONCE` | no | off | Set to `1` to check once and exit (used by the workflow) |
| `CHECK_INTERVAL` | no | `600` | Seconds between checks when running non-stop |
| `SUMMARY_LIMIT` | no | `600` | Maximum summary length in characters |
| `SEEN_FILE` | no | `seen.json` | Where posted items are saved |

## Changing the schedule

Edit the `cron` line in `post.yml`. The default `"7,37 * * * *"` means minutes 7 and 37 of every hour. GitHub's scheduler is best-effort, so runs can start late or occasionally be skipped. Each run uses at least one Actions minute, which matters on private repos with a monthly limit. Public repos are free.

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| `Invalid URL '': No scheme supplied` | The `FEED_URL` secret is missing or misspelled. Re-add it with the exact name. |
| `Feed returned 0 entries` | The feed link is wrong or the site is blocking the request. Open the link in a browser to check. |
| `Telegram sendMessage error` in the log | The bot isn't an admin of that channel, or `CHAT_ID` is wrong. |
| Run is green but nothing posts | There is no new item since the last run. This is normal. |
| Reposts after a redeploy | `seen.json` was lost. Keep it committed in the repo. |
| Scheduled runs don't appear | GitHub delays or skips cron runs. Wait an hour, or move the minutes to off-peak values. |

## Security

Never put the bot token in the code or in a commit. If it leaks, send `/revoke` to @BotFather to get a new one.

## Run it on your own computer

```
pip install -r requirements.txt
export BOT_TOKEN=... CHAT_ID=... FEED_URL=...
python bot.py              # checks over and over
RUN_ONCE=1 python bot.py   # checks once
```
