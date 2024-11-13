# Zalando Price Monitor Bot 🤖

A Telegram bot that monitors product prices on Zalando.nl, alerting users when prices change.

## Features ✨

- Real-time price monitoring for Zalando.nl products
- Instant price change notifications
- Support for multiple products per user
- Easy to use Telegram interface
- Anti-blocking measures
- Docker containerization

## Prerequisites 📋

- Python 3.11+
- Docker and Docker Compose
- Telegram Bot Token (get from [@BotFather](https://t.me/botfather))

## Installation 🚀

1. Clone the repository
```bash
git clone https://github.com/m4h0ur/zalando-price-monitor.git
cd zalando-price-monitor
```

2. Create and configure `.env` file:
```bash
cp .env.example .env
# Edit .env and add your Telegram Bot Token
```

3. Build and run with Docker:
```bash
docker-compose up -d
```

## Usage 💡

Available commands:
- `/start` - Start the bot
- `/help` - Show help message
- `/add <url>` - Add a product to monitor
- `/list` - List monitored products
- `/remove` - Remove a product from monitoring
- `/status` - Check bot status

## Project Structure 📁

```
zalando-price-monitor/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── README.md
└── src/
    └── price_monitor.py
```

## Contributing 🤝

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
