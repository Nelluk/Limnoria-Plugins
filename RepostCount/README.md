# RepostCount Plugin for Limnoria

## Description

RepostCount is a plugin for the Limnoria IRC bot that tracks and counts reposts of links in a specified channel. It helps maintain channel quality by alerting users when they post links that have already been shared.

## Features

- Tracks posted links in a specified channel
- Detects when a link is reposted
- Counts the number of reposts per user
- Ignores query parameters in URLs from certain domains to avoid false positives
- Automatically purges links older than 12 hours from its database

## Installation

1. Copy the `RepostCount` folder to your Limnoria plugins directory.
2. Load the plugin:
   ```
   @load RepostCount
   ```

## Configuration

Before using the plugin, you need to set the channel where it should be active:

```
@set RepostCount.channel #yourchannel
```

## Usage

- The plugin will automatically track links posted in the specified channel.
- It will reply to each link with the number of reposts it has received.

## Commands

### @reposters [<nick>]

Shows the top 15 reposters leaderboard or information about a specific user's reposts.

Usage:
```

@reposters
@reposters <nick>
```

Without arguments, this command displays a single-line list of the top 15 users who have reposted links, along with their repost counts, ordered from highest to lowest count.

If a <nick> is provided, it shows that user's repost count and their current rank among reposters.

Example outputs:
```

Top 15 Reposters: User1:10 User2:8 User3:7 User4:5 User5:4 ...
User1 has caused 10 reposts, currently ranked 1 among reposters.
User6 has caused 1 repost, currently ranked 12 among reposters.
User7 has not caused any reposts.
```

### @repost <nick>

Shows the current repost count for the specified nickname.

Usage:
```

@repost <nick>
```

Example output:
```

User1 has caused 10 reposts.
User2 has not caused any reposts.
```

## License

This plugin is licensed under the MIT License.