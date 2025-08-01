import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.log as log
import requests
import json
from urllib.parse import quote
import pyshorteners
from requests.exceptions import Timeout, ConnectionError

class Manifold(callbacks.Plugin):
    """Fetches and displays odds from Manifold.markets"""

    def _fetch_manifold_data(self, query, max_results=7):
        """
        Fetch and parse Manifold.markets data from API.
        
        Args:
            query (str): Search term or URL
            max_results (int): Maximum number of outcomes to return

        Returns:
            dict: Parsed event data with title and outcomes
        """
        # Prepare API query
        encoded_query = quote(query)
        search_api_url = f"https://api.manifold.markets/v0/search-markets?term={encoded_query}&sort=liquidity&filter=open&contractType=ALL&limit=1"
        
        log.debug(f"Manifold: Fetching data from API URL: {search_api_url}")
        
        # Fetch data from search API
        response = requests.get(search_api_url)
        response.raise_for_status()
        search_data = response.json()

        if not search_data:
            return {'title': "No matching market found", 'data': []}

        market = search_data[0]
        outcome_type = market['outcomeType']
        
        if outcome_type not in ['BINARY', 'MULTIPLE_CHOICE']:
            return {'title': "Unsupported market type", 'data': []}

        title = market['question']
        volume = market['volume']
        bettors = market['uniqueBettorCount']
        url = market['url']
        
        if outcome_type == 'BINARY':
            # Simple yes/no market
            probability = market['probability']
            data = [('Yes', probability, volume)]
        else:
            # Multiple choice market
            slug = market['slug']
            market_api_url = f"https://api.manifold.markets/v0/slug/{slug}"
            
            log.debug(f"Manifold: Fetching market data from API URL: {market_api_url}")
            
            # Fetch data from market API
            market_response = requests.get(market_api_url)
            market_response.raise_for_status()
            market_data = market_response.json()
            
            answers = market_data['answers']
            
            def answer_score(answer):
                prob = answer['probability']
                prob_change = answer['probChanges']['day']
                
                # Prioritize unresolved answers (upcoming games)
                if 'resolution' not in answer:
                    return 3
                
                # Recent results (with probability changes in the last day)
                if prob_change != 0:
                    return 2
                
                # Older results
                return 1

            # Filter answers with at least 1% probability
            valid_answers = [a for a in answers if a['probability'] >= 0.01]

            # Sort answers by score (descending) and then by probability (descending)
            sorted_answers = sorted(valid_answers, key=lambda x: (-answer_score(x), -x['probability']))

            # Take top max_results
            top_answers = sorted_answers[:max_results]

            data = [(answer['text'], answer['probability'], volume) for answer in top_answers]

        result = {
            'title': title,
            'data': data,
            'volume': volume,
            'bettors': bettors,
            'url': url
        }
        
        log.debug(f"Manifold: Parsed market data: {result}")
        
        return result

    def manifold(self, irc, msg, args, query):
        """<query>
        
        Fetches and displays the current odds from Manifold.markets. 
        <query> can be a search term or a Manifold.markets URL.
        """
        try:
            result = self._fetch_manifold_data(query)
            if result['data']:
                # # Format volume (currently unused)
                # volume = result['volume']
                # if volume >= 1000000:
                #     volume_str = f"{volume/1000000:.0f}M"
                # elif volume >= 1000:
                #     volume_str = f"{volume/1000:.0f}k"
                # else:
                #     volume_str = f"{volume:.0f}"

                # Shorten the URL

                try:
                    shortener = pyshorteners.Shortener(timeout=5)
                    printed_url = shortener.tinyurl.short(result['url'])
                except (Timeout, ConnectionError, pyshorteners.exceptions.ShorteningErrorException) as e:
                    log.warning(f"URL shortening failed: {str(e)}. Using full URL.")
                    printed_url = result['url']

                # Format output
                output = f"\x02{result['title']}\x02: "
                output += " | ".join([f"{outcome}: \x02{probability:.1%}\x02" for outcome, probability, _ in result['data']])
                output += f" | {printed_url}"
                
                log.debug(f"Manifold: Sending IRC reply: {output}")
                
                # Reply in the same channel, without nick prefix
                irc.reply(output, prefixNick=False)
            else:
                irc.reply("Unable to fetch odds or no valid data found.")
        except Exception as e:
            irc.reply(f"An error occurred: {str(e)}")

    manifold = wrap(manifold, ['text'])

Class = Manifold

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
