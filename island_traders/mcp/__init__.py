"""MCP integration for Island Traders.

Exposes a running game room as Model Context Protocol tools so any MCP-capable
agent harness (Codex CLI, Claude Code, a Hermes tool-calling loop, ...) can play
the game through a clean reason-act-observe loop instead of puppeting stdin.

See `game_server.py` for the stdio MCP server.
"""
