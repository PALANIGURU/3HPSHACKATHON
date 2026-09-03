"""
views.py — Step 8/9: DRF API endpoint for generating shift handover reports.

Endpoint:
  POST /api/generate-report/

Request body (JSON):
  {
    "shift_start": "2024-01-15T07:00:00Z",   # required
    "shift_end":   "2024-01-15T12:00:00Z",   # required
    "scenario":    "quiet|busy|messy"         # optional, overrides data sources
  }

Response:
  - 200: .docx file download (Content-Disposition: attachment)
  - 400: JSON error (bad parameters)
  - 500: JSON error (generation/export failed)
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from django.http import FileResponse, JsonResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request

from .fetch_activity import fetch_activity
from .generator import generate_sections, summarize_sections
from .publisher import render_docx

logger = logging.getLogger(__name__)

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
VALID_SCENARIOS = {"quiet", "busy", "messy"}


def _parse_utc_param(value: str, field_name: str) -> datetime:
    """Parse a datetime string from a request parameter. Raises ValueError on failure."""
    if not value:
        raise ValueError(f"'{field_name}' is required.")
    value = value.strip()
    for fmt in [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",  # naive — assumed UTC
    ]:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(
        f"'{field_name}' has an invalid datetime format: {value!r}. "
        "Use ISO8601, e.g. '2024-01-15T07:00:00Z'."
    )


@api_view(["POST"])
def generate_report(request: Request):
    """
    POST /api/generate-report/

    Accepts shift_start, shift_end, and optional scenario.
    Returns a .docx file download or a JSON error.
    """
    # ── Parse request body ────────────────────────────────────────────────────
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON body."}, status=400
        )

    # Validate shift window
    try:
        shift_start = _parse_utc_param(body.get("shift_start", ""), "shift_start")
        shift_end = _parse_utc_param(body.get("shift_end", ""), "shift_end")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if shift_start >= shift_end:
        return JsonResponse(
            {"error": "'shift_start' must be before 'shift_end'."}, status=400
        )

    # Validate scenario (optional)
    scenario = body.get("scenario", "").strip().lower() or None
    if scenario and scenario not in VALID_SCENARIOS:
        return JsonResponse(
            {
                "error": f"Invalid scenario '{scenario}'. Valid options: {sorted(VALID_SCENARIOS)}"
            },
            status=400,
        )

    # ── Fetch events ──────────────────────────────────────────────────────────
    try:
        if scenario:
            scenario_path = SCENARIOS_DIR / f"{scenario}.json"
            try:
                with open(scenario_path, "r", encoding="utf-8") as f:
                    scenario_data = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Failed to load scenario '%s': %s", scenario, exc)
                return JsonResponse(
                    {"error": f"Could not load scenario '{scenario}': {exc}"}, status=500
                )
            raw_events = scenario_data.get("events", [])
            # Use scenario's own shift window if caller didn't override
            if not body.get("shift_start") and "shift_start" in scenario_data:
                shift_start = _parse_utc_param(scenario_data["shift_start"], "shift_start")
            if not body.get("shift_end") and "shift_end" in scenario_data:
                shift_end = _parse_utc_param(scenario_data["shift_end"], "shift_end")
            events = fetch_activity(shift_start, shift_end, events=raw_events)
        else:
            events = fetch_activity(shift_start, shift_end)

    except Exception as exc:
        logger.exception("Error during fetch_activity: %s", exc)
        return JsonResponse(
            {"error": f"Failed to fetch activity data: {exc}"}, status=500
        )

    # ── Generate sections ─────────────────────────────────────────────────────
    try:
        sections = generate_sections(events)
        summary = summarize_sections(sections)
        logger.info(
            "Report generated for window [%s, %s): %s",
            shift_start.isoformat(),
            shift_end.isoformat(),
            summary,
        )
    except Exception as exc:
        logger.exception("Error during generate_sections: %s", exc)
        return JsonResponse(
            {"error": f"Failed to generate report sections: {exc}"}, status=500
        )

    # ── Render .docx ──────────────────────────────────────────────────────────
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".docx", delete=False, prefix="shift_report_"
        ) as tmp:
            tmp_path = tmp.name

        render_docx(
            sections=sections,
            output_path=tmp_path,
            shift_start=shift_start,
            shift_end=shift_end,
        )
    except RuntimeError as exc:
        logger.error("render_docx failed: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)
    except Exception as exc:
        logger.exception("Unexpected error in render_docx: %s", exc)
        return JsonResponse(
            {"error": f"Unexpected export failure: {exc}"}, status=500
        )

    # ── Stream file back ──────────────────────────────────────────────────────
    filename = (
        f"shift_report_{shift_start.strftime('%Y%m%d_%H%M')}_{shift_end.strftime('%H%M')}.docx"
    )
    try:
        response = FileResponse(
            open(tmp_path, "rb"),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Report-Items"] = str(summary["total_items"])
        response["X-Report-Counts"] = json.dumps(summary["counts"])
        return response
    except Exception as exc:
        logger.error("Failed to stream report file: %s", exc)
        return JsonResponse({"error": f"Failed to deliver report: {exc}"}, status=500)


@api_view(["GET"])
def health_check(request: Request):
    """GET /api/health/ — simple liveness probe."""
    return JsonResponse({"status": "ok", "service": "3HPS Shift Handover API"})
