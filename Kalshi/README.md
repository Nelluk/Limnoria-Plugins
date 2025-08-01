# Kalshi IRC Bot Plugin

## Overview
This Limnoria plugin provides real-time Kalshi prediction market information directly in your IRC channel.

## Prerequisites
- Python 3.7+
- Limnoria
- Kalshi Python SDK
- Kalshi Account

## Installation
1. Install dependencies:
```bash
pip install kalshi supybot
```

2. Set Kalshi Credentials as Environment Variables:
```bash
export KALSHI_EMAIL='your_email@example.com'
export KALSHI_PASSWORD='your_password'
```

## Usage
In your IRC channel:
- `!markets`: List top 5 active markets
- `!market MARKET_ID`: Get details for a specific market

## Configuration
Configure the plugin in your Limnoria bot's configuration.

## Security Notes
- Never share your Kalshi credentials
- Use environment variables for authentication
- Limit bot access to trusted channels

## Disclaimer
This plugin is not officially affiliated with Kalshi. Market data is provided as-is.
