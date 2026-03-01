"""Persistent memory manager for ThesisAI.

Tracks the user's thesis topic, preferred research area, discussed papers,
chosen methodology, and other contextual information across sessions.
"""

import json
import os
from datetime import datetime
from typing import Any

import config


class MemoryManager:
    """JSON-file-backed memory for cross-session context."""

    def __init__(self, filepath: str | None = None):
        self.filepath = filepath or config.MEMORY_FILE
        self.data: dict[str, Any] = self._load()

    # ── persistence ──────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Merge with defaults so new fields are always present
                    merged = self._default()
                    merged.update(loaded)
                    return merged
            except (json.JSONDecodeError, IOError):
                return self._default()
        return self._default()

    def _default(self) -> dict[str, Any]:
        return {
            "thesis_topic": None,
            "research_area": None,
            "methodology": None,
            "supervisor": None,
            "university": None,
            "deadline": None,
            "discussed_papers": [],
            "key_decisions": [],
            "custom_notes": [],
            "progress_log": [],
            "last_updated": None,
        }

    def save(self) -> None:
        self.data["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass  # Read-only filesystem (e.g., Vercel)

    # ── setters ──────────────────────────────────────────────────

    def set_field(self, field: str, value: str) -> None:
        """Set any simple text field."""
        if field in ("thesis_topic", "research_area", "methodology",
                     "supervisor", "university", "deadline"):
            self.data[field] = value
            self.save()

    def set_thesis_topic(self, topic: str) -> None:
        self.set_field("thesis_topic", topic)

    def set_research_area(self, area: str) -> None:
        self.set_field("research_area", area)

    def set_methodology(self, methodology: str) -> None:
        self.set_field("methodology", methodology)

    # ── list operations ──────────────────────────────────────────

    def add_paper(self, title: str, summary: str = "", url: str = "") -> None:
        paper = {
            "title": title,
            "summary": summary,
            "url": url,
            "added": datetime.now().isoformat(),
        }
        if not any(p["title"] == title for p in self.data["discussed_papers"]):
            self.data["discussed_papers"].append(paper)
            self.save()

    def add_decision(self, decision: str) -> None:
        entry = {"decision": decision, "date": datetime.now().isoformat()}
        self.data["key_decisions"].append(entry)
        self.save()

    def add_note(self, note: str) -> None:
        entry = {"note": note, "date": datetime.now().isoformat()}
        self.data["custom_notes"].append(entry)
        self.save()

    def add_progress(self, milestone: str) -> None:
        entry = {"milestone": milestone, "date": datetime.now().isoformat()}
        self.data["progress_log"].append(entry)
        self.save()

    def remove_item(self, list_name: str, index: int) -> bool:
        """Remove an item from a list field by index. Returns True on success."""
        if list_name in ("discussed_papers", "key_decisions",
                         "custom_notes", "progress_log"):
            items = self.data.get(list_name, [])
            if 0 <= index < len(items):
                items.pop(index)
                self.save()
                return True
        return False

    def clear_field(self, field: str) -> None:
        """Clear a field — set text to None, or list to []."""
        if field in ("thesis_topic", "research_area", "methodology",
                     "supervisor", "university", "deadline"):
            self.data[field] = None
            self.save()
        elif field in ("discussed_papers", "key_decisions",
                       "custom_notes", "progress_log"):
            self.data[field] = []
            self.save()

    def get_full_data(self) -> dict[str, Any]:
        """Return full structured memory for the UI."""
        return {
            "thesis_topic": self.data.get("thesis_topic"),
            "research_area": self.data.get("research_area"),
            "methodology": self.data.get("methodology"),
            "supervisor": self.data.get("supervisor"),
            "university": self.data.get("university"),
            "deadline": self.data.get("deadline"),
            "discussed_papers": self.data.get("discussed_papers", []),
            "key_decisions": self.data.get("key_decisions", []),
            "custom_notes": self.data.get("custom_notes", []),
            "progress_log": self.data.get("progress_log", []),
            "last_updated": self.data.get("last_updated"),
        }

    # ── context rendering ────────────────────────────────────────

    def render_context(self) -> str:
        """Produce a concise text summary for injection into the system prompt."""
        parts: list[str] = []

        if self.data.get("thesis_topic"):
            parts.append(f"Thesis topic: {self.data['thesis_topic']}")
        if self.data.get("research_area"):
            parts.append(f"Research area: {self.data['research_area']}")
        if self.data.get("methodology"):
            parts.append(f"Chosen methodology: {self.data['methodology']}")
        if self.data.get("supervisor"):
            parts.append(f"Supervisor: {self.data['supervisor']}")
        if self.data.get("university"):
            parts.append(f"University: {self.data['university']}")
        if self.data.get("deadline"):
            parts.append(f"Deadline: {self.data['deadline']}")

        papers = self.data.get("discussed_papers", [])
        if papers:
            titles = ", ".join(p["title"] for p in papers[-10:])
            parts.append(f"Previously discussed papers: {titles}")

        decisions = self.data.get("key_decisions", [])
        if decisions:
            recent = [d["decision"] for d in decisions[-5:]]
            parts.append("Recent decisions: " + "; ".join(recent))

        notes = self.data.get("custom_notes", [])
        if notes:
            recent = [n["note"] for n in notes[-5:]]
            parts.append("Notes: " + "; ".join(recent))

        progress = self.data.get("progress_log", [])
        if progress:
            recent = [p["milestone"] for p in progress[-5:]]
            parts.append("Progress: " + "; ".join(recent))

        return "\n".join(parts) if parts else "No prior context available."
