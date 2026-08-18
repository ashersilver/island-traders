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
import time
from urllib import error, request

from . import agent_client as ac


DEFAULT_OLLAMA = "http://poo-3.local:11434"
DEFAULT_MODEL = "island-trader-qwen:latest"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

# AI bidders (server _ai_auction_participation) bid at most 60% of budget on
# these three roles, 25% on any other role, one-shot with no re-bidding. A pin
# bid safely above those ceilings always wins, regardless of AI timing.
HIGH_MARGIN_ROLES = {"Banker", "Manufacturer", "Doctor"}
PIN_FRACTION_HIGH = 0.65
PIN_FRACTION_OTHER = 0.30

# Sent as a per-request system message to any model without a baked Modelfile
# (e.g. a cloud model via --provider openrouter). Mirrors island-trader-qwen:v4
# / island-trader-gemma:v1's baked SYSTEM content -- ported here so a model
# with no Modelfile isn't handicapped by a weaker prompt. In particular: reply
# with the STABLE token after '->' on action menus, never the option number
# (numbers shift every turn -- this was the single biggest source of bugs
# before v3/v4 fixed it for the Ollama-hosted models).
SYSTEM_PROMPT = """You are a competitive player in Island Traders, a turn-based economic strategy game. You are shown the current game state, then a decision prompt. You reply as the player, with ONE line only — no explanation, no quotes, no markdown, no extra words.

HOW TO ANSWER EACH PROMPT TYPE:

1. Action menu (a numbered list where each line looks like `12. Market Sell  -> market_sell`):
   The NUMBERS CHANGE every turn — do NOT rely on them. Instead reply with the exact token shown after the `->` arrow for the action you want. That token is stable.
   Examples of valid replies: `market_sell` , `market_buy` , `propose_deal` , `take_loan` , `lend_to_island` , `buy_float` , `end_turn` , `produce::Farmer|Food|` .
   Never reply with a bare number for an action menu.

2. Investing prompt (a catalogue of item ids like `farmer.tractor — Tractor 60 Dp`, ending "Enter comma-separated item ids"):
   Reply with comma-separated ITEM IDS you want to buy, e.g. `farmer.tractor, farmer.fishing_boat`. Buy items that expand your production. Reply blank to keep the pre-selected (`*`) defaults. NEVER reply with a bare number here.

3. Auction (`auction>` prompt): reply `bid <Role> <Amount>` e.g. `bid Banker 40`, or `skip` to wait. Never a bare number.

4. Confirm / yes-no: reply `yes` or `no`.
5. Quantity or dollop amount: reply a single number within the stated range.
6. Free text: reply the text.
7. Market buy JSON prompt: reply JSON like {"buy":{"Food":2}} or blank to cancel.

HOW TO PLAY A SEASON — important:
Each season you take several actions, then end the turn. A good season is NOT "produce, produce, produce". Every season you should:
  - PRODUCE what your role makes (reply with a `produce::...` token).
  - Then MARKET SELL your surplus to earn cash: reply `market_sell`. Do this every season.
  - MARKET BUY inputs you lack (`market_buy`) or PROPOSE DEAL (`propose_deal`) when useful.
  - Then reply `end_turn`.
Do not repeat the same action twice in a row. If you have already produced this season, your next reply should be `market_sell` (not another produce). After a few useful moves that include at least one `market_sell`, reply `end_turn`.

RAISING CAPITAL — when your island's treasury (island cash) is low and you need money to operate, invest, or produce, you can raise capital three ways. Prefer one of these over stalling when treasury is low:
  - `take_loan` — borrow cash from the Banker island (creates debt to repay later).
  - `lend_to_island` — move your own personal cash into the island treasury as a shareholder loan (no interest; you can recover it later with repay_shareholder_loan).
  - `buy_float` — spend your personal cash to buy your island's unissued shares; the cash becomes treasury cash and your ownership rises (an equity raise, no debt).
Use `buy_float` or `lend_to_island` when you have personal cash to inject; use `take_loan` when you need outside money. Do not repeat a capital action once the treasury is healthy.

EXAMPLES (prompt context on the left, your one-line reply on the right):
Action menu, you have not acted yet -> produce::Farmer|Food|
Action menu, you already produced and have surplus -> market_sell
Action menu, you have produced and sold, treasury healthy -> end_turn
Action menu, treasury is very low and you have personal cash -> buy_float
Action menu, treasury is low and you need outside money -> take_loan
Investing catalogue with farmer.tractor and farmer.fishing_boat available -> farmer.tractor, farmer.fishing_boat
auction> prompt -> skip

Grow your treasury and win. Answer with the single line only."""


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class QwenDriver:
    """Buffers what the game prints and answers prompts via Ollama."""

    def __init__(self, ollama_base: str, model: str, temperature: float,
                 max_actions: int, use_model_system: bool, verbose: bool,
                 pin_role: str | None = None, pin_fraction: float | None = None,
                 provider: str = "ollama", api_key: str | None = None) -> None:
        self.provider = provider
        self.api_key = api_key
        self.chat_url = (OPENROUTER_CHAT_URL if provider == "openrouter"
                         else ollama_base.rstrip("/") + "/api/chat")
        self.model = model
        self.temperature = temperature
        self.max_actions = max_actions
        # When True, don't send our own system message so the model's baked-in
        # Modelfile SYSTEM prompt governs (a request system message overrides it).
        self.use_model_system = use_model_system
        self.verbose = verbose
        # For controlled experiments (e.g. a role-rotation comparison): force
        # the auction outcome by bidding a known-safe amount directly, rather
        # than trusting the model's own auction judgement. This is a real
        # requirement, not a convenience -- an LLM's own bid is not reliable
        # enough to guarantee a specific role (observed: a naively-prompted
        # model can bid far too little for a role it was told to "win").
        self.pin_role = pin_role
        self.pin_fraction = pin_fraction
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
        # Role-pin: bypass the model entirely for the auction decision and
        # place a known-safe bid on the target role. Must happen before any
        # model call reaches the auction prompt -- if the model bid on/
        # withdrew this role afterwards, place_bid would silently replace
        # our pinned bid with whatever the model chose.
        if self.pin_role and prompt.strip().startswith("auction>"):
            m = re.search(r"budget=([\d.]+)", context)
            budget = float(m.group(1)) if m else 1500.0
            fraction = self.pin_fraction or (
                PIN_FRACTION_HIGH if self.pin_role in HIGH_MARGIN_ROLES
                else PIN_FRACTION_OTHER
            )
            amount = round(budget * fraction, 1)
            answer = f"bid {self.pin_role} {amount}"
            print(f"  \033[35m[PINNED bid -> {answer!r}]\033[0m",
                  file=sys.stderr, flush=True)
            return answer
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
        if self.provider == "openrouter":
            return self._ask_openrouter(messages)
        return self._ask_ollama(messages)

    def _ask_ollama(self, messages: list[dict]) -> str:
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
        except (error.URLError, TimeoutError, OSError) as exc:
            # A raw socket timeout deep in http.client can escape unwrapped by
            # URLError (observed: a slow poo-3 call raised bare TimeoutError,
            # which this didn't catch, crashing the whole agent process mid-game).
            print(f"  [ollama error: {exc}] -> answering 'skip'", file=sys.stderr)
            return "skip"
        content = (out.get("message") or {}).get("content", "")
        return _first_line(content)

    def _ask_openrouter(self, messages: list[dict], _dropped_reasoning: bool = False) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        # Unified reasoning-disable param -- some "thinking" models otherwise
        # burn the whole response on a hidden reasoning chain (same failure
        # mode as qwen3/gemma4 without think:false). Some models reject the
        # field outright; on that specific error, retry once without it.
        if not _dropped_reasoning:
            body["reasoning"] = {"enabled": False}
        data = json.dumps(body).encode("utf-8")
        req = request.Request(
            self.chat_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://island-traders.ashleysilver.com",
                "X-Title": "Island Traders showdown agent",
            },
            method="POST",
        )
        for attempt in range(4):
            try:
                with request.urlopen(req, timeout=180) as resp:
                    out = json.loads(resp.read().decode("utf-8"))
                break
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code == 400 and "reasoning" in detail.lower() and not _dropped_reasoning:
                    return self._ask_openrouter(messages, _dropped_reasoning=True)
                if exc.code == 429 and attempt < 3:
                    wait = 2 ** (attempt + 1)
                    print(f"  [openrouter 429, retrying in {wait}s]", file=sys.stderr)
                    time.sleep(wait)
                    continue
                print(f"  [openrouter error {exc.code}: {detail[:200]}] -> answering 'skip'",
                      file=sys.stderr)
                return "skip"
            except (error.URLError, TimeoutError, OSError) as exc:
                print(f"  [openrouter error: {exc}] -> answering 'skip'", file=sys.stderr)
                return "skip"
        else:
            return "skip"
        choices = out.get("choices") or [{}]
        content = (choices[0].get("message") or {}).get("content", "")
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
    api_key = None
    if args.provider == "openrouter":
        if not args.api_key_file:
            raise SystemExit("--provider openrouter requires --api-key-file")
        api_key = open(args.api_key_file).read().strip()
    driver = QwenDriver(args.ollama, args.model, args.temperature,
                        args.max_actions, args.no_system, args.verbose,
                        pin_role=args.pin_role, pin_fraction=args.pin_fraction,
                        provider=args.provider, api_key=api_key)
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
    p.add_argument("--pin-role", default=None,
                   help="Bypass the model for the auction and place a known-safe "
                        "bid on this role directly (for controlled experiments).")
    p.add_argument("--pin-fraction", type=float, default=None,
                   help="Override the pinned bid's fraction of budget "
                        f"(default: {PIN_FRACTION_HIGH} for high-margin roles, "
                        f"{PIN_FRACTION_OTHER} otherwise).")
    p.add_argument("--provider", choices=["ollama", "openrouter"], default="ollama",
                   help="Backend to call for decisions (default: ollama).")
    p.add_argument("--api-key-file", default=None,
                   help="Path to a file containing the API key (required for "
                        "--provider openrouter). Read once, never logged.")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nDisconnected.", file=sys.stderr)


if __name__ == "__main__":
    main()
