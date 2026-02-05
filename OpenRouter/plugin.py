###
# Copyright (c) 2025 Nelluk
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

from supybot import utils, plugins, ircutils, callbacks
from supybot.commands import *  # getopts, rest, somethingWithoutSpaces, etc.
from supybot.i18n import PluginInternationalization
import re
from collections import defaultdict
from datetime import date
from openai import OpenAI
import json

_ = PluginInternationalization("OpenRouter")


class OpenRouter(callbacks.Plugin):
    """Use an OpenAI‑compatible Chat Completion API via OpenRouter (or any compatible endpoint)."""
    threaded = True

    # ---------------------------- lifecycle ---------------------------- #

    def __init__(self, irc):
        super().__init__(irc)
        # maps (channel, qualifier) → list[dict]
        self.history = defaultdict(list)

    # ---------------------------- helpers ----------------------------- #

    def _get_param(self, opts, name, channel):
        """Return `name` from opts if present, else the channel registry default."""
        if name == "temperature" and "temp" in opts:
            return opts["temp"]
        return opts.get(name, self.registryValue(name, channel))

    def _history_key(self, channel, model_name, alias_name):
        """Return the key object used to segregate chat histories."""
        scope = self.registryValue("contextScope", channel).lower()
        if scope == "channel":
            return (channel, None)
        if scope == "channel+alias":
            return (channel, alias_name or model_name)
        # default ⇒ channel+model
        return (channel, model_name)

    def _append_history(self, key, user_msg, assistant_msg, max_history):
        hist = self.history[key]
        hist.extend([
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ])
        # trim if needed
        excess = max(len(hist) - max_history * 2, 0)
        if excess:
            del hist[:excess]

    def _is_time_sensitive(self, text):
        if not text:
            return False
        lowered = text.lower()
        keywords = [
            "latest",
            "today",
            "yesterday",
            "tomorrow",
            "this week",
            "current",
            "breaking",
            "news",
            "price",
            "stock",
            "weather",
            "score",
            "release",
            "ceo",
            "as of",
            "right now",
        ]
        if any(k in lowered for k in keywords):
            return True
        # YYYY-MM-DD
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", lowered):
            return True
        return False

    # ---------------------------- command ----------------------------- #

    _OPTSPEC = {
        "model": "somethingWithoutSpaces",
        "temperature": "float",
        "temp": "float",              # alias for convenience
        "top_p": "float",
        "max_completion_tokens": "int",
        "max_tokens": "int",
        "presence_penalty": "float",
        "frequency_penalty": "float",
        "web": "",
        "no-web": "",
    }

    @wrap([
        getopts(_OPTSPEC),
        rest("text"),
    ])
    def chat(self, irc, msg, args, opts, prompt):
        """[--model <name>] [--temperature <f>] … -- <prompt>

        Sends <prompt> to the configured API. Flags override the channel's
        defaults for this single call.
        """

        # list → dict and strip any accidental leading dashes
        opts = {opt.lstrip("-"): val for opt, val in opts}

        channel = msg.channel if irc.isChannel(msg.channel) else msg.nick
        if not self.registryValue("enabled", channel):
            return

        prompt_for_llm = (
            f"{msg.nick}: {prompt}"
            if self.registryValue("nick_include", channel)
            else prompt
        )

        # --------------------------------------------------------------- #
        # Build API request
        # --------------------------------------------------------------- #
        client = OpenAI(
            api_key=self.registryValue("api_key"),
            base_url=self.registryValue("base_url"),
        )

        system_prompt = self.registryValue("prompt", channel).replace(
            "$botnick", irc.nick
        )
        system_prompt = f"Current date: {date.today().isoformat()}\n{system_prompt}"

        model_name = opts.get("model", self.registryValue("model", channel))

        # Disallow blacklisted models
        try:
            blacklist = {m.lower() for m in (self.registryValue("models_blacklist") or [])}
        except Exception:
            blacklist = set()
        if isinstance(model_name, str) and model_name.lower() in blacklist:
            irc.error(
                f"Model '{model_name}' is disallowed by configuration. Choose a different model.")
            return

        # alias name is the first token after the bot nick, e.g. in "@grok" or "@claude"
        alias_name = msg.args[1].split()[0] if msg.args and len(msg.args) > 1 else None
        key = self._history_key(channel, model_name, alias_name)
        max_history = self.registryValue("max_history", channel)

        request_params = {
            "model": model_name,
            "messages": self.history[key][-max_history:] + [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_for_llm},
            ],
            "user": msg.nick,
        }

        for pname in (
            "temperature",
            "top_p",
            # token limit handled separately to support both names
            "presence_penalty",
            "frequency_penalty",
        ):
            if pname == "frequency_penalty" and "gemini" in model_name.lower():
                continue
            request_params[pname] = self._get_param(opts, pname, channel)

        # Choose exactly one token limit parameter, preferring max_completion_tokens
        mct = self._get_param(opts, "max_completion_tokens", channel)
        if isinstance(mct, int) and mct > 0:
            request_params["max_completion_tokens"] = mct
        else:
            mt = self._get_param(opts, "max_tokens", channel)
            if isinstance(mt, int) and mt > 0:
                request_params["max_tokens"] = mt

        # --------------------------------------------------------------- #
        # Web search plugin options
        # --------------------------------------------------------------- #
        web_mode = str(self.registryValue("web_mode", channel)).lower()
        web_force_on = "web" in opts
        web_force_off = "no-web" in opts
        if web_force_off:
            use_web = False
        elif web_mode == "off":
            use_web = False
        elif web_mode == "always":
            use_web = True
        elif web_mode == "optin":
            use_web = web_force_on
        else:
            use_web = web_force_on or self._is_time_sensitive(prompt)

        web_search_options = None
        if use_web:
            engine = str(self.registryValue("web_engine", channel)).lower()
            search_context_size = str(
                self.registryValue("web_search_context_size", channel)
            ).lower()
            try:
                max_results = int(self.registryValue("web_max_results", channel))
            except Exception:
                max_results = 5
            search_prompt = self.registryValue("web_search_prompt", channel)
            if max_results < 1:
                max_results = 1
            if max_results > 10:
                max_results = 10

            web_search_options = {
                "search_context_size": search_context_size,
                "max_results": max_results,
            }
            if search_prompt:
                web_search_options["search_prompt"] = search_prompt
            if engine in ("native", "exa"):
                web_search_options["engine"] = engine

            extra_body = request_params.get("extra_body") or {}
            extra_body["plugins"] = [{"id": "web"}]
            extra_body["web_search_options"] = web_search_options
            request_params["extra_body"] = extra_body

        # --------------------------------------------------------------- #
        # Log exact request payload (always on)
        # --------------------------------------------------------------- #
        try:
            scope = self.registryValue("contextScope", channel)
            history_slice = self.history[key][-max_history:]
            history_count = len(history_slice)
            payload_json = json.dumps(request_params, ensure_ascii=False, separators=(",", ":"))
            self.log.info(
                f"OpenRouter request → base_url={self.registryValue('base_url')} "
                f"model={model_name} scope={scope} key={key!r} "
                f"history_used={history_count} messages_total={len(request_params.get('messages', []))} "
                f"use_web={use_web} web_mode={web_mode} "
                f"web_search_options={web_search_options if use_web else 'omitted'} "
                f"payload={payload_json}"
            )
        except Exception as e:
            # Fallback to repr if JSON serialization fails for any reason
            self.log.info(
                f"OpenRouter request (repr fallback due to {e}): {request_params!r}"
            )

        # --------------------------------------------------------------- #
        # Call the API
        # --------------------------------------------------------------- #
        completion = client.chat.completions.create(**request_params)
        # Log response metadata
        try:
            finish_reason = None
            if getattr(completion, "choices", None):
                choice0 = completion.choices[0]
                finish_reason = getattr(choice0, "finish_reason", None)
            usage = getattr(completion, "usage", None)
            prompt_toks = getattr(usage, "prompt_tokens", None) if usage else None
            completion_toks = getattr(usage, "completion_tokens", None) if usage else None
            total_toks = getattr(usage, "total_tokens", None) if usage else None
            self.log.info(
                f"OpenRouter response ← id={getattr(completion, 'id', None)} "
                f"model={getattr(completion, 'model', None)} finish={finish_reason} "
                f"tokens=({prompt_toks}, {completion_toks}, {total_toks}) "
                f"created={getattr(completion, 'created', None)}"
            )
        except Exception as e:
            self.log.info(f"OpenRouter response (metadata logging failed): {e}")

        choice0 = completion.choices[0]
        message0 = choice0.message
        content = message0.content
        # Log any annotations (sources) if present
        try:
            annotations = getattr(message0, "annotations", None)
            if annotations:
                self.log.info(
                    f"OpenRouter annotations: {json.dumps(annotations, ensure_ascii=False)}"
                )
        except Exception as e:
            self.log.info(f"OpenRouter annotations logging failed: {e}")
            annotations = None

        # Optionally append sources
        try:
            if self.registryValue("web_show_sources", channel) and annotations:
                urls = []
                for ann in annotations:
                    if isinstance(ann, dict):
                        url = ann.get("url") or ann.get("source") or ann.get("link")
                        if url:
                            urls.append(url)
                if urls:
                    content = f"{content}\nSources: " + " ".join(urls)
        except Exception as e:
            self.log.info(f"OpenRouter source append failed: {e}")

        if self.registryValue("nick_strip", channel):
            content = re.sub(rf"^{re.escape(irc.nick)}: ?", "", content)

        # --------------------------------------------------------------- #
        # Send reply back to IRC
        # --------------------------------------------------------------- #
        prefix_flag = self.registryValue("nick_prefix", channel)
        if self.registryValue("reply_intact", channel):
            for line in content.splitlines():
                if line:
                    irc.reply(line, prefixNick=prefix_flag)
        else:
            irc.reply(" ".join(content.splitlines()), prefixNick=prefix_flag)

        # --------------------------------------------------------------- #
        # Save conversation history
        # --------------------------------------------------------------- #
        self._append_history(key, prompt_for_llm, content, max_history)


Class = OpenRouter

# vim: set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
