"""
Limnoria plugin for displaying Kalshi prediction market information.
"""

import supybot
import supybot.world as world

# Use this for the version of this plugin.  You may wish to put a CVS keyword
# in here if you're keeping the plugin in CVS or some similar system.
__version__ = "1.0.0"

__author__ = supybot.Author("Your Name", "YourName", "your.email@example.com")

# This is a dictionary mapping supybot.Author instances to lists of
# contributions.
__contributors__ = {}

# This is a url where the most recent plugin package can be downloaded.
__url__ = ''

# Load our configuration
from . import config

# Load our plugin class
from . import plugin

if world.testing:
    from . import test

# This is the entry point for the plugin
Class = plugin.Kalshi

# This is used by the setup.py script
configure = config.configure
