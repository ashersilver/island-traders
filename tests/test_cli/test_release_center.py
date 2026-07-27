from __future__ import annotations

from pathlib import Path

from island_traders.cli.release_center import (
    GitSnapshot,
    ReleaseSnapshot,
    branch_status,
    collect_snapshot,
    render_html,
    version_status,
)


def _snapshot(
    *,
    app_version: str = "0.1.6-dev.2026-07-14.5",
    package_version: str = "0.1.5",
    release_notes_version: str = "0.1.6-dev.2026-07-14.5",
    upstream: str = "origin/pre-release",
    dirty: tuple[str, ...] = (),
) -> ReleaseSnapshot:
    return ReleaseSnapshot(
        app_version=app_version,
        package_version=package_version,
        release_notes_version=release_notes_version,
        release_notes_has_unreleased=True,
        git=GitSnapshot(
            branch="codex/release-command-center",
            upstream=upstream,
            short_status=dirty,
            latest_tag="v0.1.5",
        ),
    )


def test_version_status_accepts_documented_dev_cycle_split():
    status, title, detail = version_status(_snapshot())

    assert status == "ok"
    assert title == "Expected dev-cycle split"
    assert "pyproject should lag" in detail


def test_version_status_warns_when_release_notes_version_lags():
    status, title, detail = version_status(
        _snapshot(release_notes_version="0.1.6-dev.2026-07-14.4")
    )

    assert status == "warn"
    assert title == "Release notes version mismatch"
    assert "constants.py" in detail


def test_branch_status_warns_for_dirty_worktree():
    status, title, detail = branch_status(_snapshot(dirty=(" M pyproject.toml",)))

    assert status == "warn"
    assert title == "Working tree has local changes"
    assert "1 changed" in detail


def test_render_html_includes_versions_and_does_not_offer_mutation_buttons():
    page = render_html(_snapshot())

    assert "0.1.6-dev.2026-07-14.5" in page
    assert "0.1.5" in page
    assert "Inspect only" in page
    assert "No git mutations" in page
    assert "Merge release PR" not in page
    assert "Create tag" not in page


def test_collect_snapshot_reads_repo_files_without_git(tmp_path: Path):
    (tmp_path / "island_traders").mkdir()
    (tmp_path / "island_traders" / "constants.py").write_text(
        'APP_VERSION: str = "0.2.0-dev.2026-07-27.1"\n',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "island-traders"\nversion = "0.1.5"\n',
        encoding="utf-8",
    )
    (tmp_path / "RELEASE_NOTES.md").write_text(
        "# Notes\n\n## Unreleased\n\n`APP_VERSION`: `0.2.0-dev.2026-07-27.1`.\n",
        encoding="utf-8",
    )

    snapshot = collect_snapshot(tmp_path)

    assert snapshot.app_version == "0.2.0-dev.2026-07-27.1"
    assert snapshot.package_version == "0.1.5"
    assert snapshot.release_notes_version == "0.2.0-dev.2026-07-27.1"
    assert snapshot.git.branch == "(detached)"
