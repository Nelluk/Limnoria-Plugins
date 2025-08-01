import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.log as log
import requests
import json
from urllib.parse import urlparse, quote
import warnings
import pyshorteners
from requests.exceptions import Timeout, ConnectionError

# Suppress InsecureRequestWarning
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

class Polymarket(callbacks.Plugin):
    """Fetches and displays odds from Polymarket"""

    def _parse_polymarket_event(self, query, is_url=True, max_responses=12):
        """
        Parse Polymarket event data from API response.
        
        Args:
            query (str): URL or search string
            is_url (bool): True if query is a URL, False if it's a search string
            max_responses (int): Maximum number of outcomes to return

        Returns:
            dict: Parsed event data with title and outcomes
        """
        # Prepare API query
        if is_url:
            parsed_url = urlparse(query)
            path_parts = parsed_url.path.split('/')
            slug = ' '.join(path_parts[-1].split('-'))
        else:
            slug = query

        encoded_slug = quote(slug)
        api_url = f"https://polymarket.com/api/events/global?q={encoded_slug}"
        
        log.debug(f"Polymarket: Fetching data from API URL: {api_url}")
        
        # Fetch data from API
        response = requests.get(api_url, verify=False)
        response.raise_for_status()
        data = response.json()

        log.debug(f"Polymarket: API response data: {data}")  # Log the raw API response

        if not data or 'events' not in data or not data['events']:
            return {'title': "No matching event found", 'data': [], 'slug': ''}

        # Find matching event
        if is_url:
            matching_event = next((event for event in data['events'] if event['slug'] == slug.replace(' ', '-')), None)
        else:
            matching_event = data['events'][0] if data['events'] else None

        if not matching_event:
            return {'title': "No matching event found", 'data': [], 'slug': ''}

        title = matching_event['title']
        slug = matching_event.get('slug', '')  # Use .get() to avoid KeyError
        markets = matching_event['markets']

        log.debug(f"Polymarket: Matching event found: {title}, slug: {slug}, markets: {markets}")  # Log matching event details

        # Parse market data
        cleaned_data = []
        for market in markets:
            outcome = market['groupItemTitle']
            log.debug(f"Polymarket: Parsing market: {outcome}")  # Log the current market being parsed
            try:
                outcomes = market['outcomes']
                outcome_prices = market['outcomePrices']
                clob_token_ids = market.get('clobTokenIds', [None] * len(market['outcomes']))

                # Handle empty outcomePrices for Yes/No markets
                if not outcome_prices:
                    if len(outcomes) == 2 and 'Yes' in outcomes and 'No' in outcomes:
                        # Try to use bestAsk/bestBid/lastTradePrice
                        yes_index = outcomes.index('Yes')
                        no_index = outcomes.index('No')
                        yes_price = market.get('bestAsk')
                        no_price = None
                        if market.get('bestBid') is not None:
                            no_price = 1 - market['bestBid']
                        if yes_price is not None and no_price is not None:
                            outcome_prices = [str(yes_price), str(no_price)]
                        elif market.get('lastTradePrice') is not None:
                            yes_price = market['lastTradePrice']
                            no_price = 1 - yes_price
                            outcome_prices = [str(yes_price), str(no_price)]
                        else:
                            log.debug(f"Skipping market due to missing prices: {market}")
                            continue
                    else:
                        log.debug(f"Skipping non-Yes/No market with missing outcomePrices: {market}")
                        continue
                if len(outcome_prices) != len(outcomes):
                    log.debug(f"Skipping market due to mismatched outcomePrices: {market}")
                    continue
                log.debug(f"Polymarket: Outcomes: {outcomes}, Prices: {outcome_prices}, Token IDs: {clob_token_ids}")  # Log parsed data
                if len(outcomes) == 2 and 'Yes' in outcomes and 'No' in outcomes:
                    yes_index = outcomes.index('Yes')
                    no_index = outcomes.index('No')
                    yes_probability = float(outcome_prices[yes_index])
                    no_probability = float(outcome_prices[no_index])
                    # Handle the edge case for Yes/No markets only if it's the only market
                    if len(markets) == 1 and yes_probability <= 0.01 and no_probability > 0.99:
                        cleaned_data.append((outcome, yes_probability, 'Yes', clob_token_ids[yes_index]))
                    else:
                        probability = yes_probability
                        display_outcome = 'Yes'
                        cleaned_data.append((outcome, probability, display_outcome, clob_token_ids[yes_index]))
                else:
                    # For multi-outcome markets, always use the highest probability
                    max_price_index = outcome_prices.index(max(outcome_prices, key=float))
                    probability = float(outcome_prices[max_price_index])
                    display_outcome = outcomes[max_price_index]
                    cleaned_data.append((outcome, probability, display_outcome, clob_token_ids[max_price_index]))
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                log.error(f"Polymarket: Error parsing market data: {str(e)}")  # Log parsing errors
                continue

        # Sort outcomes by probability and limit to max_responses
        cleaned_data.sort(key=lambda x: x[1], reverse=True)
        
        result = {
            'title': title,
            'slug': slug,
            'data': [item for item in cleaned_data if item[1] >= 0.01 or len(cleaned_data) == 1][:max_responses]
        }
        
        log.debug(f"Polymarket: Parsed event data: {result}")
        
        return result

    def _get_price_change(self, clob_token_id, current_price):
        """Fetches and calculates the 24-hour price change for a given clob_token_id."""
        api_url = f"https://clob.polymarket.com/prices-history?interval=1d&market={clob_token_id}&fidelity=1"
        try:
            response = requests.get(api_url, verify=False)
            response.raise_for_status()
            data = response.json()
            if data and 'history' in data and len(data['history']) > 0:
                price_24h_ago = data['history'][0]['p']
                return current_price - price_24h_ago
        except Exception as e:
            log.error(f"Error fetching price history: {str(e)}")
        return None

    def _find_matching_event(self, events: list, slug: str, is_url: bool) -> dict:
        """Finds the matching event from a list of events."""
        if is_url:
            return next((event for event in events if event['slug'] == slug.replace(' ', '-')), None)
        else:
            return events[0] if events else None

    def _parse_market_data(self, market: dict) -> list:
        """Parses data for a single market within an event."""
        outcome = market['groupItemTitle']
        log.debug(f"Polymarket: Parsing market: {outcome}")
        try:
            outcomes = market['outcomes']
            outcome_prices = market['outcomePrices']
            clob_token_ids = market.get('clobTokenIds', [None] * len(market['outcomes']))

            log.debug(f"Polymarket: Outcomes: {outcomes}, Prices: {outcome_prices}, Token IDs: {clob_token_ids}")

            if len(outcomes) == 2 and 'Yes' in outcomes and 'No' in outcomes:
                return self._parse_yes_no_market(outcomes, outcome_prices, clob_token_ids)
            else:
                return self._parse_multi_outcome_market(outcomes, outcome_prices, clob_token_ids)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            log.error(f"Polymarket: Error parsing market  {str(e)}")
            return []

    def _parse_yes_no_market(self, outcomes: list, outcome_prices: list, clob_token_ids: list) -> list:
        """Parses data for a Yes/No market."""
        yes_index = outcomes.index('Yes')
        no_index = outcomes.index('No')
        yes_probability = float(outcome_prices[yes_index])
        no_probability = float(outcome_prices[no_index])

        # Handle edge case for Yes/No markets where 'Yes' probability is extremely low
        if yes_probability <= 0.01 and no_probability > 0.99:
            return [(outcomes[yes_index], yes_probability, 'Yes', clob_token_ids[yes_index])]
        else:
            return [(outcomes[yes_index], yes_probability, 'Yes', clob_token_ids[yes_index])]

    def _parse_multi_outcome_market(self, outcomes: list, outcome_prices: list, clob_token_ids: list) -> list:
        """Parses data for a multi-outcome market."""
        max_price_index = outcome_prices.index(max(outcome_prices, key=float))
        probability = float(outcome_prices[max_price_index])
        display_outcome = outcomes[max_price_index]
        return [(outcomes[max_price_index], probability, display_outcome, clob_token_ids[max_price_index])]

    def polymarket(self, irc, msg, args, query: str):
        """<query>
        
        Fetches and displays the current odds from Polymarket. 
        If <query> is a URL, it fetches odds for that specific market.
        If <query> is a search string, it searches for matching markets and displays the top result.
        """
        try:
            is_url = query.startswith('http://') or query.startswith('https://')
            result = self._parse_polymarket_event(query, is_url=is_url)
            if result['data']:
                filtered_data = result['data'][:20]
                
                # Format output
                output = f"\x02{result['title']}\x02: "
                for outcome, probability, display_outcome, clob_token_id in filtered_data:
                    price_change = self._get_price_change(clob_token_id, probability)
                    change_str = f" ({'⬆️' if price_change > 0 else '🔻'}{abs(price_change)*100:.1f}%)" if price_change is not None and price_change != 0 else ""
                    output += f"{outcome}: \x02{probability:.0%}{change_str}{' (' + display_outcome + ')' if display_outcome != 'Yes' else ''}\x02 | "
                
                output = output.rstrip(' | ')
                
                # Generate URL
                if is_url:
                    market_url = query
                else:
                    slug = result.get('slug', '')
                    market_url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
                
                # Try to shorten URL, fall back to full URL if there's an error
                try:
                    shortener = pyshorteners.Shortener(timeout=5)  # Increase timeout to 5 seconds
                    short_url = shortener.tinyurl.short(market_url)
                    output += f" | {short_url}"
                except (Timeout, ConnectionError, pyshorteners.exceptions.ShorteningErrorException) as e:
                    log.warning(f"URL shortening failed: {str(e)}. Using full URL.")
                    output += f" | {market_url}"
                
                log.debug(f"Polymarket: Sending IRC reply: {output}")
                
                irc.reply(output, prefixNick=False)
            else:
                irc.reply(result['title'])
        except requests.RequestException as e:
            irc.reply(f"Error fetching data from Polymarket: {str(e)}")
        except json.JSONDecodeError:
            irc.reply("Error parsing data from Polymarket. The API response may be invalid.")
        except Exception as e:
            log.error(f"Polymarket plugin error: {str(e)}")
            irc.reply("An unexpected error occurred. Please try again later.")

    polymarket = wrap(polymarket, ['text'])

    def polymarkets(self, irc, msg, args, text):
        """<market-name-one> <market-name-two> ...
        
        Fetches and displays the current odds from Polymarket for multiple queries.
        Each market name should have words separated by hyphens.
        """

        log.debug("msg", msg, "text", text)
        queries = text.split()  # Split by spaces instead of using shlex

        log.debug(f"Split queries: {queries}")

        combined_results = []
        seen_words = set()  # Track words from previous market titles
        for query in queries:
            is_url = query.startswith('http://') or query.startswith('https://')
            query = query.replace('-', ' ') if not is_url else query
            result = self._parse_polymarket_event(query, is_url=is_url)
            log.debug(f"Processing query: {query}")
            if result['data']:
                market_title = result['title']  # Get the title from the result
                
                # Split title into words and filter out seen words
                # to handle multiple markets with the nearly-identical names
                title_words = market_title.split()
                filtered_title = ' '.join(word for word in title_words if word.lower() not in seen_words)
                
                # Update seen words with the current title words
                seen_words.update(word.lower() for word in title_words)

                # Only take the top outcome
                outcome, probability, display_outcome, clob_token_id = result['data'][0]  # Get the first outcome
                
                # Special case for "Republican" and "Democrat"
                if outcome == "Republican":
                    outcome = "\x0304Rep\x03"  # Color Red
                elif outcome == "Democrat":
                    outcome = "\x0312Dem\x03"  # Color Blue
                
                price_change = self._get_price_change(clob_token_id, probability)
                change_str = f" ({'⬆️' if price_change > 0 else '🔻'}{abs(price_change)*100:.1f}%)" if price_change is not None and price_change != 0 else ""
                combined_results.append(f"{filtered_title}: {outcome}: \x02{probability:.0%}{change_str}{' (' + display_outcome + ')' if display_outcome != 'Yes' else ''}\x02")
            else:
                combined_results.append(f"No matching market found for '{query}'.")

        if combined_results:
            output = " | ".join(combined_results)
            irc.reply(output, prefixNick=False)
        else:
            irc.reply("No matching markets found for the provided queries.")

    polymarkets = wrap(polymarkets, ['text'])

Class = Polymarket

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
