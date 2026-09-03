"""
approval_workflow.py — Role-based Manager Approval Workflow for Shift Handover Reports.

Roles:
  - 'staff': Drafts shift handover requests, submits for review (status: 'pending_approval')
  - 'manager': Reviews pending shift handovers, approves or rejects with comments.

File-backed state: core/data/approvals.json
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

APPROVALS_FILE = Path(__file__).parent / "data" / "approvals.json"


def _load_approvals() -> Dict[str, Any]:
    if not APPROVALS_FILE.exists():
        return {"requests": {}}
    try:
        with open(APPROVALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed reading approvals.json: %s", exc)
        return {"requests": {}}


def _save_approvals(data: Dict[str, Any]):
    os.makedirs(APPROVALS_FILE.parent, exist_ok=True)
    with open(APPROVALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def submit_for_approval(
    shift_start: str,
    shift_end: str,
    submitted_by: str,
    notes: str = "",
    scenario: Optional[str] = None,
) -> Dict[str, Any]:
    """Staff action: Submit a shift handover report draft for Manager approval."""
    data = _load_approvals()

    req_id = f"REQ-{shift_start.replace(':', '').replace('-', '')[:13]}-{submitted_by.lower().replace(' ', '')}"
    now_str = datetime.now(tz=timezone.utc).isoformat()

    req = {
        "id": req_id,
        "shift_start": shift_start,
        "shift_end": shift_end,
        "submitted_by": submitted_by,
        "submitted_at": now_str,
        "notes": notes,
        "scenario": scenario,
        "status": "pending_approval",  # pending_approval | approved | rejected
        "reviewed_by": None,
        "reviewed_at": None,
        "rejection_reason": None,
    }

    data["requests"][req_id] = req
    _save_approvals(data)
    logger.info("Handover request %s submitted by staff '%s'", req_id, submitted_by)
    return req


def review_handover_request(
    request_id: str,
    manager_name: str,
    decision: str,  # 'approve' or 'reject'
    reason: str = "",
) -> Dict[str, Any]:
    """Manager action: Approve or reject a pending shift handover request."""
    data = _load_approvals()
    req = data["requests"].get(request_id)

    if not req:
        raise ValueError(f"Approval request '{request_id}' not found.")

    decision_lower = decision.lower().strip()
    if decision_lower not in ["approve", "reject"]:
        raise ValueError("Decision must be 'approve' or 'reject'.")

    now_str = datetime.now(tz=timezone.utc).isoformat()
    req["reviewed_by"] = manager_name
    req["reviewed_at"] = now_str

    if decision_lower == "approve":
        req["status"] = "approved"
        req["rejection_reason"] = None
        logger.info("Handover request %s APPROVED by manager '%s'", request_id, manager_name)
    else:
        req["status"] = "rejected"
        req["rejection_reason"] = reason or "Manager requested revisions."
        logger.info("Handover request %s REJECTED by manager '%s'", request_id, manager_name)

    data["requests"][request_id] = req
    _save_approvals(data)
    return req


def list_approval_requests(role: str = "all") -> List[Dict[str, Any]]:
    """List all approval requests."""
    data = _load_approvals()
    reqs = list(data["requests"].values())
    reqs.sort(key=lambda r: r.get("submitted_at", ""), reverse=True)
    return reqs


def check_approval_status(request_id: str) -> Optional[Dict[str, Any]]:
    """Check status of a specific request."""
    data = _load_approvals()
    return data["requests"].get(request_id)
