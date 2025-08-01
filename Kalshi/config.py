import supybot.conf as conf
import supybot.registry as registry

def configure(advanced):
    from supybot.questions import expect, anything, something, yn
    conf.registerPlugin('Kalshi', True)

class KalshiConfig(registry.Group):
    """Configuration for the Kalshi plugin."""
    pass

Kalshi = conf.registerPlugin('Kalshi')
