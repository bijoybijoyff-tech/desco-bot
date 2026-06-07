# DESCO Prepaid Balance Bot

Telegram bot to check DESCO prepaid meter balance and receive daily notifications.

## Commands

| Command   | Description                              |
|-----------|------------------------------------------|
| `/start`  | Register meter number & check balance    |
| `/check`  | Manually check balance anytime           |
| `/stop`   | Cancel daily notifications               |
| `/status` | View your registered meter & settings    |
| `/cancel` | Cancel current operation                 |

## Features
- Instant balance check on meter number entry
- Optional daily notification at 9:00 PM (BD Time)
- Per-user meter storage in `users.json`
- Free hosting on Render.com (worker service)
