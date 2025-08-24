"""
Polymarket plugin

Implementation notes and gotchas:

- Avoid wildcard imports from supybot.commands. They define names like `any` that
  shadow Python builtins. Use explicit imports (e.g., `from supybot.commands import wrap`).
- Search flow uses the optimized public-search endpoint first and falls back to
  the plain endpoint if no events are returned. Optimized results sometimes omit
  fields such as `clobTokenIds`; `_ensure_clob_ids` enriches them via detail endpoints.
- Markets can present missing or stringified arrays. `_as_list` normalizes these,
  and pricing falls back to `bestAsk`/`bestBid`/`lastTradePrice` for Yes/No markets.
- URL shortening is optional. `_shorten_url` tries TinyURL with fallbacks; it logs
  and returns the full URL when shortening is unavailable.
"""

import supybot.utils as utils
# Avoid wildcard import: it can shadow Python builtins like `any`/`all`.
from supybot.commands import wrap
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.log as log
import requests
import builtins
import json
from urllib.parse import urlparse, quote
import warnings
import pyshorteners
from requests.exceptions import Timeout, ConnectionError

# Suppress InsecureRequestWarning
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

class Polymarket(callbacks.Plugin):
    """Fetches and displays odds from Polymarket"""

    def _as_list(self, value):
        """Ensure API fields that may be stringified JSON arrays are parsed as lists."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return []
        return []

    def _market_label(self, market: dict, outcomes: list) -> str:
        """Derive a readable label for a market when groupItemTitle is missing/empty."""
        label = market.get('groupItemTitle')
        if label:
            return label
        # Fallbacks: question, Yes for binary, or first outcome/slug
        if 'question' in market and market['question']:
            return market['question']
        if outcomes and set(outcomes) == {'Yes', 'No'}:
            return 'Yes'
        if outcomes:
            return outcomes[0]
        return market.get('slug', 'Market')

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
        # Choose search endpoint. Use optimized for keyword searches to mirror site behavior.
        if is_url:
            api_url = f"https://gamma-api.polymarket.com/public-search?q={encoded_slug}"
        else:
            api_url = (
                "https://gamma-api.polymarket.com/public-search?q="
                f"{encoded_slug}&optimized=true&limit_per_type=1&type=events&search_tags=true&search_profiles=true&cache=true"
            )
        
        log.debug(f"Polymarket: Fetching data from API URL: {api_url}")
        
        # Fetch data from API
        response = requests.get(api_url, verify=False)
        response.raise_for_status()
        data = response.json()

        # Fallback to non-optimized endpoint if optimized yields no events
        if (not data or 'events' not in data or not data['events']) and not is_url:
            fallback_url = f"https://gamma-api.polymarket.com/public-search?q={encoded_slug}"
            log.debug(f"Polymarket: Optimized search empty, falling back to: {fallback_url}")
            response = requests.get(fallback_url, verify=False)
            response.raise_for_status()
            data = response.json()

        log.debug(f"Polymarket: API response data: {data}")  # Log the raw API response

        if not data or 'events' not in data or not data['events']:
            return {'title': "No matching event found", 'data': [], 'slug': ''}

        # Find matching event
        if is_url:
            matching_event = next((event for event in data['events'] if event['slug'] == slug.replace(' ', '-')), None)
        else:
            # Prefer the first event that has at least one active and unclosed market.
            # If none, fall back to the top event from the API response.
            events = data.get('events', [])
            matching_event = next(
                (
                    e
                    for e in events
                    if any(m.get('active', True) and not m.get('closed', False) for m in e.get('markets', []))
                ),
                (events[0] if events else None),
            )

        if not matching_event:
            return {'title': "No matching event found", 'data': [], 'slug': ''}

        title = matching_event['title']
        slug = matching_event.get('slug', '')  # Use .get() to avoid KeyError
        markets = matching_event.get('markets', [])

        # Filter out inactive or closed markets (e.g., placeholders without real pricing)
        filtered_markets = [m for m in markets if m.get('active', True) and not m.get('closed', False)]

        # Fallback: if no active and unclosed markets, use the top market from the API response
        if filtered_markets:
            markets = filtered_markets
        else:
            log.debug("Polymarket: No active/unclosed markets; falling back to top market from API response")
            markets = markets[:1]

        # If optimized search omitted clobTokenIds, try to enrich from detailed endpoints
        markets = self._ensure_clob_ids(slug, markets)

        log.debug(f"Polymarket: Matching event found: {title}, slug: {slug}, markets: {markets}")  # Log matching event details

        # Parse market data
        cleaned_data = []
        for market in markets:
            # Normalize fields that sometimes arrive as stringified JSON
            outcomes = self._as_list(market.get('outcomes', []))
            outcome_prices_raw = self._as_list(market.get('outcomePrices', []))
            # Convert prices to floats if present
            outcome_prices = []
            try:
                outcome_prices = [float(p) for p in outcome_prices_raw]
            except Exception:
                outcome_prices = []

            clob_token_ids = self._as_list(market.get('clobTokenIds', []))
            outcome = self._market_label(market, outcomes)

            log.debug(f"Polymarket: Parsing market: {outcome}")  # Log the current market being parsed
            try:
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
                            outcome_prices = [float(yes_price), float(no_price)]
                        elif market.get('lastTradePrice') is not None:
                            yes_price = float(market['lastTradePrice'])
                            no_price = 1 - yes_price
                            outcome_prices = [yes_price, no_price]
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
                            # Ensure clob token id alignment
                        clob_id = clob_token_ids[yes_index] if yes_index < len(clob_token_ids) else None
                        cleaned_data.append((outcome, yes_probability, 'Yes', clob_id))
                    else:
                        probability = yes_probability
                        display_outcome = 'Yes'
                        clob_id = clob_token_ids[yes_index] if yes_index < len(clob_token_ids) else None
                        cleaned_data.append((outcome, probability, display_outcome, clob_id))
                else:
                    # For multi-outcome markets, always use the highest probability
                    max_price_index = outcome_prices.index(max(outcome_prices, key=float))
                    probability = float(outcome_prices[max_price_index])
                    display_outcome = outcomes[max_price_index]
                    clob_id = clob_token_ids[max_price_index] if max_price_index < len(clob_token_ids) else None
                    cleaned_data.append((outcome, probability, display_outcome, clob_id))
            except (KeyError, ValueError, TypeError, IndexError, json.JSONDecodeError) as e:
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

    def _ensure_clob_ids(self, event_slug: str, markets: list) -> list:
        """Ensure markets include clobTokenIds by fetching enriched data when available.

        Tries event-by-slug endpoint first, then per-market by slug.
        Swallows errors and returns markets unchanged on failure.
        """
        try:
            # Quick check: if at least one market already has clobTokenIds, we still try to fill the rest.
            need_fill = [m for m in markets if not self._as_list(m.get('clobTokenIds', []))]
            if not need_fill:
                return markets

            # Attempt: fetch event details by slug
            if event_slug:
                evt_url = f"https://gamma-api.polymarket.com/events?slug={quote(event_slug)}"
                log.debug(f"Polymarket: Enriching markets via event endpoint: {evt_url}")
                r = requests.get(evt_url, verify=False)
                if r.ok:
                    evt = r.json()
                    # Response might be {"events": [...]} or a single event dict
                    evt_obj = None
                    if isinstance(evt, dict) and 'events' in evt and evt['events']:
                        evt_obj = evt['events'][0]
                    elif isinstance(evt, dict) and 'markets' in evt:
                        evt_obj = evt
                    if evt_obj and 'markets' in evt_obj:
                        by_slug = {em.get('slug'): em for em in evt_obj['markets']}
                        for m in markets:
                            if not self._as_list(m.get('clobTokenIds', [])):
                                em = by_slug.get(m.get('slug'))
                                if em and self._as_list(em.get('clobTokenIds', [])):
                                    m['clobTokenIds'] = em.get('clobTokenIds')

            # Per-market enrichment for any still missing
            for m in markets:
                if self._as_list(m.get('clobTokenIds', [])):
                    continue
                mslug = m.get('slug')
                if not mslug:
                    continue
                m_url = f"https://gamma-api.polymarket.com/markets?slug={quote(mslug)}"
                log.debug(f"Polymarket: Enriching market via market endpoint: {m_url}")
                try:
                    rr = requests.get(m_url, verify=False)
                    if not rr.ok:
                        continue
                    mj = rr.json()
                    candidate = None
                    if isinstance(mj, dict) and 'markets' in mj and mj['markets']:
                        candidate = mj['markets'][0]
                    elif isinstance(mj, list) and mj:
                        candidate = mj[0]
                    elif isinstance(mj, dict) and 'clobTokenIds' in mj:
                        candidate = mj
                    if candidate and self._as_list(candidate.get('clobTokenIds', [])):
                        m['clobTokenIds'] = candidate.get('clobTokenIds')
                except Exception:
                    continue
        except Exception as e:
            log.debug(f"Polymarket: _ensure_clob_ids failed: {e}")
        return markets

    def _shorten_url(self, market_url: str) -> str:
        """Attempts to shorten a URL with multiple providers and broad compatibility.

        Tries TinyURL first (Polymarket links are long), then falls back to
        is.gd and da.gd. Returns the original URL on any failure.
        """
        try:
            try:
                # Some pyshorteners versions accept timeout; others don't.
                shortener = pyshorteners.Shortener(timeout=5)
            except TypeError:
                shortener = pyshorteners.Shortener()

            # Preferred provider: TinyURL
            try:
                short_url = shortener.tinyurl.short(market_url)
                log.debug(f"Polymarket: URL shortened via TinyURL -> {short_url}")
                return short_url
            except Exception as e:
                log.debug(f"Polymarket: TinyURL failed -> {e!r}")

            # Fallback: is.gd
            try:
                short_url = shortener.isgd.short(market_url)
                log.debug(f"Polymarket: URL shortened via is.gd -> {short_url}")
                return short_url
            except Exception as e:
                log.debug(f"Polymarket: is.gd failed -> {e!r}")

            # Fallback: da.gd
            try:
                short_url = shortener.dagd.short(market_url)
                log.debug(f"Polymarket: URL shortened via da.gd -> {short_url}")
                return short_url
            except Exception as e:
                log.debug(f"Polymarket: da.gd failed -> {e!r}")
        except Exception as e:
            log.debug(f"Polymarket: URL shortener setup failed -> {e!r}")
        return market_url

    def _get_price_change(self, clob_token_id, current_price):
        """Fetches and calculates the 24-hour price change for a given clob_token_id."""
        if not clob_token_id:
            return None
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
        # Skip inactive or closed markets
        if not market.get('active', True) or market.get('closed', False):
            log.debug(
                "Polymarket: Skipping inactive/closed market: %s",
                market.get('groupItemTitle', market.get('slug', 'unknown')),
            )
            return []
        outcomes = self._as_list(market.get('outcomes', []))
        outcome_prices_raw = self._as_list(market.get('outcomePrices', []))
        try:
            outcome_prices = [float(p) for p in outcome_prices_raw]
        except Exception:
            outcome_prices = []
        clob_token_ids = self._as_list(market.get('clobTokenIds', []))
        outcome = self._market_label(market, outcomes)
        log.debug(f"Polymarket: Parsing market: {outcome}")
        try:
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
            log.debug(
                f"Polymarket: result summary -> title={result.get('title')}, slug={result.get('slug')}, count={len(result.get('data', []))}"
            )
            if result['data']:
                filtered_data = result['data'][:20]
                log.debug(f"Polymarket: formatting {len(filtered_data)} items")
                
                # Format output
                output = f"\x02{result['title']}\x02: "
                for item in filtered_data:
                    try:
                        outcome, probability, display_outcome, clob_token_id = item
                        log.debug(f"Polymarket: item -> outcome={outcome}, prob={probability}, clob={clob_token_id}")
                        price_change = self._get_price_change(clob_token_id, probability) if clob_token_id else None
                        change_str = (
                            f" ({'⬆️' if price_change > 0 else '🔻'}{abs(price_change)*100:.1f}%)"
                            if price_change is not None and price_change != 0
                            else ""
                        )
                        output += f"{outcome}: \x02{probability:.0%}{change_str}{' (' + display_outcome + ')' if display_outcome != 'Yes' else ''}\x02 | "
                    except Exception as e:
                        log.exception(f"Polymarket: formatting error for item {item!r}: {e!r}")
                        continue
                
                output = output.rstrip(' | ')
                
                # Generate URL
                if is_url:
                    market_url = query
                else:
                    slug = result.get('slug', '')
                    market_url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
                log.debug(f"Polymarket: market_url={market_url}")
                
                # Try to shorten URL (TinyURL with fallbacks); append full URL if it fails
                short_url = self._shorten_url(market_url)
                if short_url == market_url:
                    log.warning("Polymarket: URL shortening unavailable; using full URL.")
                output += f" | {short_url}"
                
                log.debug(f"Polymarket: Sending IRC reply: {output}")
                
                irc.reply(output, prefixNick=False)
            else:
                irc.reply(result['title'])
        except requests.RequestException as e:
            irc.reply(f"Error fetching data from Polymarket: {str(e)}")
        except json.JSONDecodeError:
            irc.reply("Error parsing data from Polymarket. The API response may be invalid.")
        except Exception as e:
            # Include full stack trace to aid debugging in production logs
            log.exception(f"Polymarket plugin error: {e!r}")
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
                
                price_change = self._get_price_change(clob_token_id, probability) if clob_token_id else None
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
