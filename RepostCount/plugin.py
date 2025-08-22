import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.ircmsgs as ircmsgs
import supybot.conf as conf
import supybot.world as world
import time
import re
from urllib.parse import urlparse, urlunsplit, parse_qs, urlencode
from supybot import registry
# import pprint  # For pretty printing in debug logs
import supybot.ircdb as ircdb

class RepostCount(callbacks.Plugin):
    """
    A plugin to track and count reposts of links in a specified channel.
    """

    def __init__(self, irc):
        self.__parent = super(RepostCount, self)
        self.__parent.__init__(irc)
        self.filename = conf.supybot.directories.data.dirize(self.name() + '.db')
        self.link_filename = conf.supybot.directories.data.dirize(self.name() + '_links.db')
        self.alias_filename = conf.supybot.directories.data.dirize(self.name() + '_aliases.db')
        # Loads existing repost counts, link database, and alias map
        self.user_repost_count, self.link_database, self.alias_map = self.load_data()
        self.domains_ignore_params = ['twitter.com', 'x.com', 'twimg.com', 'nytimes.com']

    def load_data(self):
        """Load the user repost count, link database, and alias map from files."""
        try:
            with open(self.filename, 'r') as f:
                user_repost_count = eval(f.read())
        except Exception:
            user_repost_count = {}

        try:
            with open(self.link_filename, 'r') as f:
                link_database = eval(f.read())
        except Exception:
            link_database = {}

        try:
            with open(self.alias_filename, 'r') as f:
                alias_map = eval(f.read())
        except Exception:
            alias_map = {}

        # Normalize keys to lowercase and fold counts through alias map
        def canonical(n, amap):
            n = (n or '').lower()
            seen = set()
            while n in amap and n not in seen:
                seen.add(n)
                n = amap[n]
            return n

        # Lowercase all keys first
        tmp_counts = {}
        for k, v in user_repost_count.items():
            lk = (k or '').lower()
            tmp_counts[lk] = tmp_counts.get(lk, 0) + int(v or 0)

        # Fold via alias map
        final_counts = {}
        for k, v in tmp_counts.items():
            ck = canonical(k, alias_map)
            final_counts[ck] = final_counts.get(ck, 0) + v

        return final_counts, link_database, alias_map

    def save_data(self):
        """Save the user repost count, link database, and alias map to files."""
        with open(self.filename, 'w') as f:
            f.write(repr(self.user_repost_count))

        with open(self.link_filename, 'w') as f:
            f.write(repr(self.link_database))

        with open(self.alias_filename, 'w') as f:
            f.write(repr(self.alias_map))

    def die(self):
        """Save data when the plugin is unloaded."""
        self.save_data()
        self.__parent.die()

    def _strip_url_params(self, url):
        """Remove query parameters from URLs of specified domains."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        base_domain = domain[4:] if domain[:4] == 'www.' else domain
        
        if base_domain in self.domains_ignore_params:
            # For specified domains, remove all parameters
            self.log.debug(f"Stripping params from URL: {url}")
            clean_url = urlunsplit(('http', parsed.netloc.lower(), parsed.path.lower(), '', ''))
        else:
            # For other domains, keep all parameters
            clean_url = urlunsplit(('http', parsed.netloc.lower(), parsed.path.lower(), parsed.query.lower(), ''))
        
        self.log.debug(f"Parsed URL: {parsed}, Domain: {domain}, Clean URL: {clean_url}")       
        return clean_url

    def _extract_url(self, text):
        """Extract the first URL from a given text."""
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        match = re.search(url_pattern, text)
        return match.group(0) if match else None

    def _purge_old_links(self):
        """Remove links older than 12 hours from the database."""
        current_time = time.time()
        old_links = [url for url, (_, timestamp) in self.link_database.items() 
                     if current_time - timestamp > 12 * 3600]
        for url in old_links:
            del self.link_database[url]
            self.log.debug(f"Removed old link from database: {url}")
        
        if old_links:
            self.save_data()  # Save after purging

    def _canonical_nick(self, nick):
        """Return the canonical (lowercased/aliased) form of a nick."""
        n = (nick or '').lower()
        seen = set()
        while n in self.alias_map and n not in seen:
            seen.add(n)
            n = self.alias_map[n]
        return n

    def _merge_alias(self, primary, alias):
        """Alias 'alias' to 'primary' and merge counts into primary."""
        p = self._canonical_nick(primary)
        a = self._canonical_nick(alias)

        if p == a:
            return False, "Primary and alias resolve to the same nick."

        # Update alias mapping
        self.alias_map[a] = p

        # Merge historical counts
        if a in self.user_repost_count:
            self.user_repost_count[p] = self.user_repost_count.get(p, 0) + self.user_repost_count.get(a, 0)
            del self.user_repost_count[a]

        # Also re-fold any existing aliases that might have pointed to 'a'
        # to now point to 'p' (path compression)
        for k, v in list(self.alias_map.items()):
            if v == a:
                self.alias_map[k] = p

        self.save_data()
        return True, f"Aliased {alias} -> {primary} and merged counts."

    def _remove_alias(self, alias):
        """Remove an alias mapping for a nick (does not split counts)."""
        a = (alias or '').lower()
        if a in self.alias_map:
            del self.alias_map[a]
            self.save_data()
            return True, f"Removed alias for {alias}."
        return False, f"No alias found for {alias}."

    def doPrivmsg(self, irc, msg):
        """Handle incoming messages and check for reposts."""
        channel = msg.args[0]
        
        if irc.isChannel(channel) and channel == self.registryValue('channel'):
            text = msg.args[1]
            url = self._extract_url(text)
            
            if url:
                self._purge_old_links()
                clean_url = self._strip_url_params(url)
                nick = msg.nick
                current_time = time.time()

                if clean_url in self.link_database:
                    original_poster, post_time = self.link_database[clean_url]
                    
                    # Compare canonical nicks to avoid counting case or aliases
                    if self._canonical_nick(nick) != self._canonical_nick(original_poster):
                        time_diff = current_time - post_time
                        hours, remainder = divmod(time_diff, 3600)
                        minutes, _ = divmod(remainder, 60)
                        
                        cnick = self._canonical_nick(nick)
                        self.user_repost_count[cnick] = self.user_repost_count.get(cnick, 0) + 1
                        
                        irc.reply(
                            f"That link was already posted by {original_poster} {int(hours)}h {int(minutes)}m ago. "
                            f"Repost count for {nick} is now {self.user_repost_count[cnick]}.",
                            prefixNick=False,
                        )
                        
                        # Log the repost
                        self.log.info(f"Repost detected: {nick} reposted {clean_url} originally posted by {original_poster}")
                    else:
                        self.link_database[clean_url] = (nick, current_time)
                        self.log.debug(f"Updated timestamp for existing link: {clean_url} posted by {nick}")
                else:
                    self.link_database[clean_url] = (nick, current_time)
                    self.log.debug(f"Added new link to database: {clean_url} posted by {nick}")

                self.save_data()  # Save after any modifications

    def reposters(self, irc, msg, args, nick=None):
        """[<nick>]

        Shows the top 15 reposters leaderboard. If <nick> is provided, shows that user's repost count and rank.
        """
        if not self.user_repost_count:
            irc.reply("No reposts have been recorded yet.", prefixNick=False)
            return

        # Sort users by repost count in descending order
        sorted_reposters = sorted(self.user_repost_count.items(), key=lambda x: x[1], reverse=True)

        if nick:
            cnick = self._canonical_nick(nick)
            if cnick in self.user_repost_count:
                count = self.user_repost_count[cnick]
                rank = next(i for i, (user, _) in enumerate(sorted_reposters, 1) if user == cnick)
                irc.reply(f"{nick} has committed {count} repost{'s' if count != 1 else ''}, currently ranked {rank} among reposters.", prefixNick=False)
            else:
                irc.reply(f"{nick} has not been caught linking any reposts.", prefixNick=False)
        else:
            # Get the top 15 reposters
            top_reposters = sorted_reposters[:15]

            # Format the leaderboard
            leaderboard = ["Top 15 Reposters:"]
            for user, count in top_reposters:
                leaderboard.append(f"{user}:{count}")

            # Join the leaderboard entries and reply
            irc.reply(" ".join(leaderboard), prefixNick=False)

    reposters = wrap(reposters, [optional('text')])

    def purge(self, irc, msg, args, option):
        """[<nickname>|all]

        Purges the entire repost list, or the repost count for a specific nickname. 
        Limited to the bot owner.
        """
        if not ircdb.checkCapability(msg.prefix, 'owner'):
            irc.error("This command is limited to the bot owner.", Raise=True)
        
        if option == 'all':
            self.user_repost_count.clear()
            self.link_database.clear()
            irc.reply("All repost data has been purged.")
        elif option:
            copt = self._canonical_nick(option)
            if copt in self.user_repost_count:
                del self.user_repost_count[copt]
                irc.reply(f"Repost count for {option} has been purged.")
            else:
                irc.error(f"No repost data found for {option}.")
        else:
            irc.error("Please specify 'all' or a nickname to purge.")
        
        self.save_data()

    purge = wrap(purge, ['owner', optional('text')])

    def repost(self, irc, msg, args, nick):
        """<nickname>

        Shows the current repost count for the specified nickname.
        """
        cnick = self._canonical_nick(nick)
        if cnick in self.user_repost_count:
            count = self.user_repost_count[cnick]
            irc.reply(f"{nick} has caused {count} repost{'s' if count != 1 else ''}.")
        else:
            irc.reply(f"{nick} has not caused any reposts.")

    repost = wrap(repost, ['text'])

    def aliasadd(self, irc, msg, args, primary, alias):
        """<primary> <alias>

        Aliases <alias> to <primary> and merges their repost counts. Limited to the bot owner.
        """
        if not ircdb.checkCapability(msg.prefix, 'owner'):
            irc.error("This command is limited to the bot owner.", Raise=True)

        ok, message = self._merge_alias(primary, alias)
        if ok:
            irc.reply(message)
        else:
            irc.error(message)

    aliasadd = wrap(aliasadd, ['owner', 'something', 'something'])

    def aliasrm(self, irc, msg, args, alias):
        """<alias>

        Removes an alias mapping. Counts remain with the primary nick. Limited to the bot owner.
        """
        if not ircdb.checkCapability(msg.prefix, 'owner'):
            irc.error("This command is limited to the bot owner.", Raise=True)

        ok, message = self._remove_alias(alias)
        if ok:
            irc.reply(message)
        else:
            irc.error(message)

    aliasrm = wrap(aliasrm, ['owner', 'something'])

    def aliases(self, irc, msg, args):
        """
        Lists current alias mappings (alias -> primary). Limited to the bot owner.
        """
        if not ircdb.checkCapability(msg.prefix, 'owner'):
            irc.error("This command is limited to the bot owner.", Raise=True)

        if not self.alias_map:
            irc.reply("No aliases configured.")
            return

        pairs = [f"{a}->{p}" for a, p in sorted(self.alias_map.items())]
        irc.reply("Aliases: " + " ".join(pairs))

    aliases = wrap(aliases, ['owner'])

Class = RepostCount

# Register the plugin
conf.registerPlugin('RepostCount')
conf.registerChannelValue(conf.supybot.plugins.RepostCount, 'channel',
    registry.String('', """The channel where the RepostCount should be active."""))
