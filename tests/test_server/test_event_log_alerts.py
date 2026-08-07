"""Event-log action alerts (#3).

The sidebar "My Alerts" panel already covered the numeric half of #3 (price,
stock, treasury thresholds). This covers the other half the issue asks for:
alerts driven by the **event log** — "an action associated with the event log
below which will create popups when the type of event being tracked takes
place".

Client-only feature, so these are static checks over `index.html`: enough to
catch the wiring being removed or the backfill guard being dropped.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

INDEX = (
    Path(__file__).resolve().parents[2]
    / "island_traders" / "server" / "static" / "index.html"
)


@pytest.fixture(scope="module")
def markup() -> str:
    return INDEX.read_text()


def test_alert_categories_match_the_log_categories(markup):
    """Every alertable category must be one `_logCategory` can actually emit.

    A category with no matching log line would be a switch that silently
    never fires.
    """
    emitted = set(re.findall(r"return '(\w+)';", markup[markup.index("function _logCategory"):][:600]))
    declared = set(re.findall(r"\{key: '(\w+)',\s*label:", markup))

    # 'mine' is the per-player relevance flag, not a _logCategory return.
    assert declared - {"mine"} <= emitted, (
        f"alert categories with no log category: {declared - {'mine'} - emitted}"
    )


def test_addlog_consults_the_alert_rules(markup):
    body = re.search(r"function addLog\(text, cls = ''\) \{(.*?)\n\}", markup, re.S).group(1)

    assert "_maybeAlert(" in body, "addLog must offer each line to the alert matcher"


def test_backfill_does_not_fire_alerts(markup):
    """Rejoining a long game must not spray toasts for history already past."""
    body = re.search(r"function syncServerLog\(msg\) \{(.*?)\n\}", markup, re.S).group(1)

    assert "_alertsSuppressed = true" in body
    assert "finally" in body, "the guard must be released even if addLog throws"
    assert "seenServerLogCount === 0" in body, "only the first back-fill is suppressed"


def test_alerts_are_reachable_from_the_event_log(markup):
    """#3 asks for the action to hang off the event log specifically."""
    assert 'id="log-alert-btn"' in markup
    assert 'onclick="openAlertSettings()"' in markup


def test_rules_persist_and_can_be_cleared(markup):
    assert "ALERT_RULES_KEY" in markup
    assert "localStorage.setItem(ALERT_RULES_KEY" in markup
    assert "function clearAlertSettings" in markup


def test_both_alert_systems_use_the_same_toast_style(markup):
    """The numeric panel and the log alerts should look like one feature."""
    alert_toasts = re.findall(r"showToast\([^;]*?\{\s*type: '(\w+)', ms: \d+ ?\}\)", markup)
    fired = [t for t in alert_toasts if t == "alert"]

    assert len(fired) >= 2, "threshold alerts and log alerts should share the style"
    assert ".toast.alert{" in markup, "the shared style must exist"
