import supybot.conf as conf
import supybot.registry as registry

def configure(advanced):
    from supybot.questions import expect, anything, something, yn
    conf.registerPlugin('RepostCount', True)

RepostCount = conf.registerPlugin('RepostCount')

conf.registerChannelValue(
    RepostCount,
    'channel',
    registry.String('', """The channel where the RepostCount should be active."""),
)

conf.registerGlobalValue(
    RepostCount,
    'ignoredNicks',
    registry.SpaceSeparatedListOfStrings(
        [],
        """Space-separated nicks to ignore for repost penalties/replies (case-insensitive raw nick match).""",
    ),
)
