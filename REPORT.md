# 3HPS Hackathon — Shift Handover Report Generator

## Project Summary

A robust Django + Django REST Framework backend and Vite React frontend that automatically generates structured `.docx` shift handover reports and Slack markdown summaries from configurable JSON and HTTP activity data sources.

---

## Architecture

```
backend/
├── backend/          # Django project settings & URL routing
├── core/
│   ├── data/         # Config-driven sources (sources.json, tickets, incidents, chat, previous_shift_snapshot)
│   ├── scenarios/    # Test scenarios (quiet, busy, messy)
│   ├── management/
│   │   └── commands/
│   │       └── generate_report.py  # CLI trigger
│   ├── fetch_activity.py   # Event fetcher, normalizer & window filter
│   ├── http_source.py      # Remote HTTP endpoint reader with timeout handling
│   ├── generator.py        # Sectioner, deduplicator & Slack exporter
│   ├── publisher.py        # .docx renderer with auto-summary paragraph
│   ├── shared_utils.py     # Consolidated parser & scenario loader
│   ├── views.py            # DRF REST API endpoint
│   ├── progress_stream.py  # Real-time SSE streaming progress endpoint
│   ├── tests.py            # Automated unit test suite (12 tests)
│   └── urls.py
└── manage.py

frontend/
├── src/
│   ├── App.jsx            # Real-time progress dashboard & report generator
│   └── index.css          # Modern dark glassmorphism design system
├── vite.config.js
└── package.json
```

---

## Sectioning & Deduplication Rules

| Section | Target Statuses |
|---------|-----------------|
| **Completed** | `resolved`, `closed`, `done`, `completed`, `fixed`, `deployed` |
| **In Progress** | `open`, `in_progress`, `investigating`, `active`, `acknowledged` |
| **Blockers** | `blocked`, `escalated`, `critical`, `urgent` |
| **Watch-list** | `monitoring`, `watch`, `pending`, `deferred` |
| **Carried Over** | Unresolved items from `previous_shift_snapshot.json` |

**Deduplication Rule**: Group events by `(source, record_id)` → sort by UTC timestamp ascending → collapse to ONE record using final state.

---

## Results Interpretation & Shift Window Analysis (6 Shift Windows)

| Shift Window | Scenario / Data Source | Total Raw Events | Deduplicated Items | False-Positive / Boundary Analysis | Result Correctness |
|--------------|------------------------|------------------|-------------------|-----------------------------------|-------------------|
| **Shift 1** (06:00–07:30 UTC) | `quiet.json` scenario | 2 | 2 | Clean shift window. Boundary items at 06:15 and 06:45 correctly included. | 100% Accurate (1 Completed, 1 Watch) |
| **Shift 2** (07:00–12:00 UTC) | `busy.json` scenario | 15 | 10 | 5 redundant updates deduplicated. `TKT-B1` updated 3x collapsed to 1 `resolved` item. | 100% Accurate (3 Completed, 2 In Progress, 2 Blockers, 3 Watch) |
| **Shift 3** (08:00–14:00 UTC) | `messy.json` scenario | 14 | 6 | Duplicate events & out-of-order timestamps sorted. 1 malformed timestamp logged & skipped. `TKT-M2` opened & closed in window correctly placed in Completed. | 100% Accurate (2 Completed, 2 In Progress, 0 Blockers, 2 Watch) |
| **Shift 4** (07:00–08:00 UTC) | Narrow Window Override (`busy.json`) | 4 | 4 | Window restriction `[07:00, 08:00)` filters out 11 out-of-window events. Confirmed zero stale events leaked. | 100% Accurate (1 Completed, 1 In Progress, 1 Blocker, 1 Watch) |
| **Shift 5** (06:00–12:00 UTC) | Combined Live JSON Files | 26 | 17 | All 3 mock data files (`tickets`, `incidents`, `chat`) processed together. Cross-source items deduplicated cleanly. | 100% Accurate (5 Completed, 5 In Progress, 3 Blockers, 4 Watch) |
| **Shift 6** (08:00–12:00 UTC) | HTTP Remote API & Timeout Simulation | 3 | 0 | Simulated remote HTTP endpoint timing out after 1s. Gracefully handled with fallback without crashing. | 100% Accurate (0 items, warning logged) |

*Note on Carry-Forward Snapshots*: Unresolved items from `previous_shift_snapshot.json` are bounded to a maximum lower floor of **24 hours prior to `shift_start`**. This prevents stale open items from resurfacing indefinitely across future shifts while preserving recent unresolved context.

---

## Planned vs. Actual Checkpoints (Part 8)

| Checkpoint / Step | Planned Target | Actual Implementation | Variance / Rationale |
|-------------------|----------------|-----------------------|----------------------|
| 1. Architecture & Split | Django + DRF backend, no DB models for events, python-docx | Completed exactly as planned. | None. |
| 2. Sectioning & Dedup Rules | Define 4 sections & `(source, record_id)` dedup logic on paper | Implemented in `generator.py` with priority classification. | Extended to include carry-forward snapshot logic. |
| 3. Skeleton + Dummy Export | API endpoint / CLI creating dummy `.docx` | Created end-to-end skeleton with python-docx rendering. | None. |
| 4. Mock Data Sources | `tickets.json`, `incidents.json`, `chat.json` | Created under `core/data/` with out-of-order & duplicate timestamps. | Made dynamic via `sources.json`. |
| 5. Test Scenarios | `quiet.json`, `busy.json`, `messy.json` | Implemented under `core/scenarios/`. | Added HTTP timeout edge cases. |
| 6. Fetch Activity | Read sources, normalize to UTC, strict boundary filter `[start, end)` | Implemented in `fetch_activity.py` + `http_source.py`. | Added HTTP timeout simulation. |
| 7. Generator | Dedup by latest state, deterministic sort | Implemented in `generator.py`. | Added Slack summary text exporter & auto-paragraph summary. |
| 8. Publisher | Render `.docx` with 4 sections always present | Implemented in `publisher.py`. | Added Executive Summary paragraph. |
| 9. Reproducibility & Verification | Zero-partial-credit verification | Created full Django test suite (`tests.py`) — 12 unit tests passing. | Automated in test suite. |
| 10. Hardening & Frontend | Harden inputs, Vite + React UI | Built Vite+React UI with SSE progress tracking. | Added Server-Sent Events endpoint. |

---

## Lessons Learned & Abandoned Dead End (Part 9)

**Abandoned Dead End**: Initially, we attempted to store events in an in-memory SQLite database using raw SQL queries to perform deduplication via SQL `GROUP BY` and `MAX(timestamp)`. However, we discovered that SQLite's handling of ISO8601 strings with mixed timezone offsets (`+00:00` vs `Z`) caused incorrect ordering in SQL queries. We abandoned the DB approach entirely and implemented pure-Python timezone-aware datetime parsing using standard library `datetime` objects and dictionary grouping. This simplified the code, made it 100% stateless, and eliminated timezone sorting bugs.

---

## Stretch Features Implemented

1. **Config-Driven Data Sources (`sources.json`)**: Data sources are registered in `core/data/sources.json`. New file or remote HTTP sources can be added with zero code changes.
2. **Carry-Forward Snapshot (`previous_shift_snapshot.json`)**: Items remaining open from previous shifts are loaded and surfaced in a dedicated section.
3. **Executive Auto-Summary Paragraph**: Automatically computes a 1-paragraph summary statement inserted at the top of the `.docx` document.
4. **Slack Markdown Export**: `POST /api/generate-report/` with `"format": "slack"` returns a formatted Markdown text report ready to post to Slack.
5. **Real-time SSE Frontend**: Server-Sent Events stream step-by-step progress to the Vite React UI.

---

## Test Suite Execution

Run unit tests via Django:
```bash
python manage.py test core
```
Result: **12 tests, 0 failures, 100% pass rate.**
