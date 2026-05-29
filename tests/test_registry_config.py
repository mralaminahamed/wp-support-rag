"""Tests for the declarative plugin config loader (FR-PM-5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from apps.api.ingestion.registry import parse_plugin_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_all_committed_plugin_configs_parse() -> None:
    """Every config under config/plugins/ parses into a valid spec (FR-PM-5)."""
    configs = sorted((REPO_ROOT / "config/plugins").glob("*.yaml"))
    assert len(configs) >= 2
    for path in configs:
        spec = parse_plugin_config(path)
        assert spec.slug == path.stem
        assert spec.sources
        if spec.github_repo:
            assert "/" in spec.github_repo


def test_parses_real_yaml_config() -> None:
    """The committed Swift Menu Duplicator YAML config parses fully."""
    spec = parse_plugin_config(REPO_ROOT / "config/plugins/swift-menu-duplicator.yaml")

    assert spec.slug == "swift-menu-duplicator"
    assert spec.github_repo == "mralaminahamed/swift-menu-duplicator"
    assert spec.wporg_slug == "swift-menu-duplicator"
    assert len(spec.sources) == 7
    issues = next(s for s in spec.sources if s.source_type == "github_issues")
    assert issues.config["labels"] == ["question", "support"]


def test_parses_toml_config(tmp_path: Path) -> None:
    """A TOML config produces an equivalent spec."""
    toml = tmp_path / "plugin.toml"
    toml.write_text(
        'slug = "demo"\n'
        'name = "Demo"\n'
        'wporg_slug = "demo"\n\n'
        "[[sources]]\n"
        'source_type = "wporg_faq"\n\n'
        "[[sources]]\n"
        'source_type = "github_readme"\n'
        "enabled = false\n"
    )
    spec = parse_plugin_config(toml)

    assert spec.slug == "demo"
    assert {s.source_type for s in spec.sources} == {"wporg_faq", "github_readme"}
    readme = next(s for s in spec.sources if s.source_type == "github_readme")
    assert readme.enabled is False


def test_rejects_unknown_format(tmp_path: Path) -> None:
    """An unsupported file extension raises."""
    bad = tmp_path / "plugin.ini"
    bad.write_text("nope")
    with pytest.raises(ValueError, match="unsupported config format"):
        parse_plugin_config(bad)
