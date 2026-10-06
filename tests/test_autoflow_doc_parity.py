"""Keep the fork's onboarding and command synopsis on its shipped surfaces."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_onboarding_points_at_autoflow_instead_of_upstream() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "https://github.com/Grunte12/AutoFlow/blob/feature/autoflow-preview/AGENTS.md" in readme
    assert (
        "https://github.com/Grunte12/AutoFlow/blob/feature/autoflow-preview/docs/INDEX.md" in readme
    )
    assert "github.com/ffroliva/gflow-cli/blob/main/AGENTS.md" not in readme


def test_usage_synopsis_lists_recovery_and_batch_with_accurate_data_label() -> None:
    usage = (ROOT / "docs" / "USAGE.md").read_text(encoding="utf-8")
    synopsis = usage.split("## Synopsis", maxsplit=1)[1].split("Global flags:", maxsplit=1)[0]

    assert "batch MANIFEST" in synopsis
    assert "download MEDIA_ID" in synopsis
    assert "read-only queries" not in synopsis.lower()
    assert "Recover an already-generated video" in synopsis
