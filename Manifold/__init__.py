"""
Manifold: Fetches and displays odds from Manifold.markets
"""

import supybot
import supybot.world as world

__version__ = "0.1"
__author__ = supybot.Author("Your Name", "Your Email", "Your Website")
__contributors__ = {}
__url__ = ''

from . import config
from . import plugin
from importlib import reload
reload(config)
reload(plugin)

if world.testing:
    from . import test

Class = plugin.Class
configure = config.configure
