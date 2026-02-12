"""Markdown script parser for UGCKit.

Parses video scripts from markdown format into structured data.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from ugckit.models import CompositionMode, ScreencastOverlay, Script, Segment

# Regex patterns for parsing
SCRIPT_HEADER_PATTERN = re.compile(
    r"###\s+Script\s+(\w+):\s+[\"']?(.+?)[\"']?\s*(?:\(|$)", re.MULTILINE
)
CLIP_PATTERN = re.compile(r"\*\*Clip\s+(\d+)\s*\((?:.*?(\d+)s|[^)]*)\):\*\*")
# Match double-quoted text (allows apostrophes inside)
SAYS_PATTERN = re.compile(r'Says:\s*"([^"]+)"', re.DOTALL)
SCREENCAST_PATTERN = re.compile(
    r"\[screencast:\s*([\w\-\.]+)\s*@\s*([\d.]+)s?-([\d.]+)s?\s*(?:mode:(\w+))?\]",
    re.IGNORECASE,
)
CHARACTER_PATTERN = re.compile(r"\*\*(?:Persona|Character):\*\*\s*(.+)")

# Words per second for duration estimation
WORDS_PER_SECOND = 3.0


def estimate_duration(text: str) -> float:
    """Estimate speech duration from text.

    Args:
        text: Speech text.

    Returns:
        Estimated duration in seconds.
    """
    words = len(text.split())
    return words / WORDS_PER_SECOND


def parse_screencast_tags(text: str) -> List[ScreencastOverlay]:
    """Parse all screencast tags from text.

    Format: [screencast: filename @ start-end mode:pip]

    Args:
        text: Text containing screencast tags.

    Returns:
        List of ScreencastOverlay objects found.
    """
    results = []
    for match in SCREENCAST_PATTERN.finditer(text):
        filename = match.group(1)
        start = float(match.group(2))
        end = float(match.group(3))
        mode_str = match.group(4)

        if end <= start:
            continue

        mode = CompositionMode.OVERLAY
        if mode_str and mode_str.lower() == "pip":
            mode = CompositionMode.PIP

        # Only append .mp4 if no extension present
        if "." not in filename:
            filename = f"{filename}.mp4"

        results.append(
            ScreencastOverlay(
                file=filename,
                start=start,
                end=end,
                mode=mode,
            )
        )
    return results


def parse_script_section(content: str, script_id: str, title: str) -> Script:
    """Parse a single script section.

    Args:
        content: Markdown content of the script section.
        script_id: Script identifier (e.g., "A1").
        title: Script title.

    Returns:
        Parsed Script object.
    """
    segments: List[Segment] = []
    character = None

    # Extract character
    char_match = CHARACTER_PATTERN.search(content)
    if char_match:
        character = char_match.group(1).strip()

    # Find all clip headers and pair with their content
    clip_matches = list(CLIP_PATTERN.finditer(content))
    for idx, match in enumerate(clip_matches):
        clip_num = int(match.group(1))
        header_duration = int(match.group(2)) if match.group(2) else None

        # Extract content between this clip header and the next (or end)
        start = match.end()
        end = clip_matches[idx + 1].start() if idx + 1 < len(clip_matches) else len(content)
        clip_content = content[start:end]

        # Extract speech text
        says_match = SAYS_PATTERN.search(clip_content)
        if not says_match:
            continue

        text = says_match.group(1).strip()
        duration = float(header_duration) if header_duration else estimate_duration(text)

        # Check for screencast tags
        screencasts = parse_screencast_tags(clip_content)

        segment = Segment(
            id=clip_num,
            text=text,
            duration=duration,
            screencasts=screencasts,
        )
        segments.append(segment)

    # Calculate total duration
    total_duration = sum(s.duration for s in segments)

    return Script(
        script_id=script_id,
        title=title,
        character=character,
        total_duration=total_duration,
        segments=segments,
    )


def parse_markdown_file(file_path: Path) -> List[Script]:
    """Parse a markdown file containing video scripts.

    Args:
        file_path: Path to markdown file.

    Returns:
        List of parsed Script objects.
    """
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    scripts: List[Script] = []

    # Find all script sections
    # Pattern: ### Script XX: "Title"
    script_matches = list(SCRIPT_HEADER_PATTERN.finditer(content))

    for i, match in enumerate(script_matches):
        script_id = match.group(1)
        title = match.group(2).strip("\"'")

        # Get content until next script or end of file
        start = match.end()
        end = script_matches[i + 1].start() if i + 1 < len(script_matches) else len(content)
        section_content = content[start:end]

        script = parse_script_section(section_content, script_id, title)
        scripts.append(script)

    return scripts


def find_script_by_id(scripts: List[Script], script_id: str) -> Optional[Script]:
    """Find a script by its ID.

    Args:
        scripts: List of scripts.
        script_id: Script ID to find (e.g., "A1", "B1_duolingo").

    Returns:
        Script if found, None otherwise.
    """
    # Normalize ID for comparison
    normalized_id = script_id.lower().replace("_", "").replace("-", "")

    for script in scripts:
        script_normalized = script.script_id.lower().replace("_", "").replace("-", "")
        if script_normalized == normalized_id or script.script_id.lower() == script_id.lower():
            return script

    return None


def parse_scripts_directory(scripts_dir: Path) -> List[Script]:
    """Parse all markdown files in a directory.

    Args:
        scripts_dir: Directory containing markdown script files.

    Returns:
        List of all parsed scripts.
    """
    all_scripts: List[Script] = []

    for md_file in scripts_dir.glob("*.md"):
        scripts = parse_markdown_file(md_file)
        all_scripts.extend(scripts)

    return all_scripts


def load_script(script_ref: str, scripts_dir: Optional[Path] = None) -> Script:
    """Load a script by ID or file path.

    Args:
        script_ref: Script ID (e.g., "A1") or path to markdown file.
        scripts_dir: Directory to search for scripts (default: current dir).

    Returns:
        Parsed Script object.

    Raises:
        FileNotFoundError: If script file or ID not found.
        ValueError: If no scripts found in file.
    """
    script_path = Path(script_ref)

    # Direct path to markdown file
    if script_path.exists() and script_path.suffix == ".md":
        scripts = parse_markdown_file(script_path)
        if not scripts:
            raise ValueError(f"No scripts found in {script_path}")
        return scripts[0]

    # Script ID - search in directory
    search_dir = scripts_dir or Path(".")
    scripts = parse_scripts_directory(search_dir)
    found = find_script_by_id(scripts, script_ref)

    if not found:
        available = [s.script_id for s in scripts]
        raise FileNotFoundError(f"Script '{script_ref}' not found. Available: {available}")

    return found
