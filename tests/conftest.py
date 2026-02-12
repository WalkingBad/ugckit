"""Shared fixtures for UGCKit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ugckit.config import load_config
from ugckit.models import Config


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def sample_script_md(tmp_dir: Path) -> Path:
    """Create a sample script markdown file."""
    content = """\
### Script T1: "Test Script One"

**Character:** Alex

**Clip 1 (8s):**
Says: "First clip with eight seconds duration from header."

**Clip 2 (VEO 12s):**
[screencast: demo_screen @ 1.5-5.0]
Says: "Second clip has a screencast overlay and twelve seconds."

**Clip 3 ():**
Says: "Third clip has no duration so it uses word count fallback."
"""
    path = tmp_dir / "test_script.md"
    path.write_text(content)
    return path


@pytest.fixture
def multi_script_md(tmp_dir: Path) -> Path:
    """Create a markdown file with multiple scripts."""
    content = """\
### Script A1: "First Script"

**Clip 1 (8s):**
Says: "Hello from script A1."

**Clip 2 (8s):**
Says: "Second segment of A1."

### Script A2: "Second Script"

**Clip 1 (10s):**
Says: "Hello from script A2."
"""
    path = tmp_dir / "multi.md"
    path.write_text(content)
    return path


@pytest.fixture
def default_config() -> Config:
    """Load default configuration."""
    return load_config()


@pytest.fixture
def avatar_dir(tmp_dir: Path) -> Path:
    """Create a directory with fake avatar files."""
    d = tmp_dir / "avatars"
    d.mkdir()
    return d


@pytest.fixture
def scripts_dir(tmp_dir: Path, sample_script_md: Path) -> Path:
    """Create a scripts directory with a sample script."""
    d = tmp_dir / "scripts"
    d.mkdir()
    # Copy script into directory
    (d / "T1.md").write_text(sample_script_md.read_text())
    return d
