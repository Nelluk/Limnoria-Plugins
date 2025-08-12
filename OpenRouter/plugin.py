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
from openai import OpenAI

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

        model_name = opts.get("model", self.registryValue("model", channel))

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
        # Call the API
        # --------------------------------------------------------------- #
        completion = client.chat.completions.create(**request_params)
        content = completion.choices[0].message.content

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
