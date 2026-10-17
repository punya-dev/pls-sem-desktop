"""
PDF Export Module (Section 26: REP-05).
Generates publication-quality PDF reports using reportlab with clean typography,
formatted tables, narrative sections, and academic references.
"""

from typing import List, Dict, Any, Optional
import io
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)

from reporting.templates import (
    build_reflective_summary,
    build_formative_summary,
    build_discriminant_validity_summary,
    build_structural_summary,
    build_fit_summary,
)
from reporting.narrative import generate_narrative_report


def generate_pdf_report(
    results: Dict[str, Any],
    project_name: str = "PLS-SEM Project",
    dataset_name: str = "Analysis Dataset",
    model_name: str = "Path Model",
    author: Optional[str] = "Antigravity PLS-SEM Engine",
) -> bytes:
    """
    Builds a complete, formatted PDF report and returns the raw bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=10,
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=15,
    )

    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=8,
    )

    th_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1,  # Center
    )

    td_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
        alignment=0,  # Left
    )

    story = []

    # Title & Metadata
    story.append(Paragraph(f"PLS-SEM Analysis Report: {model_name}", title_style))
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph(f"Project: <b>{project_name}</b> | Dataset: <b>{dataset_name}</b> | Date: {now_str}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#cbd5e1"), spaceAfter=15))

    # Narrative Executive Summary
    story.append(Paragraph("Executive Summary & Methodology", h1_style))
    narrative_text = generate_narrative_report(results, style="apa")
    for block in narrative_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("# "):
            continue  # Skip main title since we already rendered it
        elif block.startswith("## "):
            story.append(Paragraph(block[3:], h1_style))
        elif block.startswith("### "):
            story.append(Paragraph(block[4:], h2_style))
        elif block.startswith("- "):
            items = block.split("\n- ")
            for item in items:
                clean_item = item.lstrip("- ")
                story.append(Paragraph(f"• {clean_item}", body_style))
        else:
            story.append(Paragraph(block, body_style))

    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=15))

    # Comprehensive Tables
    table_builders = [
        build_reflective_summary,
        build_formative_summary,
        build_discriminant_validity_summary,
        build_structural_summary,
        build_fit_summary,
    ]

    for builder in table_builders:
        t_data = builder(results)
        cols = t_data.get("columns", [])
        raw_rows = t_data.get("rows", [])
        if not raw_rows:
            continue

        story.append(Paragraph(t_data.get("title", "Summary Table"), h1_style))

        # Convert table to flowable paragraphs
        header_cells = [Paragraph(c, th_style) for c in cols]
        body_cells = []
        for r in raw_rows:
            body_cells.append([Paragraph(str(c), td_style) for c in r])

        table_matrix = [header_cells] + body_cells

        pdf_table = Table(table_matrix, repeatRows=1)
        pdf_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))

        story.append(pdf_table)

        # Footnotes
        notes = t_data.get("footnotes", [])
        if notes:
            story.append(Spacer(1, 4))
            for note in notes:
                story.append(Paragraph(f"<i>Note.</i> {note}", ParagraphStyle("Note", parent=body_style, fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))))

        story.append(Spacer(1, 15))

    doc.build(story)
    return buffer.getvalue()
