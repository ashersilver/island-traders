from __future__ import annotations

import argparse
import html
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


APP_VERSION_RE = re.compile(r'^APP_VERSION:\s*str\s*=\s*"([^"]+)"', re.MULTILINE)
PACKAGE_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
UNRELEASED_VERSION_RE = re.compile(r"`APP_VERSION`:\s*`([^`]+)`")


@dataclass(frozen=True)
class GitSnapshot:
    branch: str
    upstream: str
    short_status: tuple[str, ...]
    latest_tag: str
    # False when the newest tag in the repo is not an ancestor of HEAD — the
    # normal state on a pre-release branch, because release tags are cut on
    # master. Surfaced so the page cannot imply the tag is on this branch.
    latest_tag_reachable: bool = True

    @property
    def dirty_count(self) -> int:
        return len(self.short_status)


@dataclass(frozen=True)
class ReleaseSnapshot:
    app_version: str
    package_version: str
    release_notes_version: str
    release_notes_has_unreleased: bool
    git: GitSnapshot


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract(pattern: re.Pattern[str], text: str, label: str) -> str:
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Could not find {label}")
    return match.group(1)


def _run_git(repo: Path, args: Sequence[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=repo,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _git_succeeds(repo: Path, args: Sequence[str]) -> bool:
    """Run a git query that answers via exit status rather than output."""
    try:
        return subprocess.call(
            ["git", *args],
            cwd=repo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) == 0
    except FileNotFoundError:
        return False


def collect_snapshot(repo: Path) -> ReleaseSnapshot:
    constants_text = _read(repo / "island_traders" / "constants.py")
    pyproject_text = _read(repo / "pyproject.toml")
    notes_text = _read(repo / "RELEASE_NOTES.md")

    branch = _run_git(repo, ["branch", "--show-current"]) or "(detached)"
    upstream = _run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    short_status = tuple(
        line for line in _run_git(repo, ["status", "--short"]).splitlines() if line
    )
    # `git describe` only sees tags reachable from HEAD, so on a pre-release
    # branch it reports the last tag on THIS line of history — which skips the
    # real release tag, because releases are tagged on the master merge commit.
    # Ask for the newest tag in the repo instead, then say whether it is on
    # this branch.
    latest_tag = _run_git(
        repo,
        ["for-each-ref", "--sort=-creatordate", "--count=1",
         "--format=%(refname:short)", "refs/tags"],
    ) or "(none)"
    latest_tag_reachable = (
        latest_tag != "(none)"
        and _git_succeeds(repo, ["merge-base", "--is-ancestor", latest_tag, "HEAD"])
    )

    return ReleaseSnapshot(
        app_version=_extract(APP_VERSION_RE, constants_text, "APP_VERSION"),
        package_version=_extract(PACKAGE_VERSION_RE, pyproject_text, "package version"),
        release_notes_version=_extract(
            UNRELEASED_VERSION_RE, notes_text, "Unreleased APP_VERSION"
        ),
        release_notes_has_unreleased="## Unreleased" in notes_text,
        git=GitSnapshot(
            branch=branch,
            upstream=upstream or "(none)",
            short_status=short_status,
            latest_tag=latest_tag,
            latest_tag_reachable=latest_tag_reachable,
        ),
    )


def version_status(snapshot: ReleaseSnapshot) -> tuple[str, str, str]:
    app = snapshot.app_version
    package = snapshot.package_version
    notes = snapshot.release_notes_version

    if notes != app:
        return (
            "warn",
            "Release notes version mismatch",
            f"Unreleased says {notes}; constants.py says {app}. Align before merge.",
        )
    if app == package:
        return (
            "ok",
            "Versions reconciled",
            "Running APP_VERSION and package version match. This looks like a tagged release state.",
        )
    if "-dev." in app:
        return (
            "ok",
            "Expected dev-cycle split",
            f"APP_VERSION {app} is ahead of package {package}; pyproject should lag until release cut.",
        )
    return (
        "warn",
        "Version split needs review",
        f"APP_VERSION {app} and package {package} differ outside the documented dev-cycle pattern.",
    )


def branch_status(snapshot: ReleaseSnapshot) -> tuple[str, str, str]:
    if snapshot.git.dirty_count:
        return (
            "warn",
            "Working tree has local changes",
            f"{snapshot.git.dirty_count} changed path(s). Commit, stash, or explain them before release.",
        )
    if snapshot.git.upstream in {"origin/pre-release", "pre-release"}:
        return (
            "ok",
            "Branch tracks pre-release",
            "This matches the project release-process guidance for feature work.",
        )
    return (
        "warn",
        "Branch base needs confirmation",
        f"Current upstream is {snapshot.git.upstream}; release work usually targets origin/pre-release.",
    )


def checklist(snapshot: ReleaseSnapshot) -> list[tuple[str, str, str]]:
    version = version_status(snapshot)
    branch = branch_status(snapshot)
    unreleased = (
        "ok",
        "Unreleased section present",
        "RELEASE_NOTES.md has the required Unreleased section.",
    )
    if not snapshot.release_notes_has_unreleased:
        unreleased = (
            "warn",
            "Missing Unreleased section",
            "Add ## Unreleased before merging to pre-release.",
        )
    return [
        version,
        branch,
        unreleased,
        (
            "info",
            "Manual test evidence",
            "Record pytest, server smoke, export, and simulation results before opening a PR.",
        ),
        (
            "info",
            "No mutation buttons in V0.1",
            "This command center reports state and suggests commands; it does not merge or tag.",
        ),
    ]


def _badge_class(status: str) -> str:
    return {"ok": "ok", "warn": "warn"}.get(status, "info")


def render_html(snapshot: ReleaseSnapshot) -> str:
    checks = checklist(snapshot)
    dirty_rows = "\n".join(
        f"<li><code>{html.escape(line)}</code></li>" for line in snapshot.git.short_status[:12]
    )
    if not dirty_rows:
        dirty_rows = "<li>No local changes detected.</li>"
    elif snapshot.git.dirty_count > 12:
        dirty_rows += f"<li>...and {snapshot.git.dirty_count - 12} more.</li>"

    check_cards = "\n".join(
        f"""
        <article class=\"check {_badge_class(status)}\">
          <div class=\"icon\">{'OK' if status == 'ok' else '!' if status == 'warn' else 'i'}</div>
          <div>
            <h3>{html.escape(title)}</h3>
            <p>{html.escape(detail)}</p>
          </div>
        </article>
        """
        for status, title, detail in checks
    )

    tag_note = (
        ""
        if snapshot.git.latest_tag_reachable
        else '<span style="display:block;color:#f3b83f;font-size:11px;'
             'margin-top:3px">not on this branch</span>'
    )

    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>Island Traders Release Command Center</title>
<style>
:root {{
  --bg:#06101b; --panel:#0d1b2b; --panel2:#11243a; --line:#244462;
  --ink:#edf4f8; --muted:#8aa2b6; --cyan:#18c7df; --gold:#f3b83f;
  --green:#26de81; --red:#ff6470; --blue:#69a7ff; --radius:8px;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:#040912;color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif}}
.page{{max-width:1420px;margin:0 auto;padding:28px}}
header{{display:flex;gap:18px;align-items:flex-start;justify-content:space-between;margin-bottom:22px}}
h1{{margin:0 0 6px;color:var(--gold);font-size:32px}}
.lede{{margin:0;color:var(--muted);max-width:820px}}
.stamp{{border:1px solid rgba(243,184,63,.38);background:rgba(243,184,63,.08);border-radius:var(--radius);padding:12px 14px;color:#f8d98c;min-width:260px}}
.grid{{display:grid;grid-template-columns:1fr 360px;gap:16px}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}}
.panel h2{{margin:0;padding:12px 14px;border-bottom:1px solid var(--line);font-size:14px;color:var(--cyan);text-transform:uppercase;letter-spacing:.06em}}
.body{{padding:14px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}}
.metric{{background:#081423;border:1px solid #1c3753;border-radius:var(--radius);padding:12px}}
.metric label{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px}}
.metric strong{{font-size:17px;color:var(--ink);word-break:break-word}}
.checks{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.check{{display:flex;gap:10px;background:#081423;border:1px solid #1c3753;border-radius:var(--radius);padding:12px}}
.check.ok{{border-color:rgba(38,222,129,.45)}} .check.warn{{border-color:rgba(243,184,63,.55)}} .check.info{{border-color:rgba(105,167,255,.45)}}
.icon{{width:28px;height:28px;border-radius:999px;display:grid;place-items:center;flex:0 0 auto;font-weight:900;background:var(--panel2);color:var(--muted)}}
.ok .icon{{background:var(--green);color:#00180c}} .warn .icon{{background:var(--gold);color:#1a1300}} .info .icon{{background:var(--blue);color:#001326}}
.check h3{{margin:0 0 4px;font-size:14px}} .check p{{margin:0;color:var(--muted);font-size:13px}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#d5e8ff}}
pre{{margin:0;white-space:pre-wrap;background:#050d18;border:1px solid #1c3753;border-radius:var(--radius);padding:12px;color:#d5e8ff}}
ul{{margin:0;padding-left:20px;color:var(--muted)}} li{{margin:.35rem 0}}
.flow{{display:grid;gap:10px}}
.step{{background:#081423;border:1px solid #1c3753;border-radius:var(--radius);padding:11px}}
.step b{{display:block;color:var(--ink)}} .step span{{display:block;color:var(--muted);font-size:13px;margin-top:3px}}
@media(max-width:960px){{.grid,.checks,.metrics{{grid-template-columns:1fr}} header{{display:block}} .stamp{{margin-top:14px}}}}
</style>
</head>
<body>
<main class=\"page\">
  <header>
    <div>
      <h1>Island Traders Release Command Center</h1>
      <p class=\"lede\">V0.1 local release cockpit. It reads the current checkout, explains version state, highlights release-process gaps, and keeps dangerous actions as explicit human-run commands.</p>
    </div>
    <div class=\"stamp\"><strong>Generated locally</strong><br>No git mutations. No network calls.</div>
  </header>

  <section class=\"grid\">
    <div>
      <section class=\"panel\">
        <h2>Current Checkout</h2>
        <div class=\"body\">
          <div class=\"metrics\">
            <div class=\"metric\"><label>APP_VERSION</label><strong>{html.escape(snapshot.app_version)}</strong></div>
            <div class=\"metric\"><label>Package Version</label><strong>{html.escape(snapshot.package_version)}</strong></div>
            <div class=\"metric\"><label>Release Notes</label><strong>{html.escape(snapshot.release_notes_version)}</strong></div>
            <div class=\"metric\"><label>Latest Tag</label><strong>{html.escape(snapshot.git.latest_tag)}</strong>{tag_note}</div>
          </div>
          <div class=\"metrics\">
            <div class=\"metric\"><label>Branch</label><strong>{html.escape(snapshot.git.branch)}</strong></div>
            <div class=\"metric\"><label>Upstream</label><strong>{html.escape(snapshot.git.upstream)}</strong></div>
            <div class=\"metric\"><label>Local Changes</label><strong>{snapshot.git.dirty_count}</strong></div>
            <div class=\"metric\"><label>Mode</label><strong>Inspect only</strong></div>
          </div>
          <div class=\"checks\">{check_cards}</div>
        </div>
      </section>
    </div>

    <aside class=\"flow\">
      <section class=\"panel\">
        <h2>Suggested Flow</h2>
        <div class=\"body flow\">
          <div class=\"step\"><b>1. Finish branch work</b><span>Keep this branch scoped and update release notes.</span></div>
          <div class=\"step\"><b>2. Verify</b><span>Run pytest plus targeted server/export/simulation smoke checks.</span></div>
          <div class=\"step\"><b>3. Open PR to pre-release</b><span>Link the issue or requirement. Use Refs/Closes intentionally.</span></div>
          <div class=\"step\"><b>4. Release cut later</b><span>Only at release time reconcile pyproject and create tags.</span></div>
        </div>
      </section>

      <section class=\"panel\">
        <h2>Verification Commands</h2>
        <div class=\"body\">
<pre>pytest
island-traders-sim --games 100 --seed 42
island-traders-export --output ./printables-smoke
island-traders-server --host 127.0.0.1 --port 8001</pre>
        </div>
      </section>

      <section class=\"panel\">
        <h2>Working Tree</h2>
        <div class=\"body\"><ul>{dirty_rows}</ul></div>
      </section>
    </aside>
  </section>
</main>
</body>
</html>
"""


def write_command_center(repo: Path, output: Path) -> ReleaseSnapshot:
    snapshot = collect_snapshot(repo)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(snapshot), encoding="utf-8")
    return snapshot


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the release command center.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root to inspect. Defaults to the current directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("release-command-center.html"),
        help="HTML file to write. Defaults to ./release-command-center.html.",
    )
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    output = args.output if args.output.is_absolute() else repo / args.output
    snapshot = write_command_center(repo, output)

    print(f"Wrote {output}")
    print(f"APP_VERSION: {snapshot.app_version}")
    print(f"package version: {snapshot.package_version}")
    print(f"branch: {snapshot.git.branch} -> {snapshot.git.upstream}")
    print(f"local changes: {snapshot.git.dirty_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
