"""
generator.py — Step 7: Apply sectioning rules, deduplication, carry-forward tracking, and Slack summary output.
"""

from datetime import datetime
from typing import Any, Dict, List

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

SECTION_PRIORITY = [
    ("completed", COMPLETED_STATUSES),
    ("blockers", BLOCKER_STATUSES),
    ("watch_list", WATCH_STATUSES),
    ("in_progress", IN_PROGRESS_STATUSES),
]

def _classify_status(status: str) -> str:
    status_lower = status.lower().strip() if isinstance(status, str) else ""
    for section_key, status_set in SECTION_PRIORITY:
        if status_lower in status_set:
            return section_key
    return "in_progress"


def _make_display_line(event: dict) -> dict:
    ts: datetime = event["_parsed_timestamp"]
    return {
        "source": event["source"],
        "record_id": event["record_id"],
        "summary": event["summary"],
        "status": event["status"],
        "timestamp": ts.strftime("%Y-%m-%d %H:%M UTC"),
        "still_open": event.get("_still_open", False),
    }


def generate_sections(events: list[dict]) -> dict[str, list[dict]]:
    """
    Apply sectioning rules and deduplication to a flat list of normalized events.
    """
    sections: dict[str, list[dict]] = {
        "completed": [],
        "in_progress": [],
        "blockers": [],
        "watch_list": [],
        "still_open": [],  # Stretch: carry-forward from previous shift
    }

    groups: dict[tuple[str, str], list[dict]] = {}
    for event in events:
        key = (event["source"], event["record_id"])
        groups.setdefault(key, []).append(event)

    for (source, record_id), group in groups.items():
        sorted_group = sorted(group, key=lambda e: e["_parsed_timestamp"])
        final_event = sorted_group[-1]

        section_key = _classify_status(final_event["status"])
        display = _make_display_line(final_event)

        # Check if item is carried forward and still open
        if final_event.get("_still_open") and section_key != "completed":
            sections["still_open"].append(display)

        sections[section_key].append(display)

    for key in sections:
        sections[key].sort(key=lambda d: (d["source"], d["record_id"]))

    return sections


def generate_slack_summary(sections: dict[str, list[dict]], shift_start: datetime, shift_end: datetime) -> str:
    """
    Generate a markdown/Slack-formatted plain text summary (Stretch feature).
    """
    start_str = shift_start.strftime("%Y-%m-%d %H:%M UTC") if shift_start else "N/A"
    end_str = shift_end.strftime("%Y-%m-%d %H:%M UTC") if shift_end else "N/A"
    
    total = sum(len(v) for k, v in sections.items() if k != "still_open")
    
    lines = [
        f"*📢 SHIFT HANDOVER SUMMARY ({start_str} → {end_str})*",
        f"Total Active Items: {total}",
        ""
    ]
    
    mapping = [
        ("completed", "✅ Completed"),
        ("in_progress", "🔄 In Progress"),
        ("blockers", "🚨 Blockers"),
        ("watch_list", "👁️ Watch-List"),
        ("still_open", "⏳ Carried Over From Previous Shift"),
    ]
    
    for key, title in mapping:
        items = sections.get(key, [])
        lines.append(f"*{title} ({len(items)})*")
        if not items:
            lines.append("  • _Nothing to report_")
        else:
            for item in items:
                lines.append(f"  • `[{item['record_id']}]` {item['summary']} (_{item['status']}_)")
        lines.append("")

    return "\n".join(lines).strip()


def generate_auto_paragraph_summary(sections: dict[str, list[dict]]) -> str:
    """
    Generate a 1-paragraph summary statement for the report header (Stretch feature).
    """
    completed_cnt = len(sections.get("completed", []))
    in_prog_cnt = len(sections.get("in_progress", []))
    blockers_cnt = len(sections.get("blockers", []))
    watch_cnt = len(sections.get("watch_list", []))
    still_open_cnt = len(sections.get("still_open", []))

    summary = (
        f"During this shift, a total of {completed_cnt} issue(s) were successfully resolved, while {in_prog_cnt} item(s) "
        f"remain actively in progress. Currently, there are {blockers_cnt} critical blocker(s) requiring urgent attention "
        f"and {watch_cnt} item(s) on the watch-list. "
    )
    if still_open_cnt > 0:
        summary += f"Additionally, {still_open_cnt} item(s) carried over from the previous shift remain open."
    else:
        summary += "No unresolved items were carried over from the previous shift."

    return summary


def summarize_sections(sections: dict[str, list[dict]]) -> dict[str, Any]:
    return {
        "total_items": sum(len(v) for k, v in sections.items() if k != "still_open"),
        "counts": {k: len(v) for k, v in sections.items()},
    }
