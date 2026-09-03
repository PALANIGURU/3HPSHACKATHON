"""
generator.py — Step 7: Apply sectioning rules and deduplication.

Sectioning rules:
  Completed  → status in COMPLETED_STATUSES
  In Progress → status in IN_PROGRESS_STATUSES
  Blockers   → status in BLOCKER_STATUSES
  Watch-list → status in WATCH_STATUSES

Dedup rule:
  Group events by (source, record_id).
  Sort each group by _parsed_timestamp ascending.
  Collapse to ONE line per record using the FINAL (latest) state.
  If a ticket opens AND closes inside the window, it goes to Completed
  (latest state wins).

Determinism guarantee:
  Output is sorted by (source, record_id) within each section.
  This ensures identical input always produces identical output.
"""

from datetime import datetime
from typing import Any

# ─── Status classification sets ────────────────────────────────────────────────

COMPLETED_STATUSES = frozenset(
    ["resolved", "closed", "done", "completed", "fixed", "deployed"]
)
IN_PROGRESS_STATUSES = frozenset(
    ["open", "in_progress", "investigating", "active", "acknowledged"]
)
BLOCKER_STATUSES = frozenset(
    ["blocked", "escalated", "critical", "urgent"]
)
WATCH_STATUSES = frozenset(
    ["monitoring", "watch", "pending", "deferred"]
)

# Priority order for classification (first match wins)
SECTION_PRIORITY = [
    ("completed", COMPLETED_STATUSES),
    ("blockers", BLOCKER_STATUSES),
    ("watch_list", WATCH_STATUSES),
    ("in_progress", IN_PROGRESS_STATUSES),
]

SECTION_ORDER = ["completed", "in_progress", "blockers", "watch_list"]


def _classify_status(status: str) -> str:
    """
    Classify a status string into one of the 4 section keys.
    Falls back to 'in_progress' for unknown statuses.
    """
    status_lower = status.lower().strip() if isinstance(status, str) else ""
    for section_key, status_set in SECTION_PRIORITY:
        if status_lower in status_set:
            return section_key
    # Unknown statuses treated as in_progress
    return "in_progress"


def _make_display_line(event: dict) -> dict:
    """
    Build the display dict for a single deduplicated record.
    Returns a dict with keys: source, record_id, summary, status, timestamp.
    """
    ts: datetime = event["_parsed_timestamp"]
    return {
        "source": event["source"],
        "record_id": event["record_id"],
        "summary": event["summary"],
        "status": event["status"],
        "timestamp": ts.strftime("%Y-%m-%d %H:%M UTC"),
    }


def generate_sections(events: list[dict]) -> dict[str, list[dict]]:
    """
    Apply sectioning rules and deduplication to a flat list of normalized events.

    Args:
        events: Output from fetch_activity() — flat list of normalized event dicts
                with '_parsed_timestamp' key.

    Returns:
        Dict with 4 keys: 'completed', 'in_progress', 'blockers', 'watch_list'.
        Each value is a sorted list of display dicts (one per unique record).
    """
    sections: dict[str, list[dict]] = {
        "completed": [],
        "in_progress": [],
        "blockers": [],
        "watch_list": [],
    }

    # ── Step 1: Group by (source, record_id) ──────────────────────────────────
    groups: dict[tuple[str, str], list[dict]] = {}
    for event in events:
        key = (event["source"], event["record_id"])
        groups.setdefault(key, []).append(event)

    # ── Step 2: Dedup each group — collapse to final (latest) state ───────────
    for (source, record_id), group in groups.items():
        # Sort by timestamp ascending — latest is last
        sorted_group = sorted(group, key=lambda e: e["_parsed_timestamp"])
        final_event = sorted_group[-1]  # Latest update = final state

        section_key = _classify_status(final_event["status"])
        display = _make_display_line(final_event)
        sections[section_key].append(display)

    # ── Step 3: Sort deterministically by (source, record_id) ─────────────────
    for key in sections:
        sections[key].sort(key=lambda d: (d["source"], d["record_id"]))

    return sections


def summarize_sections(sections: dict[str, list[dict]]) -> dict[str, Any]:
    """
    Return summary statistics for logging and API response metadata.
    """
    return {
        "total_items": sum(len(v) for v in sections.values()),
        "counts": {k: len(v) for k, v in sections.items()},
    }
