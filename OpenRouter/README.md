# OpenRouter Limnoria Plugin

A tiny Limnoria/Supybot plugin that turns your IRC bot into a front‑end for any **OpenAI‑compatible chat‑completion service** (OpenRouter, OpenAI, Groq, etc.).

---

## Installation

### PluginDownloader:
`@plugindownloader install Nelluk OpenRouter`

`@load OpenRouter`

### Manual:
1. Copy the `OpenRouter/` directory into `plugins/` and reload the bot:

   ```irc
   @load OpenRouter
   ```
2. Install the OpenAI Python SDK (still required even if you’re not using OpenAI):

   ```bash
   pip install openai
   ```
3. Grab an API key from your provider (e.g. [https://openrouter.ai/keys](https://openrouter.ai/keys)).

---

## Basic configuration

```irc
# Required
@config plugins.openrouter.api_key   sk‑live_your_key_here
@config plugins.openrouter.base_url  https://openrouter.ai/api/v1  # or https://api.openai.com/v1/
@config plugins.openrouter.prompt  You are an IRC bot. Be concise, helpful, and accurate.

# Common tweaks
@config plugins.openrouter.model          deepseek/deepseek-chat-v3-0324:free  # default model
@config plugins.openrouter.temperature    0.7                                  # sampling temperature
@config plugins.openrouter.max_history    10                                   # turns kept in memory
@config plugins.openrouter.max_completion_tokens 2000                          # some models require this parameter

# Web search (new)
#   web_mode: off | auto | always | optin
#   web_engine: auto | native | exa
#   web_search_context_size: low | medium | high
@config plugins.openrouter.web_mode auto
@config plugins.openrouter.web_engine auto
@config plugins.openrouter.web_search_context_size medium
@config plugins.openrouter.web_max_results 5
@config plugins.openrouter.web_search_prompt "Use web results to answer. Be concise (2-3 sentences). Do not include citations or URLs unless explicitly asked."
@config plugins.openrouter.web_show_sources False

# Conversation isolation (new)
#   channel         – one shared thread per channel
#   channel+model   – separate thread per model (default)
#   channel+alias   – separate thread per command alias
@config plugins.openrouter.contextScope   channel+model
```

Run `@config list plugins.openrouter` to explore all options.

---

## Command

```irc
@openrouter chat [--model <name>] [--temperature <f>] [--top_p <f>]
                 [--max_completion_tokens <n>] [--max_tokens <n>]
                 [--presence_penalty <f>]
                 [--frequency_penalty <f>] -- <prompt>
```

* Flags override the channel‑level defaults for this single call.
* Use `--` to mark where flags end and your prompt begins.
* Token limit precedence (only one is sent):
  1) CLI `--max_completion_tokens` > 2) CLI `--max_tokens` >
  3) channel `max_completion_tokens` (> 0) > 4) channel `max_tokens`.

### Example

```irc
@openrouter chat --model x‑ai/grok‑2‑1212 --temp 0.3 -- Summarise today in haiku
```

### Web search usage (new)

Auto mode runs search when the prompt looks time‑sensitive (e.g. “latest”,
“today”, “price”, “weather”, or a YYYY‑MM‑DD date). You can also force it
per message:

```irc
# Force search for a single prompt
@openrouter chat --web -- What’s the latest Nvidia driver?

# Force no search for a single prompt
@openrouter chat --no-web -- Explain recursion
```

Search engines:

```irc
@config plugins.openrouter.web_engine auto
@config plugins.openrouter.web_engine native
@config plugins.openrouter.web_engine exa
```

Show sources (appends a “Sources:” line to replies):

```irc
@config plugins.openrouter.web_show_sources True
```

Current date is always injected into the system prompt to reduce stale‑date
responses. No config required.

---

## Handy aliases

Create shortcuts so users don’t have to remember long model names:

```irc
@alias add grok "openrouter chat --model x‑ai/grok‑2‑1212 -- $*"
```

If you define several aliases, set `contextScope` to `channel+model` or `channel+alias` so each keeps its own history.

---

## OpenAI/endpoint compatibility

- The plugin now supports both `max_tokens` and `max_completion_tokens` and will
  prefer `max_completion_tokens` when provided. This improves compatibility with
  providers or models that require the newer parameter while remaining
compatible with OpenRouter and other OpenAI‑compatible chat‑completion
endpoints that accept `max_tokens`.

---

## Model restrictions (blacklist)

Admins can block specific models globally. By default, `openai/o1-pro` is
blocked. Any attempt to chat with a blacklisted model returns an error and the
request is not sent to the API.

```irc
# View the blacklist (space‑separated, case‑insensitive)
@config get plugins.openrouter.models_blacklist

# Set or extend the blacklist
@config set plugins.openrouter.models_blacklist "openai/o1-pro another/model-id"

# Example: this will error and not call the API
@openrouter chat --model openai/o1-pro -- hello
```
