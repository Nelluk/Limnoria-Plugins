# Polymarket Supybot Plugin

This plugin for Supybot (Limnoria) allows users to fetch and display current odds from Polymarket directly in IRC channels.

## Features

- Fetch odds for specific Polymarket events using URLs
- Search for Polymarket events using keywords
- Display top outcomes with probabilities and 24-hour price changes
- Support for both Yes/No markets and markets with custom outcomes

## Installation

1. Ensure you have Supybot (Limnoria) installed and configured.

2. Clone this repository and place the resulting 'Polymarket' directory in your Supybot plugins directory. The path typically looks like this:
   ```
   /path/to/your/supybot/plugins/Polymarket/plugin.py
   ```

4. Load the plugin in your Supybot instance:
   ```
   @load Polymarket
   ```

## Usage

The plugin provides two commands: `polymarket` and `polymarkets`.

### Syntax

```
@polymarket <query>
```

Where `<query>` can be either a Polymarket URL or a search term.

### Examples

1. Fetching odds for a specific market using URL:
   ```
   @polymarket https://polymarket.com/event/balance-of-power-2024-election
   ```
   Output:
   ```
   Balance of Power: 2024 Election: Republicans sweep: 32% (🔻1.0%) | D Prez, R Senate, D House: 28% (🔺0.5%) | Democrats sweep: 21% (🔻0.2%) | R Prez, R Senate, D House: 15% (🔺0.3%) | D Prez, R Senate, R House: 5% (🔻0.1%)
   ```

2. Searching for a market using keywords:
   ```
   @polymarket nfl sunday
   ```
   Output:
   ```
   NFL Sunday: Packers vs Bears: 58% (🔺2.0%) (Packers) | Cowboys vs Giants: 62% (🔻1.5%) (Cowboys) | 49ers vs Rams: 55% (🔺0.5%) (49ers)
   ```

### Multiple events

```
@polymarkets <event-slug-or-url-one> <event-slug-or-url-two> ...
```

`polymarkets` accepts either full Polymarket event URLs or bare event slugs.
Bare slugs are looked up exactly, which makes it possible to include more
events in one IRC command than with full URLs.

Example:

```
@polymarkets fed-decision-in-october government-shutdown-by-friday
```

The singular `polymarket` command continues to treat non-URL input as a
keyword search.

## Notes

- The plugin will display up to 7 outcomes for each query, sorted by probability.
- Only outcomes with at least 1% probability are shown.
- For markets with custom outcomes (not Yes/No), the outcome name is displayed in parentheses.
- Each outcome now includes a 24-hour price change, shown as a percentage point difference with an up (🔺) or down (🔻) arrow.

## Dependencies

- requests
- urllib

These should be installed by default in most Python environments.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.

## Disclaimer

This plugin is not officially associated with Polymarket. Use at your own risk and be aware of the terms of service of Polymarket when using this plugin.
