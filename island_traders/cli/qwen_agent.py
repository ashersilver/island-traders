"""Drive an Island Traders terminal player with a qwen model on Ollama.

This wraps ``agent_client`` (the provider-agnostic stdin/stdout bridge) and
replaces its human I/O with calls to an Ollama server. Every prompt the game
would have shown a human is sent to the model together with the game context
printed just before it, and the model's single-line reply is fed back as the
response.

Example (join a room created in the browser, play it with qwen on poo-3):

    python -m island_traders.cli.qwen_agent ABC123 \
        --name "Qwen" \
        --server https://island-traders.ashleysilver.com \
        --ollama http://poo-3.local:11434 \
        --model island-trader-qwen:latest

Nothing here talks to the game directly -- it only patches how
``agent_client`` reads and writes, so all WebSocket/message handling stays in
one place.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from urllib import error, request

from . import agent_client as ac


DEFAULT_OLLAMA = "http://poo-3.local:11434"
DEFAULT_MODEL = "island-trader-qwen:latest"

SYSTEM_PROMPT = """You are a competitive player in Island Traders, a turn-based \
economic strategy game. You are shown the current game state followed by a \
decision prompt.

Reply with ONLY the exact value the game expects, on a single line, with no \
explanation, no quotes, and no markdown:
- Numbered option lists: reply with ONLY the option number (e.g. '5'). Do not \
repeat the option's text.
- Auctions: reply like 'bid Banker 40', or 'withdraw Banker', or 'skip' to wait.
- Investing: reply with comma-separated item ids (e.g. 'oil_rig, food_farm'), \
or blank to keep the current selection.
- confirm / yes-no prompts: reply 'yes' or 'no'.
- quantities and dollop amounts: reply with a single number within the stated range.
- free text: reply with the text.
- market buy JSON: reply with JSON like {"buy":{"Food":2}} or blank to cancel.

Trade actively -- don't only produce. Each season, use 'Market Sell' to turn \
surplus goods into cash, 'Market Buy' to acquire inputs you lack, and 'Propose \
Deal' to trade directly with other islands. A turn that only produces wastes \
the market.

When the action menu lists an 'End Turn' (end_turn) option and you have made \
a few useful moves this season (ideally including at least one market trade), \
choose End Turn to finish -- don't keep acting forever.

Play to grow your treasury and win. Answer with the single line only."""


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class QwenDriver:
    """Buffers what the game prints and answers prompts via Ollama."""

    def __init__(self, ollama_base: str, model: str, temperature: float,
                 max_actions: int, use_model_system: bool, verbose: bool) -> None:
        self.chat_url = ollama_base.rstrip("/") + "/api/chat"
        self.model = model
        self.temperature = temperature
        self.max_actions = max_actions
        # When True, don't send our own system message so the model's baked-in
        # Modelfile SYSTEM prompt governs (a request system message overrides it).
        self.use_model_system = use_model_system
        self.verbose = verbose
        self._buffer: list[str] = []
        self._season_actions = 0  # actions taken in the current turn
        self._turn_actions: list[str] = []  # action values chosen this turn

    # -- replaces agent_client.print: capture context, mirror to stderr --
    def capture_print(self, *args: object, **kwargs: object) -> None:
        text = " ".join(str(a) for a in args)
        self._buffer.append(text)
        # Mirror to stderr so a human can watch the game unfold live.
        print(text, file=sys.stderr, flush=True)

    # -- replaces agent_client._ainput: ask qwen instead of a human --
    async def ainput(self, prompt: str) -> str:
        context = "\n".join(self._buffer)
        self._buffer.clear()
        # The main season-action menu is the only prompt that lists an
        # 'end_turn' option. The season never ends on a timer -- the player
        # must pick End Turn -- and the model can't be trusted to, so cap the
        # actions per turn and force End Turn once the cap is hit.
        is_action_menu = "-> end_turn" in context
        if is_action_menu:
            self._season_actions += 1
            if self._season_actions > self.max_actions:
                self._season_actions = 0
                self._turn_actions = []
                print("  \033[33m[auto -> 'end_turn' (action cap reached)]\033[0m",
                      file=sys.stderr, flush=True)
                return "end_turn"
            # The model is stateless per call, so the game context never says
            # "you already produced this turn" -- and without that it just
            # produces every time. Inject the turn history so it moves on.
            context += "\n\n" + self._turn_memory_note()
        answer = await asyncio.to_thread(self._ask, context, prompt)
        # The auction handler loops until it gets 'bid <Role> <Amount>',
        # 'withdraw <Role>', or blank/'skip'. A bare menu number (which the
        # trade-tuned model tends to emit) would spin it, so coerce to 'skip'.
        if prompt.strip().startswith("auction>"):
            low = answer.strip().lower()
            if not (low.startswith("bid ") or low.startswith("withdraw ")
                    or low in {"", "skip"}):
                answer = "skip"
        # Numeric prompts (sell price, quantities): the value-token-trained
        # model sometimes answers with an action token, which the server
        # rejects ("price must be positive") and the whole sale cancels.
        # If the answer isn't a number, fall back to the prompt's own
        # suggested/prefill value, else its max.
        if prompt.strip().startswith(("Dollops >", "Quantity >")):
            if not re.fullmatch(r"-?\d+(\.\d+)?", answer.strip()):
                m = (re.search(r"suggested=([\d.]+)", context)
                     or re.search(r"prefill=([\d.]+)", context)
                     or re.search(r"max=([\d.]+)", context)
                     # choose_quantity renders its range as "[1–5]" / "(max 5)"
                     or re.search(r"\[\d+\s*[–-]\s*(\d+)\]", context)
                     or re.search(r"\(max\s+([\d.]+)\)", context))
                fallback = m.group(1) if m else "0"
                print(f"  \033[33m[auto -> {fallback!r} (non-numeric answer "
                      f"{answer!r} at numeric prompt)]\033[0m",
                      file=sys.stderr, flush=True)
                answer = fallback
        if is_action_menu:
            if _ends_turn(answer):
                self._season_actions = 0  # model ended the turn itself
                self._turn_actions = []
            else:
                self._turn_actions.append(answer)
        print(f"  \033[36m[qwen -> {answer!r}]\033[0m", file=sys.stderr, flush=True)
        return answer

    def _turn_memory_note(self) -> str:
        done = self._turn_actions
        produced = any(a.startswith("produce") for a in done)
        sold = any("market_sell" in a for a in done)
        lines = ["ACTIONS YOU ALREADY TOOK THIS SEASON: "
                 + (", ".join(done) if done else "none") + "."]
        if sold:
            lines.append("You have already produced and sold. Reply `end_turn` "
                         "to finish (or `market_buy`/`propose_deal` if useful).")
        elif produced:
            lines.append("You have already produced this season. Do NOT produce "
                         "again -- reply `market_sell` now to sell your surplus.")
        else:
            lines.append("You have not produced yet -- reply with a `produce::...` "
                         "action first.")
        return "\n".join(lines)

    def _ask(self, context: str, prompt: str) -> str:
        user = f"{context}\n\n{prompt}\n\nYour single-line answer:"
        messages = []
        if not self.use_model_system:
            messages.append({"role": "system", "content": SYSTEM_PROMPT})
        messages.append({"role": "user", "content": user})
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        # Disable thinking for every model that supports it (qwen3, gemma4):
        # left on, the whole token budget can vanish into a hidden thinking
        # block and the visible answer arrives empty (or slow).
        body["think"] = False
        data = json.dumps(body).encode("utf-8")
        req = request.Request(
            self.chat_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=180) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            print(f"  [ollama error: {exc}] -> answering 'skip'", file=sys.stderr)
            return "skip"
        content = (out.get("message") or {}).get("content", "")
        return _first_line(content)


def _ends_turn(answer: str) -> bool:
    return "end_turn" in answer.strip().lower()


def _first_line(content: str) -> str:
    """Reduce a model reply to a single clean command line."""
    content = _THINK_RE.sub("", content).strip()
    # Strip common code-fence / bullet noise, then take the last meaningful line
    # (models sometimes reason first, answer last).
    lines = [ln.strip(" `*-\t") for ln in content.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return "skip"
    line = lines[-1]
    # Drop a leading label like "Answer:" if the model added one.
    line = re.sub(r"^(answer|response|reply)\s*[:=]\s*", "", line, flags=re.IGNORECASE)
    return line.strip()


async def run(args: argparse.Namespace) -> None:
    driver = QwenDriver(args.ollama, args.model, args.temperature,
                        args.max_actions, args.no_system, args.verbose)
    # Patch the bridge's I/O. agent_client uses the module-global `print` and
    # its own `_ainput`, so assigning here redirects every call it makes.
    ac.print = driver.capture_print  # type: ignore[attr-defined]
    ac._ainput = driver.ainput       # type: ignore[assignment]
    await ac.run_client(args.server, args.code, args.name)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Play an Island Traders room with a qwen model via Ollama.",
    )
    p.add_argument("code", help="Room join code, e.g. ABC123")
    p.add_argument("--name", default="Qwen", help="Player name to join with")
    p.add_argument("--server", default="https://island-traders.ashleysilver.com",
                   help="Game server base URL")
    p.add_argument("--ollama", default=DEFAULT_OLLAMA,
                   help=f"Ollama base URL (default: {DEFAULT_OLLAMA})")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Ollama model (default: {DEFAULT_MODEL})")
    p.add_argument("--temperature", type=float, default=0.4)
    p.add_argument("--max-actions", type=int, default=3,
                   help="Actions per turn before End Turn is forced (default: 3)")
    p.add_argument("--no-system", action="store_true",
                   help="Don't send a system message; use the model's baked-in "
                        "Modelfile SYSTEM prompt instead (for island-trader-qwen:v2)")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nDisconnected.", file=sys.stderr)


if __name__ == "__main__":
    main()
