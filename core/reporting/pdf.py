"""SAR PDF export via ReportLab (PRD F6.3, WIREFRAMES "SAR PDF layout").

Layout: header + DRAFT watermark (until approved), case summary box, network graph
PNG, 5 narrative sections with evidence footnote markers, Appendix A (evidence
table) and Appendix B (validation result + approver). Returns PDF bytes. Lives in
``core`` and never imports streamlit.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.casegraph import load_case_subgraph
from core.utils import fmt_amount, utcnow

_BAND_HEX = {"high": "#DC2626", "medium": "#F59E0B", "low": "#16A34A"}
_SECTIONS = ["summary", "subjects", "activity", "red_flags", "conclusion"]


def case_graph_png(case_id: str, width: float = 6.0, height: float = 3.2) -> bytes:
    """Render a static PNG of the case subgraph for embedding in the PDF."""
    sub = load_case_subgraph(case_id)
    g = nx.DiGraph()
    for n in sub.nodes:
        g.add_node(n["id"], band=n["band"])
    for e in sub.edges:
        if e["source"] in g and e["target"] in g:
            g.add_edge(e["source"], e["target"], suspicious=e["suspicious"])

    fig, ax = plt.subplots(figsize=(width, height))
    if g.number_of_nodes():
        pos = nx.spring_layout(g, seed=42, k=0.9)
        node_colors = [_BAND_HEX.get(g.nodes[n]["band"], "#94A3B8") for n in g.nodes]
        edge_colors = ["#DC2626" if g.edges[e].get("suspicious") else "#CBD5E1"
                       for e in g.edges]
        nx.draw_networkx_nodes(g, pos, node_color=node_colors, node_size=700, ax=ax)
        nx.draw_networkx_edges(g, pos, edge_color=edge_colors, width=1.6,
                               arrowsize=12, ax=ax)
        nx.draw_networkx_labels(g, pos, font_size=7, ax=ax)
    ax.axis("off")
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _watermark(canvas, doc) -> None:
    """Draw a DRAFT watermark across the page."""
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 54)
    canvas.setFillColor(colors.Color(0.86, 0.15, 0.15, alpha=0.12))
    canvas.translate(A4[0] / 2, A4[1] / 2)
    canvas.rotate(45)
    canvas.drawCentredString(0, 0, "DRAFT - Human review required")
    canvas.restoreState()


def build_sar_pdf(case_id: str, result, approved: bool = False) -> bytes:
    """Build the SAR PDF for a case and drafting result; return PDF bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            title=f"SAR {case_id}")
    styles = getSampleStyleSheet()
    h = ParagraphStyle("rs-h", parent=styles["Heading2"], textColor=colors.HexColor("#1E3A8A"))
    body = styles["BodyText"]
    story: list = []

    story.append(Paragraph("RingSight — Suspicious Activity Report", styles["Title"]))
    status = "APPROVED" if approved else "DRAFT (pending human review)"
    story.append(Paragraph(
        f"Case <b>{case_id}</b> &nbsp;|&nbsp; Status: {status} &nbsp;|&nbsp; "
        f"Generated {utcnow().strftime('%Y-%m-%d %H:%M')} UTC", body))
    story.append(Spacer(1, 6 * mm))

    # Summary box.
    totals = result.pack.totals
    summary_rows = [
        ["Typology", result.typology.typology],
        ["Grounding score", f"{result.validation.grounding_score:.0f}%"],
        ["Total amount", fmt_amount(totals.get("total_amount", 0))],
        ["Transactions", str(totals.get("n_txns", 0))],
        ["Date range", str(totals.get("date_range", "n/a"))],
        ["Patterns", ", ".join(result.pack.patterns)],
    ]
    tbl = Table(summary_rows, colWidths=[40 * mm, 120 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6 * mm))

    # Network graph.
    try:
        story.append(Image(io.BytesIO(case_graph_png(case_id)), width=160 * mm, height=85 * mm))
    except Exception:  # pragma: no cover - graph optional
        story.append(Paragraph("<i>Network graph unavailable.</i>", body))
    story.append(Spacer(1, 4 * mm))

    # Narrative sections with evidence footnote markers.
    for section in _SECTIONS:
        sentences = getattr(result.narrative, section)
        if not sentences:
            continue
        story.append(Paragraph(section.replace("_", " ").title(), h))
        for sent in sentences:
            marks = "".join(f"<super>[{e}]</super>" for e in sent.evidence_ids)
            story.append(Paragraph(f"{sent.text} {marks}", body))
        story.append(Spacer(1, 3 * mm))

    # Appendix A: evidence table.
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Appendix A — Evidence", h))
    ev_rows = [["ID", "Kind", "Summary"]]
    ev_rows += [[it.id, it.kind, it.summary] for it in result.pack.items]
    ev_tbl = Table(ev_rows, colWidths=[14 * mm, 22 * mm, 124 * mm])
    ev_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(ev_tbl)

    # Appendix B: validation + approver.
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Appendix B — Validation", h))
    story.append(Paragraph(
        f"Grounding score: {result.validation.grounding_score:.0f}% "
        f"({'passed' if result.validation.passed else 'needs review'}). "
        f"Issues: {len(result.validation.issues)}.", body))
    for issue in result.validation.issues:
        story.append(Paragraph(f"• {issue.section}[{issue.index}]: {issue.problem}", body))

    on_page = (lambda c, d: None) if approved else _watermark
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    return buf.read()
