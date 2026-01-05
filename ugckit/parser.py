"""Markdown script parser for UGCKit.

Parses video scripts from markdown format into structured data.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from ugckit.models import CompositionMode, Script, ScreencastOverlay, Segment

# Regex patterns for parsing
SCRIPT_HEADER_PATTERN = re.compile(r"###\s+Script\s+(\w+):\s+[\"']?(.+?)[\"']?\s*(?:\(|$)")
CLIP_PATTERN = re.compile(r"\*\*Clip\s+(\d+)\s*\(.*?\):\*\*")
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


def parse_screencast_tag(text: str) -> Optional[ScreencastOverlay]:
    """Parse screencast tag from text.

    Format: [screencast: filename @ start-end mode:pip]

    Args:
        text: Text containing screencast tag.

    Returns:
        ScreencastOverlay if found, None otherwise.
    """
    match = SCREENCAST_PATTERN.search(text)
    if not match:
        return None

    filename = match.group(1)
    start = float(match.group(2))
    end = float(match.group(3))
    mode_str = match.group(4)

    mode = CompositionMode.OVERLAY
    if mode_str and mode_str.lower() == "pip":
        mode = CompositionMode.PIP

    return ScreencastOverlay(
        file=f"{filename}.mp4",
        start=start,
        end=end,
        mode=mode,
    )


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

    # Split into clips
    clip_sections = re.split(CLIP_PATTERN, content)

    # Process clips (skip first element which is before first clip)
    clip_num = 0
    for i in range(1, len(clip_sections), 2):
        if i + 1 >= len(clip_sections):
            break

        clip_num = int(clip_sections[i])
        clip_content = clip_sections[i + 1]

        # Extract speech text
        says_match = SAYS_PATTERN.search(clip_content)
        if not says_match:
            continue

        text = says_match.group(1).strip()
        duration = estimate_duration(text)

        # Check for screencast tags
        screencasts = []
        screencast = parse_screencast_tag(clip_content)
        if screencast:
            screencasts.append(screencast)

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
    with open(file_path) as f:
        content = f.read()

    scripts: List[Script] = []

    # Find all script sections
    # Pattern: ### Script XX: "Title"
    script_matches = list(SCRIPT_HEADER_PATTERN.finditer(content))

    for i, match in enumerate(script_matches):
        script_id = match.group(1)
        title = match.group(2).strip('"\'')

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
