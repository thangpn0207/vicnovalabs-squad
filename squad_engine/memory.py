#!/usr/bin/env python3
"""
OpenClaw-Inspired 3-Tier Persistent Memory System & Context Compactor.
Manages SOUL.md, MEMORY.md, and WORKING.md to preserve architectural continuity
and compact volatile context, preventing token blowup across long agent sessions.
"""

import os
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional, List


DEFAULT_SOUL_MD = """# SOUL — Squad Identity & Immutable Invariants

## Core Principles
1. **Proof-of-Active-Interaction (POAI)**: Software is never certified working based on static screenshots or assumptions.
2. **Zero Code-Offloading**: Agents write directly to the filesystem and verify themselves; never offload code to user.
3. **Bug Hunting Over Passing Pressure**: QA's primary mission is finding edge cases, not manufacturing passing tests.
4. **Separation of Concerns**: Dev writes code, Design dictates UI/HIG, QA conducts black-box audits, Debug solves root causes.
"""

DEFAULT_MEMORY_MD = """# MEMORY — Long-Term Architectural Knowledge & Lessons Learned

## Project Insights & Decisions
- *Initialized by VicnovaLabs Squad.*
"""

DEFAULT_WORKING_MD = """# WORKING — Active Task Scratchpad & Volatile Context

## Current Status
- No active task running.
"""


class SquadMemory:
    """Manages the 3-Tier Markdown Memory for a project workspace."""

    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace = Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        self.memory_dir = self.workspace / ".squad" / "memory"
        self.soul_file = self.memory_dir / "SOUL.md"
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.working_file = self.memory_dir / "WORKING.md"
        self._ensure_initialized()

    def _ensure_initialized(self):
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        if not self.soul_file.exists():
            self.soul_file.write_text(DEFAULT_SOUL_MD, encoding="utf-8")
        if not self.memory_file.exists():
            self.memory_file.write_text(DEFAULT_MEMORY_MD, encoding="utf-8")
        if not self.working_file.exists():
            self.working_file.write_text(DEFAULT_WORKING_MD, encoding="utf-8")

    def read_soul(self) -> str:
        return self.soul_file.read_text(encoding="utf-8") if self.soul_file.exists() else ""

    def read_memory(self) -> str:
        return self.memory_file.read_text(encoding="utf-8") if self.memory_file.exists() else ""

    def read_working(self) -> str:
        return self.working_file.read_text(encoding="utf-8") if self.working_file.exists() else ""

    def append_long_term_insight(
        self,
        topic: str,
        insight: str,
        trust_level: str = "inferred"
    ) -> None:
        """
        Append a permanent architectural lesson, approved decision, or defect pattern.

        Args:
            topic: Short label for the insight category.
            insight: The insight text to record.
            trust_level: 'verified' (proven by test/oracle), 'decision' (user-approved ADR),
                         'inferred' (agent hypothesis), 'historical' (legacy context),
                         or 'superseded' (overridden by newer decisions).
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        tag_map = {
            "verified": "[VERIFIED]",
            "decision": "[DECISION]",
            "inferred": "[INFERRED]",
            "historical": "[HISTORICAL]",
            "superseded": "[SUPERSEDED]"
        }
        trust_tag = tag_map.get(trust_level.lower(), "[INFERRED]")
        entry = f"\n### [{timestamp}] {trust_tag} {topic}\n- {insight.strip()}\n"
        current = self.read_memory()
        self.memory_file.write_text(current + entry, encoding="utf-8")

    def supersede_insight(self, topic: str, reason: str = "") -> int:
        """
        Mark all older insights with the matching topic as [SUPERSEDED] so stale
        decisions or assumptions no longer pollute agent context.
        """
        content = self.read_memory()
        lines = content.splitlines(keepends=True)
        sections: List[str] = []
        current_block: List[str] = []

        for line in lines:
            if line.startswith("### ") and current_block:
                sections.append("".join(current_block))
                current_block = [line]
            else:
                current_block.append(line)
        if current_block:
            sections.append("".join(current_block))

        superseded_count = 0
        updated_sections = []
        for sec in sections:
            # Check if this section header matches topic and is not already superseded
            header_line = sec.splitlines()[0] if sec.splitlines() else ""
            if topic.lower() in header_line.lower() and "[SUPERSEDED]" not in header_line:
                # Replace tag in header line with [SUPERSEDED]
                new_header = re.sub(r"\[(VERIFIED|DECISION|INFERRED|HISTORICAL)\]", "[SUPERSEDED]", header_line)
                body = sec[len(header_line):]
                if reason:
                    body += f"\n- *Superseded note: {reason}*\n"
                updated_sections.append(new_header + body)
                superseded_count += 1
            else:
                updated_sections.append(sec)

        self.memory_file.write_text("".join(updated_sections), encoding="utf-8")
        return superseded_count

    def get_active_insights(self) -> str:
        """
        Return long-term memory containing only active (non-superseded) insights.
        Excludes any sections tagged [SUPERSEDED].
        """
        content = self.read_memory()
        lines = content.splitlines(keepends=True)
        sections: List[str] = []
        current_block: List[str] = []

        for line in lines:
            if line.startswith("### ") and current_block:
                sections.append("".join(current_block))
                current_block = [line]
            else:
                current_block.append(line)
        if current_block:
            sections.append("".join(current_block))

        active_sections = [s for s in sections if "[SUPERSEDED]" not in s]
        return "".join(active_sections)

    def compact_memory(self, max_inferred_entries: int = 50) -> Dict[str, Any]:
        """
        Remove oldest [INFERRED] entries when count exceeds max_inferred_entries.
        [VERIFIED], [DECISION], and active entries are never compacted.
        """
        content = self.read_memory()
        lines = content.splitlines(keepends=True)

        # Split into section blocks by ### header
        sections: List[str] = []
        current_block: List[str] = []
        for line in lines:
            if line.startswith("### ") and current_block:
                sections.append("".join(current_block))
                current_block = [line]
            else:
                current_block.append(line)
        if current_block:
            sections.append("".join(current_block))

        # Separate header from blocks
        inferred_blocks = [s for s in sections if "[INFERRED]" in s]
        non_inferred_blocks = [s for s in sections if "[INFERRED]" not in s]

        removed = 0
        if len(inferred_blocks) > max_inferred_entries:
            keep_count = max_inferred_entries
            removed = len(inferred_blocks) - keep_count
            inferred_blocks = inferred_blocks[-keep_count:]  # Keep newest

        compacted = non_inferred_blocks + inferred_blocks
        self.memory_file.write_text("".join(compacted), encoding="utf-8")
        return {
            "compacted": removed > 0,
            "removed_entries": removed,
            "remaining_inferred": len(inferred_blocks),
            "verified_entries": sum(1 for s in non_inferred_blocks if "[VERIFIED]" in s),
            "decision_entries": sum(1 for s in non_inferred_blocks if "[DECISION]" in s)
        }


    def update_working_scratchpad(self, task_name: str, status: str, notes: Optional[str] = None):
        """Update the volatile current working memory."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        content = (
            f"# WORKING — Active Task Scratchpad\n\n"
            f"- **Active Task**: `{task_name}`\n"
            f"- **Status**: `{status}`\n"
            f"- **Last Updated**: {timestamp}\n"
        )
        if notes:
            content += f"\n## Notes\n{notes.strip()}\n"
        self.working_file.write_text(content, encoding="utf-8")

    def get_summary_bundle(self) -> Dict[str, Any]:
        """Return memory status and token counts for context inspection."""
        soul = self.read_soul()
        mem = self.read_memory()
        work = self.read_working()
        return {
            "status": "active",
            "memory_dir": str(self.memory_dir),
            "soul_tokens": len(soul) // 4,
            "memory_tokens": len(mem) // 4,
            "working_tokens": len(work) // 4,
            "total_tokens": (len(soul) + len(mem) + len(work)) // 4
        }


def compact_context_text(text: str, max_lines: int = 35, max_chars_per_line: int = 140) -> str:
    """
    OpenClaw-style Context Compactor.
    Filters terminal noise, progress bars, and repetitive logs into a high-density, bounded receipt.
    """
    if not text:
        return ""

    lines = text.strip().splitlines()
    if len(lines) <= max_lines and len(text) <= max_lines * max_chars_per_line:
        return text.strip()

    # Filter out noisy progress lines (e.g. download bars, dots, empty lines)
    filtered = []
    noise_patterns = [
        re.compile(r"^\s*[\.=\-\*]{5,}\s*$"), # Dot/bar animations
        re.compile(r"\b\d+%\s*\[=*>?\s*\]"), # Download progress
        re.compile(r"^\s*$") # Blank
    ]

    for line in lines:
        if any(p.search(line) for p in noise_patterns):
            continue
        # Truncate overly wide lines
        if len(line) > max_chars_per_line:
            line = line[:max_chars_per_line - 3] + "..."
        filtered.append(line)

    if len(filtered) <= max_lines:
        return "\n".join(filtered)

    # Take head and tail with compaction notice
    half = max_lines // 2
    head = filtered[:half]
    tail = filtered[-half:]
    omitted = len(filtered) - (2 * half)

    receipt = (
        "\n".join(head)
        + f"\n\n... [Context Compactor: Omitted {omitted} redundant lines] ...\n\n"
        + "\n".join(tail)
    )
    return receipt
