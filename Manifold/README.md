# Manifold Supybot Plugin

This plugin for Supybot (Limnoria) allows users to fetch and display current odds from Manifold.markets directly in IRC channels.

## Features

- Fetch odds for specific Manifold.markets events using URLs or search terms
- Display top outcomes with probabilities
- Show market volume and number of unique bettors
- Support for both binary (Yes/No) markets and markets with multiple outcomes
- Provide direct link to the market

## Installation

1. Ensure you have Supybot (Limnoria) installed and configured.

2. Clone this repository and place the resulting 'Manifold' directory in your Supybot plugins directory. The path typically looks like this:
   ```
   /path/to/your/supybot/plugins/Manifold/plugin.py
   ```

3. Load the plugin in your Supybot instance:
   ```
   @load Manifold
   ```

## Usage

The plugin provides a single command: `manifold`

### Syntax

```
@manifold <query>
```

Where `<query>` can be either a Manifold.markets URL or a search term.

### Examples

1. Fetching odds for a specific market using URL:
   ```
   @manifold https://manifold.markets/user/market-slug
   ```
   Output:
   ```
   Market Title (Volume: 343k, Bettors: 150): Outcome1: 60.0% | Outcome2: 40.0% | https://manifold.markets/user/market-slug
   ```

2. Searching for a market using keywords:
   ```
   @manifold AI breakthrough 2023
   ```
   Output:
   ```
   Will there be a major AI breakthrough in 2023? (Volume: 50k, Bettors: 200): Yes: 30.0% | No: 70.0% | https://manifold.markets/user/will-there-be-a-major-ai-breakthrough
   ```

## Notes

- The plugin will display up to 7 outcomes for each query, sorted by probability.
- For markets with multiple outcomes, all top outcomes are shown (up to the limit).
- The output includes the market title, total volume, number of unique bettors, and a direct link to the market.
- Volume is displayed in a simplified format (e.g., 343k for 343,000).

## Dependencies

- requests

This should be installed by default in most Python environments. If not, you can install it using pip:
```
pip install requests
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.

## Disclaimer

This plugin is not officially associated with Manifold.markets. Use at your own risk and be aware of the terms of service of Manifold.markets when using this plugin.
