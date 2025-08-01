# OpenRouter Limnoria Plugin

A Limnoria/Supybot plugin that lets your IRC bot converse with any **OpenAI‑compatible chat‑completion endpoint** (e.g. [OpenRouter](https://openrouter.ai/), OpenAI, Groq, etc.).

Initially based on [Oddluck's ChatGPT plugin](https://github.com/progval/oddluck-limnoria-plugins/tree/master/ChatGPT)

---

## Installation

1. Drop `OpenRouter/` into your bot’s `plugins/` directory and reload:

   ```irc
   @load OpenRouter
   ```
2. Install the OpenAI Python SDK (needed even for non‑OpenAI endpoints):

   ```shell
   pip install openai
   ```
3. Obtain an API key from your provider (for OpenRouter: [https://openrouter.ai/keys](https://openrouter.ai/keys)).

---

## Quick configuration

```irc
# Mandatory: your key and base URL
@config plugins.openrouter.api_key   sk‑live_your_key_here
@config plugins.openrouter.base_url  https://openrouter.ai/api/v1

# Sensible defaults
@config plugins.openrouter.model          gpt‑4o-mini
@config plugins.openrouter.temperature    0.7
@config plugins.openrouter.top_p          1.0
@config plugins.openrouter.max_history    10   # messages kept per channel
```

Run `@config list plugins.openrouter` to see every toggle (nick‑prefixing, history size, etc.).

---

## Command syntax

```irc
@openrouter chat [--model <name>] [--temperature <f>] [--top_p <f>]
                 [--max_tokens <n>] [--presence_penalty <f>]
                 [--frequency_penalty <f>] -- <prompt>
```

* Flags are **optional**—if omitted, the channel’s configured defaults apply.
* Use `--` to mark where flags end and your prompt begins (unless you supply no flags at all).
* `--temp` is accepted as a shorthand for `--temperature`.

### Examples

```irc
# Quick ask with defaults
a> @openrouter chat Hello, what’s the news?

# Specify a different model and sampling temperature
b> @openrouter chat --model x‑ai/grok‑2‑1212 --temp 0.3 -- Summarise today in haiku

# Top‑p sampling and hard token limit
c> @openrouter chat --top_p 0.8 --max_tokens 64 -- Give me a dad joke
```

---

## Creating friendly shortcuts

Use Limnoria’s **Alias** plugin so users don’t have to remember model names:

```irc
@alias add grok "openrouter chat --model x‑ai/grok‑2‑1212 -- $*"
```

Now `@grok How do rockets work?` maps to the full OpenRouter command.

---

## Optional features

| Setting                           | Description                                                                           |
| --------------------------------- | ------------------------------------------------------------------------------------- |
| `plugins.openrouter.nick_include` | Prepend the caller’s nick to their prompt (handy for multi‑user channels).            |
| `plugins.openrouter.nick_strip`   | Strip the bot’s own nick from the assistant’s replies.                                |
| `plugins.openrouter.reply_intact` | If *true*, send each line exactly; if *false* (default) collapse to one line.         |
| `plugins.openrouter.prompt`       | System prompt injected at the start of every conversation; `$botnick` is substituted. |

---

## Troubleshooting

* **“Unknown option”** – you mistyped a flag; run the command without flags to see usage.
* **Rate‑limit errors** – check your provider’s dashboard and consider lowering history or `max_tokens`.
* **Nothing happens** – ensure `plugins.openrouter.enabled` is `True` for the channel.

