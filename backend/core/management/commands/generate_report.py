"""
Management command: generate_report

Usage:
    python manage.py generate_report \\
        --shift-start "2024-01-15T07:00:00Z" \\
        --shift-end "2024-01-15T12:00:00Z" \\
        [--output report.docx] \\
        [--scenario quiet|busy|messy]

Exit codes:
    0 — success
    1 — validation error or generation/export failure (fail loudly)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.fetch_activity import fetch_activity
from core.generator import generate_sections, summarize_sections
from core.publisher import render_docx

logger = logging.getLogger(__name__)

SCENARIOS_DIR = Path(__file__).parent.parent.parent / "scenarios"
VALID_SCENARIOS = {"quiet", "busy", "messy"}


def parse_utc(value: str, field_name: str) -> datetime:
    for fmt in [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
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
    raise CommandError(
        f"Invalid datetime for '{field_name}': {value!r}. Use ISO8601, e.g. '2024-01-15T07:00:00Z'."
    )


class Command(BaseCommand):
    help = "Generate a shift handover .docx report from JSON data sources or a test scenario."

    def add_arguments(self, parser):
        parser.add_argument(
            "--shift-start",
            dest="shift_start",
            required=False,
            help="Shift start datetime in ISO8601 UTC (e.g. '2024-01-15T07:00:00Z'). "
                 "Not required when --scenario is used (scenario provides defaults).",
        )
        parser.add_argument(
            "--shift-end",
            dest="shift_end",
            required=False,
            help="Shift end datetime in ISO8601 UTC (e.g. '2024-01-15T12:00:00Z'). "
                 "Not required when --scenario is used (scenario provides defaults).",
        )
        parser.add_argument(
            "--output",
            dest="output",
            default="shift_report.docx",
            help="Output .docx file path (default: shift_report.docx).",
        )
        parser.add_argument(
            "--scenario",
            dest="scenario",
            default=None,
            choices=list(VALID_SCENARIOS),
            help="Use a test scenario (quiet/busy/messy) instead of live data sources.",
        )

    def handle(self, *args, **options):
        scenario = options.get("scenario")
        output_path = options["output"]

        # ── Resolve shift window ──────────────────────────────────────────────
        if scenario:
            scenario_path = SCENARIOS_DIR / f"{scenario}.json"
            if not scenario_path.exists():
                raise CommandError(f"Scenario file not found: {scenario_path}")
            try:
                with open(scenario_path, "r", encoding="utf-8") as f:
                    scenario_data = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                raise CommandError(f"Failed to load scenario '{scenario}': {exc}") from exc

            raw_events = scenario_data.get("events", [])
            # Scenario provides shift window defaults
            sc_start = scenario_data.get("shift_start")
            sc_end = scenario_data.get("shift_end")

            shift_start_raw = options.get("shift_start") or sc_start
            shift_end_raw = options.get("shift_end") or sc_end

            if not shift_start_raw or not shift_end_raw:
                raise CommandError(
                    "shift_start and shift_end must be provided (either via --shift-start/--shift-end "
                    "or embedded in the scenario file)."
                )
            shift_start = parse_utc(shift_start_raw, "shift_start")
            shift_end = parse_utc(shift_end_raw, "shift_end")

            self.stdout.write(
                self.style.HTTP_INFO(
                    f"[scenario={scenario}] window: {shift_start.isoformat()} -> {shift_end.isoformat()}"
                )
            )
            events = fetch_activity(shift_start, shift_end, events=raw_events)
        else:
            if not options.get("shift_start") or not options.get("shift_end"):
                raise CommandError(
                    "--shift-start and --shift-end are required when not using --scenario."
                )
            shift_start = parse_utc(options["shift_start"], "shift_start")
            shift_end = parse_utc(options["shift_end"], "shift_end")

            if shift_start >= shift_end:
                raise CommandError("--shift-start must be before --shift-end.")

            self.stdout.write(
                self.style.HTTP_INFO(
                    f"window: {shift_start.isoformat()} -> {shift_end.isoformat()}"
                )
            )
            events = fetch_activity(shift_start, shift_end)

        self.stdout.write(f"  Events fetched (after filter): {len(events)}")

        # ── Generate sections ─────────────────────────────────────────────────
        try:
            sections = generate_sections(events)
            summary = summarize_sections(sections)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"generate_sections failed: {exc}"))
            sys.exit(1)

        self.stdout.write(
            "  Sections: "
            + " | ".join(f"{k}={v}" for k, v in summary["counts"].items())
        )

        # ── Render .docx ──────────────────────────────────────────────────────
        try:
            out = render_docx(
                sections=sections,
                output_path=output_path,
                shift_start=shift_start,
                shift_end=shift_end,
            )
        except RuntimeError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            sys.exit(1)

        self.stdout.write(
            self.style.SUCCESS(f"[OK] Report written: {out}  (total items: {summary['total_items']})")
        )
