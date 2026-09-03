"""
pdf_publisher.py — High-impact, visually grand PDF report generator using ReportLab.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from .generator import generate_auto_paragraph_summary

SECTION_CONFIG = [
    {
        "key": "completed",
        "title": "COMPLETED ITEMS",
        "bg_color": colors.HexColor("#052E16"),
        "text_color": colors.HexColor("#4ADE80"),
        "border_color": colors.HexColor("#166534"),
        "empty_msg": "No completed items to report in this shift window.",
    },
    {
        "key": "in_progress",
        "title": "IN PROGRESS ITEMS",
        "bg_color": colors.HexColor("#172554"),
        "text_color": colors.HexColor("#60A5FA"),
        "border_color": colors.HexColor("#1E40AF"),
        "empty_msg": "No active in-progress items.",
    },
    {
        "key": "blockers",
        "title": "CRITICAL BLOCKERS",
        "bg_color": colors.HexColor("#450A0A"),
        "text_color": colors.HexColor("#F87171"),
        "border_color": colors.HexColor("#991B1B"),
        "empty_msg": "No critical blockers reported.",
    },
    {
        "key": "watch_list",
        "title": "WATCH-LIST ITEMS",
        "bg_color": colors.HexColor("#451A03"),
        "text_color": colors.HexColor("#FBBF24"),
        "border_color": colors.HexColor("#92400E"),
        "empty_msg": "No watch-list items.",
    },
    {
        "key": "still_open",
        "title": "CARRIED OVER FROM PREVIOUS SHIFT",
        "bg_color": colors.HexColor("#2E1065"),
        "text_color": colors.HexColor("#C084FC"),
        "border_color": colors.HexColor("#6B21A8"),
        "empty_msg": "No carried-over items.",
    },
]


def render_pdf(
    sections: dict,
    output_path: str,
    shift_start: Optional[datetime] = None,
    shift_end: Optional[datetime] = None,
    generated_at: Optional[datetime] = None,
) -> str:
    """
    Render a visually grand PDF shift handover report.
    """
    try:
        if generated_at is None:
            generated_at = datetime.now(tz=timezone.utc)

        output_path = str(output_path)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()

        # Styles
        banner_title = ParagraphStyle(
            "BannerTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=30,
            textColor=colors.white,
            alignment=TA_CENTER,
        )

        banner_sub = ParagraphStyle(
            "BannerSub",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#94A3B8"),
            alignment=TA_CENTER,
        )

        win_meta = ParagraphStyle(
            "WinMeta",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#E2E8F0"),
            alignment=TA_CENTER,
        )

        exec_label = ParagraphStyle(
            "ExecLabel",
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#F8FAFC"),
        )

        exec_body = ParagraphStyle(
            "ExecBody",
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#CBD5E1"),
        )

        item_style = ParagraphStyle(
            "ItemText",
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#F8FAFC"),
        )

        empty_style = ParagraphStyle(
            "EmptyText",
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#64748B"),
        )

        story = []

        # ── 1. Top Header Banner Box ───────────────────────────────────────────
        win_str = (
            f"SHIFT WINDOW: {shift_start.strftime('%Y-%m-%d %H:%M UTC')}  →  "
            f"{shift_end.strftime('%Y-%m-%d %H:%M UTC')}"
            if shift_start and shift_end
            else "SHIFT HANDOVER REPORT"
        )

        header_data = [
            [Paragraph("SHIFT HANDOVER REPORT", banner_title)],
            [Paragraph(win_str, win_meta)],
            [Paragraph(f"3HPS Handover Generator  |  Generated: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}", banner_sub)],
        ]

        header_table = Table(header_data, colWidths=[540])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#090D16")),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,-1), (-1,-1), 16),
            ('LINEBELOW', (0,-1), (-1,-1), 2, colors.HexColor("#38BDF8")),
        ]))

        story.append(header_table)
        story.append(Spacer(1, 14))

        # ── 2. Metric Summary Cards Table ──────────────────────────────────────
        completed_cnt = len(sections.get("completed", []))
        in_prog_cnt = len(sections.get("in_progress", []))
        blockers_cnt = len(sections.get("blockers", []))
        watch_cnt = len(sections.get("watch_list", []))
        total_cnt = sum(len(v) for k, v in sections.items() if k != "still_open")

        stat_card_style_num = ParagraphStyle("StatNum", fontName="Helvetica-Bold", fontSize=20, leading=22, alignment=TA_CENTER)
        stat_card_style_lbl = ParagraphStyle("StatLbl", fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#94A3B8"))

        stats_data = [
            [
                Paragraph(f"<font color='#FFFFFF'>{total_cnt}</font>", stat_card_style_num),
                Paragraph(f"<font color='#4ADE80'>{completed_cnt}</font>", stat_card_style_num),
                Paragraph(f"<font color='#60A5FA'>{in_prog_cnt}</font>", stat_card_style_num),
                Paragraph(f"<font color='#F87171'>{blockers_cnt}</font>", stat_card_style_num),
                Paragraph(f"<font color='#FBBF24'>{watch_cnt}</font>", stat_card_style_num),
            ],
            [
                Paragraph("TOTAL ITEMS", stat_card_style_lbl),
                Paragraph("COMPLETED", stat_card_style_lbl),
                Paragraph("IN PROGRESS", stat_card_style_lbl),
                Paragraph("BLOCKERS", stat_card_style_lbl),
                Paragraph("WATCH-LIST", stat_card_style_lbl),
            ]
        ]

        stats_table = Table(stats_data, colWidths=[108, 108, 108, 108, 108])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0F172A")),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#1E293B")),
        ]))

        story.append(stats_table)
        story.append(Spacer(1, 14))

        # ── 3. Executive Summary Block ────────────────────────────────────────
        exec_text = generate_auto_paragraph_summary(sections)
        exec_data = [
            [Paragraph("EXECUTIVE SUMMARY", exec_label)],
            [Paragraph(exec_text, exec_body)],
        ]
        exec_table = Table(exec_data, colWidths=[540])
        exec_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0F172A")),
            ('PADDING', (0,0), (-1,-1), 12),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#334155")),
        ]))

        story.append(exec_table)
        story.append(Spacer(1, 16))

        # ── 4. Section Blocks ──────────────────────────────────────────────────
        for cfg in SECTION_CONFIG:
            key = cfg["key"]
            items = sections.get(key, [])

            if key == "still_open" and not items:
                continue

            sec_title_style = ParagraphStyle(
                f"SecTitle_{key}",
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=14,
                textColor=cfg["text_color"],
            )

            sec_rows = [[Paragraph(f"{cfg['title']} ({len(items)})", sec_title_style)]]

            if not items:
                sec_rows.append([Paragraph(cfg["empty_msg"], empty_style)])
            else:
                for item in items:
                    formatted_line = (
                        f"<b>[{item['record_id']}]</b>  {item['summary']}<br/>"
                        f"<font color='#94A3B8'>Status: {item['status']}  |  Timestamp: {item['timestamp']}</font>"
                    )
                    sec_rows.append([Paragraph(f"• {formatted_line}", item_style)])

            sec_table = Table(sec_rows, colWidths=[540])
            sec_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), cfg["bg_color"]),
                ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#0B0F19")),
                ('PADDING', (0,0), (-1,-1), 10),
                ('BOX', (0,0), (-1,-1), 1, cfg["border_color"]),
                ('INNERGRID', (0,1), (-1,-1), 0.5, colors.HexColor("#1E293B")),
            ]))

            story.append(sec_table)
            story.append(Spacer(1, 12))

        # ── 5. Footer ─────────────────────────────────────────────────────────
        footer_p = Paragraph(
            "AUTO-GENERATED BY 3HPS SHIFT HANDOVER GENERATOR  |  CONFIDENTIAL",
            ParagraphStyle("FooterText", fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#475569"))
        )
        story.append(Spacer(1, 10))
        story.append(footer_p)

        doc.build(story)
        return output_path

    except Exception as exc:
        raise RuntimeError(f"Failed to render PDF report to '{output_path}': {exc}") from exc
