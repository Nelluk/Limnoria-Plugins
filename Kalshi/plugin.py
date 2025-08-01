import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.world as world
import supybot.log as log
from datetime import datetime
import pytz

class Kalshi(callbacks.Plugin):
    """Kalshi Prediction Market IRC Bot Plugin"""
    threaded = True  # Make network calls in a separate thread
    
    def __init__(self, irc):
        super().__init__(irc)
    
    def _shorten_url(self, url):
        """Helper method to shorten URL using TinyURL service"""
        try:
            import pyshorteners
            shortener = pyshorteners.Shortener()
            return shortener.tinyurl.short(url)
        except Exception as e:
            log.error('Kalshi: Failed to shorten URL: %s', str(e))
            return url
    
    def kalshi(self, irc, msg, args, query_string):
        """<query>
        
        Search Kalshi prediction markets and display current prices.
        Example: kalshi house seats
        """
        try:
            import requests  # Import here to allow for better reloading
            
            url = "https://api.elections.kalshi.com/v1/search/series"
            params = {
                "query": query_string,
                "order_by": "querymatch",
                "page_size": 5,
                "fuzzy_threshold": 4
            }
            
            log.debug('Kalshi: Making API request to %s with params: %r', url, params)
            response = requests.get(url, params=params)
            
            if response.status_code != 200:
                log.error('Kalshi: API request failed with status %d: %s', response.status_code, response.text)
                irc.reply(f"Error fetching data: API returned status {response.status_code}")
                return
                
            try:
                data = response.json()
            except ValueError as e:
                log.error('Kalshi: Failed to parse API response as JSON: %s. Response text: %s', str(e), response.text)
                irc.reply("Error: Invalid response from API")
                return
            
            if not data or 'current_page' not in data or not data['current_page']:
                irc.reply("No results found.")
                return
            
            # Find the first open series
            now = datetime.now(pytz.UTC)
            
            open_series = None
            for series in data['current_page']:
                # Check if any market in the series is currently open
                if series.get('markets'):
                    for market in series['markets']:
                        open_time = datetime.strptime(market['open_ts'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                        if open_time <= now:
                            open_series = series
                            break
                    if open_series:
                        break
            
            if not open_series:
                irc.reply("No currently open markets found.")
                return
            
            # Use the open series for display
            top_series = open_series
            
            # Debug log the API response
            log.debug('Kalshi: Full API response for selected series: %r', top_series)
            log.debug('Kalshi: Series keys available: %s', ', '.join(top_series.keys()))
            if top_series.get('markets'):
                log.debug('Kalshi: First market keys available: %s', ', '.join(top_series['markets'][0].keys()))
            
            # Format header with series information
            series_title = top_series['series_title']
            event_title = top_series['event_title']
            event_subtitle = top_series['event_subtitle']
            
            # Build output parts
            output_parts = []
            
            # Add header
            output_parts.append(f"{ircutils.bold(series_title)} {event_subtitle} | {event_title}")
            
            # Get markets and sort by yes_bid price
            if top_series.get('markets'):
                markets = top_series['markets']
                # Filter for markets with active prices and sort by yes_bid
                active_markets = [m for m in markets if m.get('yes_bid', 0) > 0]
                sorted_markets = sorted(active_markets, key=lambda x: x.get('yes_bid', 0), reverse=True)
                
                # Format market outcomes
                market_parts = []
                for market in sorted_markets[:8]:
                    subtitle = market.get('yes_subtitle', 'No subtitle')
                    current_price = market.get('yes_bid', 'N/A')
                    price_delta = market.get('price_delta', 0)
                    
                    # Format price changes with colors
                    if price_delta > 0:
                        delta_str = ircutils.mircColor(f"+{price_delta}¢", 'green')
                    elif price_delta < 0:
                        delta_str = ircutils.mircColor(f"{price_delta}¢", 'red')
                    else:
                        delta_str = f"±{price_delta}¢"
                    
                    market_parts.append(f"{subtitle}: {current_price}¢ ({delta_str})")
                
                if market_parts:
                    output_parts.append(" | ".join(market_parts))
                
                # If there are more markets with non-zero prices, add count
                remaining = len([m for m in markets if m.get('yes_bid', 0) > 0]) - 8
                if remaining > 0:
                    output_parts.append(f"(+{remaining} more)")
            
            # Add shortened URL using series_ticker
            market_url = f"https://kalshi.com/markets/{top_series.get('series_ticker', '')}"
            log.debug('Kalshi: Constructing URL: %s', market_url)
            short_url = self._shorten_url(market_url)
            log.debug('Kalshi: Shortened URL: %s', short_url)
            output_parts.append(short_url)
            
            # Send single combined message
            irc.reply(" | ".join(output_parts))
            
        except requests.RequestException as e:
            irc.reply(f"Error fetching data: {str(e)}")
        except Exception as e:
            irc.reply(f"Error: {str(e)}")
    
    kalshi = wrap(kalshi, ['text'])

Class = Kalshi
