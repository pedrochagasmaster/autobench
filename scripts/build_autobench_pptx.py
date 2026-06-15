"""Generate an editable, Mastercard-branded PPTX of the Autobench v3.0 deck.

Content is sourced from ``docs/Autobench_v3.0_Precision_Compliance.pdf`` and
restyled with the visual identity of
``docs/Acquiring_Performance_Map_New_Data_Strategy-v2 1.pdf`` (the Mastercard
"Acquiring Performance Map" template).

The output is a fully native PowerPoint file: every element is a real shape,
text box, or table, so the deck can be edited in PowerPoint/Keynote/Google
Slides without any rasterised images.

Usage::

    py scripts/build_autobench_pptx.py [output.pptx]
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

# --------------------------------------------------------------------------- #
# Brand palette (sampled directly from the Mastercard template PDF)
# --------------------------------------------------------------------------- #
ORANGE = RGBColor(0xFF, 0x67, 0x1B)        # accent rule / bands / header cards
ORANGE_DEEP = RGBColor(0xF3, 0x70, 0x21)   # darker accent
MC_RED = RGBColor(0xEB, 0x00, 0x1B)        # Mastercard logo red
MC_YELLOW = RGBColor(0xF7, 0x9E, 0x1B)     # Mastercard logo amber
MC_OVERLAP = RGBColor(0xFF, 0x5F, 0x00)    # logo intersection orange
INK = RGBColor(0x17, 0x17, 0x17)           # primary text
GRAY = RGBColor(0x59, 0x59, 0x59)          # secondary text
LIGHT_GRAY = RGBColor(0x8C, 0x8C, 0x8C)    # footer / captions
HAIRLINE = RGBColor(0xD2, 0xD2, 0xD2)      # thin rules / borders
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CREAM = RGBColor(0xF4, 0xF2, 0xEF)         # title-slide base
CREAM_LIGHT = RGBColor(0xFA, 0xF9, 0xF7)   # title-slide circle
PANEL = RGBColor(0xF7, 0xF6, 0xF4)         # soft panel fill
PANEL_BORDER = RGBColor(0xE3, 0xE1, 0xDE)
DARK_BG = RGBColor(0x16, 0x16, 0x16)       # closing slide
NAVY = RGBColor(0x1F, 0x2D, 0x52)          # table header / deep accent

HEAD_FONT = "Arial"   # stand-in for "Mark Offc For MC"
BODY_FONT = "Arial"   # stand-in for "Mark For MC Narrow"

# 16:9 widescreen
SLIDE_W = Emu(12192000)
SLIDE_H = Emu(6858000)

MARGIN = Pt(38)
CONTENT_W = SLIDE_W - MARGIN * 2

CONFIDENTIAL = "\u00a92025 Mastercard. Proprietary and Confidential"


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #
def _set_fill(shape, color):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color


def _no_line(shape):
    shape.line.fill.background()


def _line(shape, color, width=Pt(1)):
    shape.line.color.rgb = color
    shape.line.width = width


def _no_shadow(shape):
    # Strip the theme style reference (carries an effectRef -> drop shadow)
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)
    el = shape._element.spPr
    if el.find(qn("a:effectLst")) is None:
        el.append(el.makeelement(qn("a:effectLst"), {}))


def add_rect(slide, x, y, w, h, fill=None, line=None, line_w=Pt(1),
             rounded=False):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        x, y, w, h,
    )
    if fill is None:
        shp.fill.background()
    else:
        _set_fill(shp, fill)
    if line is None:
        _no_line(shp)
    else:
        _line(shp, line, line_w)
    _no_shadow(shp)
    if rounded:
        try:
            shp.adjustments[0] = 0.06
        except (IndexError, KeyError):
            pass
    return shp


def add_oval(slide, x, y, w, h, fill, alpha=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, w, h)
    _set_fill(shp, fill)
    _no_line(shp)
    _no_shadow(shp)
    if alpha is not None:
        _set_alpha(shp, alpha)
    return shp


def _set_alpha(shape, alpha_pct):
    """Apply transparency (0-100, where 100 = fully transparent)."""
    srgb = shape.fill.fore_color._xFill.find(qn("a:srgbClr"))
    if srgb is None:
        return
    a = srgb.makeelement(qn("a:alpha"), {"val": str(int((100 - alpha_pct) * 1000))})
    srgb.append(a)


def _apply_runs(p, runs, size, color, font=BODY_FONT, bold=False,
                line_spacing=None, space_after=None, align=None):
    if align is not None:
        p.alignment = align
    if line_spacing is not None:
        p.line_spacing = line_spacing
    if space_after is not None:
        p.space_after = space_after
    for text, opts in runs:
        r = p.add_run()
        r.text = text
        f = r.font
        f.size = size
        f.name = opts.get("font", font)
        f.bold = opts.get("bold", bold)
        f.italic = opts.get("italic", False)
        f.color.rgb = opts.get("color", color)


def add_text(slide, x, y, w, h, paragraphs, anchor=MSO_ANCHOR.TOP,
             wrap=True):
    """paragraphs: list of dicts with keys runs/size/color/font/bold/...

    Each ``runs`` entry is a list of ``(text, opts)`` tuples.
    """
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        _apply_runs(
            p,
            para["runs"],
            para.get("size", Pt(14)),
            para.get("color", INK),
            font=para.get("font", BODY_FONT),
            bold=para.get("bold", False),
            line_spacing=para.get("line_spacing"),
            space_after=para.get("space_after"),
            align=para.get("align"),
        )
    return tb


def plain(text, **opts):
    """Convenience: a single-run paragraph spec."""
    return [(text, opts)]


# --------------------------------------------------------------------------- #
# Brand furniture
# --------------------------------------------------------------------------- #
def mastercard_logo(slide, right, top, diameter):
    """Draw the two-circle Mastercard mark (vector, editable)."""
    overlap = diameter * 0.42
    total_w = diameter * 2 - overlap
    left = right - total_w
    red = add_oval(slide, left, top, diameter, diameter, MC_RED)
    yellow = add_oval(slide, left + diameter - overlap, top, diameter,
                      diameter, MC_YELLOW)
    # intersection lens (semi-transparent orange on top)
    lens = add_oval(slide, left + diameter - overlap, top, overlap, diameter,
                    MC_OVERLAP)
    _set_alpha(lens, 35)
    return red, yellow


def footer(slide, page_no, total, dark=False):
    txt_color = LIGHT_GRAY if not dark else RGBColor(0x9A, 0x9A, 0x9A)
    # page number, bottom-left
    add_text(
        slide, MARGIN, SLIDE_H - Pt(30), Pt(120), Pt(20),
        [{"runs": plain(f"{page_no}", color=txt_color, bold=True),
          "size": Pt(9), "font": HEAD_FONT}],
        anchor=MSO_ANCHOR.MIDDLE,
    )
    # vertical confidential note on right edge
    box = slide.shapes.add_textbox(SLIDE_W - Pt(20), Pt(120), Pt(16),
                                   SLIDE_H - Pt(260))
    tf = box.text_frame
    tf.word_wrap = False
    tf.margin_left = 0
    tf.margin_right = 0
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = CONFIDENTIAL
    r.font.size = Pt(6)
    r.font.name = HEAD_FONT
    r.font.color.rgb = txt_color
    bodyPr = tf._txBody.find(qn("a:bodyPr"))
    bodyPr.set("vert", "vert270")
    # logo bottom-right
    mastercard_logo(slide, SLIDE_W - MARGIN, SLIDE_H - Pt(54), Pt(30))


def header(slide, headline, section_label):
    """Bold headline + section label + full-width orange rule."""
    add_text(
        slide, MARGIN, Pt(28), CONTENT_W, Pt(96),
        [{"runs": plain(headline, color=INK), "size": Pt(26), "bold": True,
          "font": HEAD_FONT, "line_spacing": 1.05}],
    )
    label_y = Pt(118)
    add_text(
        slide, MARGIN, label_y, CONTENT_W, Pt(22),
        [{"runs": plain(section_label, color=INK), "size": Pt(13),
          "bold": True, "font": HEAD_FONT}],
    )
    rule = add_rect(slide, MARGIN, label_y + Pt(24), CONTENT_W, Pt(2.2),
                    fill=ORANGE)
    return rule.top + rule.height


def title_header(slide, title, subtitle):
    """Lighter headline style (title + thin grey subtitle) for table slides."""
    add_text(
        slide, MARGIN, Pt(40), CONTENT_W, Pt(60),
        [{"runs": plain(title, color=INK), "size": Pt(30), "bold": True,
          "font": HEAD_FONT}],
    )
    add_text(
        slide, MARGIN, Pt(96), CONTENT_W, Pt(40),
        [{"runs": plain(subtitle, color=GRAY), "size": Pt(15),
          "font": BODY_FONT, "line_spacing": 1.1}],
    )
    return Pt(150)


def bg(slide, color=WHITE):
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, fill=color)


def bullets_spec(items, size=Pt(13), color=INK, bullet_color=GRAY,
                 line_spacing=1.12, space_after=Pt(7)):
    """Build paragraph specs with hanging bullets from rich item tuples.

    Each item is a list of (text, opts) runs.
    """
    paras = []
    for runs in items:
        full = [("\u2022  ", {"color": bullet_color, "bold": True})] + list(runs)
        paras.append({
            "runs": full, "size": size, "color": color, "font": BODY_FONT,
            "line_spacing": line_spacing, "space_after": space_after,
        })
    return paras


# --------------------------------------------------------------------------- #
# Slide builders
# --------------------------------------------------------------------------- #
def new_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])  # blank


def slide_title(prs):
    s = new_slide(prs)
    bg(s, CREAM)
    # large soft concentric "Performance Map" arc — overlapping circle band
    c = add_oval(s, Emu(int(SLIDE_W * 0.30)), Emu(int(-SLIDE_H * 0.55)),
                 Emu(int(SLIDE_W * 0.95)), Emu(int(SLIDE_H * 1.9)),
                 CREAM_LIGHT)
    _no_shadow(c)
    ring = s.shapes.add_shape(
        MSO_SHAPE.OVAL, Emu(int(SLIDE_W * 0.33)), Emu(int(-SLIDE_H * 0.5)),
        Emu(int(SLIDE_W * 0.9)), Emu(int(SLIDE_H * 1.8)))
    ring.fill.background()
    _line(ring, HAIRLINE, Pt(0.75))
    _no_shadow(ring)

    add_text(
        s, MARGIN + Pt(10), Pt(220), Pt(760), Pt(120),
        [{"runs": plain("Autobench v3.0", color=INK), "size": Pt(46),
          "font": HEAD_FONT, "line_spacing": 1.0},
         {"runs": plain("The Precision Compliance Engine", color=INK),
          "size": Pt(46), "font": HEAD_FONT, "line_spacing": 1.0}],
    )
    add_text(
        s, MARGIN + Pt(12), Pt(360), Pt(620), Pt(60),
        [{"runs": plain(
            "Next-Generation Benchmarking, Minimal Distortion, "
            "Absolute Control.", color=INK), "size": Pt(18), "bold": True,
          "font": HEAD_FONT, "line_spacing": 1.1}],
    )
    add_text(
        s, MARGIN + Pt(12), Pt(450), Pt(620), Pt(60),
        [{"runs": plain("Executive Overview & Operational Capabilities",
                        color=GRAY), "size": Pt(12), "font": BODY_FONT},
         {"runs": plain("Mastercard Advisors \u2013 Performance Analytics",
                        color=GRAY), "size": Pt(12), "font": BODY_FONT}],
    )
    mastercard_logo(s, SLIDE_W - MARGIN, Pt(34), Pt(46))
    return s


def slide_paradox(prs, page):
    s = new_slide(prs)
    bg(s)
    header(
        s,
        "Compliant benchmarking forces a trade-off between privacy and "
        "market truth \u2014 Autobench removes it.",
        "The paradox of compliant benchmarking",
    )
    top = Pt(195)
    gap = Pt(150)
    col_w = Emu(int((CONTENT_W - gap) / 2))
    right_x = MARGIN + col_w + gap

    def column(x, title, items, title_color):
        add_text(s, x, top, col_w, Pt(34),
                 [{"runs": plain(title, color=title_color), "size": Pt(17),
                   "bold": True, "font": HEAD_FONT}])
        add_text(s, x, top + Pt(40), col_w, Pt(220),
                 bullets_spec([plain(i) for i in items], size=Pt(13.5),
                              space_after=Pt(9)))

    column(MARGIN, "The Risk: Control 3 Constraints", [
        "Strict concentration caps (e.g., no peer over 25% share)",
        "Minimum participant thresholds",
        "Zero-tolerance regulatory environment",
        "Manual compliance weighting destroys data fidelity",
    ], INK)
    column(right_x, "The Goal: Market Reality", [
        "Maintain exact market positioning",
        "Preserve rank integrity across dimensions",
        "Deliver actionable merchant and issuer performance data",
    ], INK)

    # central arrow with label
    arrow = s.shapes.add_shape(
        MSO_SHAPE.RIGHT_ARROW, MARGIN + col_w + Pt(8), top + Pt(70),
        gap - Pt(16), Pt(54))
    _set_fill(arrow, ORANGE)
    _no_line(arrow)
    _no_shadow(arrow)
    add_text(s, MARGIN + col_w - Pt(20), top + Pt(128), gap + Pt(40), Pt(30),
             [{"runs": plain("The Autobench Imperative", color=ORANGE_DEEP),
               "size": Pt(10.5), "bold": True, "font": HEAD_FONT,
               "align": PP_ALIGN.CENTER}])

    # bottom orange solution band
    add_rect(s, MARGIN, SLIDE_H - Pt(150), CONTENT_W, Pt(78),
             fill=ORANGE, rounded=True)
    add_text(
        s, MARGIN + Pt(28), SLIDE_H - Pt(150), CONTENT_W - Pt(56), Pt(78),
        [{"runs": [
            ("The Solution: ", {"bold": True, "color": WHITE}),
            ("Autobench v3.0 uses advanced Linear Programming (LP) to enforce "
             "absolute privacy compliance while mathematically minimizing "
             "distortion.", {"color": WHITE})],
          "size": Pt(14), "font": BODY_FONT, "line_spacing": 1.12,
          "align": PP_ALIGN.CENTER}],
        anchor=MSO_ANCHOR.MIDDLE,
    )
    footer(s, page, TOTAL)
    return s


def _phase_card(slide, x, y, w, h, title, subtitle, rows, accent=NAVY):
    add_rect(slide, x, y, w, h, fill=PANEL, line=PANEL_BORDER, line_w=Pt(1),
             rounded=True)
    head_h = Pt(60) if subtitle else Pt(46)
    paras = [{"runs": plain(title, color=accent), "size": Pt(15),
              "bold": True, "font": HEAD_FONT, "align": PP_ALIGN.CENTER,
              "line_spacing": 1.0}]
    if subtitle:
        paras.append({"runs": plain(subtitle, color=GRAY), "size": Pt(10),
                      "font": "Consolas", "align": PP_ALIGN.CENTER})
    add_text(slide, x + Pt(8), y + Pt(14), w - Pt(16), head_h, paras,
             anchor=MSO_ANCHOR.TOP)
    inner_y = y + head_h + Pt(14)
    inner_x = x + Pt(16)
    inner_w = w - Pt(32)
    avail = (y + h) - inner_y - Pt(16)
    rh = min(Pt(56), Emu(int(avail / max(len(rows), 1))) - Pt(10))
    for r in rows:
        add_rect(slide, inner_x, inner_y, inner_w, rh, fill=WHITE,
                 line=HAIRLINE, line_w=Pt(0.75), rounded=True)
        add_text(slide, inner_x + Pt(8), inner_y, inner_w - Pt(16), rh,
                 [{"runs": plain(r, color=INK), "size": Pt(11.5),
                   "font": BODY_FONT, "align": PP_ALIGN.CENTER,
                   "line_spacing": 1.0}],
                 anchor=MSO_ANCHOR.MIDDLE)
        inner_y += rh + Pt(10)


def _connector_arrow(slide, x, y, w, h):
    a = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x, y, w, h)
    _set_fill(a, NAVY)
    _no_line(a)
    _no_shadow(a)


def slide_architecture(prs, page):
    s = new_slide(prs)
    bg(s)
    header(
        s,
        "Three coordinated phases turn raw data into compliant, "
        "audit-ready intelligence.",
        "The Autobench architecture",
    )
    top = Pt(190)
    h = Pt(290)
    arrow_w = Pt(46)
    col_w = Emu(int((CONTENT_W - arrow_w * 2) / 3))
    x0 = MARGIN
    x1 = x0 + col_w + arrow_w
    x2 = x1 + col_w + arrow_w

    _phase_card(s, x0, top, col_w, h, "Phase 1", "Ingestion Interfaces", [
        "CLI (Automated Pipelines)",
        "TUI (Textual User Interface for Analysts)",
    ])
    _phase_card(s, x1, top, col_w, h, "Phase 2: Core Engine",
                "core/dimensional_analyzer.py", [
        "Data Normalization & Schema Validation",
        "Control 3.2 Privacy Validator",
        "Global LP Optimization (SciPy linprog + HiGHS)",
    ], accent=ORANGE_DEEP)
    _phase_card(s, x2, top, col_w, h, "Phase 3", "Output Artifacts", [
        "Excel Reporting (Summary, Ranks, Diagnostics)",
        "Balanced CSV (BI Ready)",
        "Comprehensive Audit Packages",
    ])
    _connector_arrow(s, x0 + col_w + Pt(6), top + h / 2 - Pt(18),
                     arrow_w - Pt(12), Pt(36))
    _connector_arrow(s, x1 + col_w + Pt(6), top + h / 2 - Pt(18),
                     arrow_w - Pt(12), Pt(36))
    footer(s, page, TOTAL)
    return s


def slide_solver(prs, page):
    s = new_slide(prs)
    bg(s)
    header(
        s,
        "A three-tier solver cascade guarantees an answer \u2014 even when "
        "strict optimization fails.",
        "Algorithmic resilience: the solver fallback",
    )
    levels = [
        ("Level 1: Global LP Optimization", [
            "Attempts to solve all dimensions simultaneously.",
            "Objective: minimize deviation from 1.0 + rank penalty + slack.",
            "Outcome: zero privacy violations, lowest system-wide distortion.",
        ], "If structurally infeasible"),
        ("Level 2: Subset Search & Per-Dimension LP", [
            "Greedily finds the largest feasible subset of dimensions.",
            "Drops conflicting dimensions to independent solvers.",
        ], "If strict LP fails"),
        ("Level 3: Bayesian / Heuristic Fallback", [
            "Utilizes L-BFGS-B scipy.minimize.",
            "Engages on edge-case categories.",
            "Guarantees an output under extreme data sparsity.",
        ], None),
    ]
    box_w = Pt(700)
    x = MARGIN + (CONTENT_W - box_w) / 2
    y = Pt(178)
    heights = [Pt(92), Pt(74), Pt(92)]
    accents = [ORANGE, NAVY, GRAY]
    for (title, items, cond), bh, accent in zip(levels, heights, accents):
        add_rect(s, x, y, box_w, bh, fill=PANEL, line=accent,
                 line_w=Pt(1.5), rounded=True)
        add_text(s, x + Pt(20), y + Pt(10), box_w - Pt(40), Pt(24),
                 [{"runs": plain(title, color=INK), "size": Pt(14.5),
                   "bold": True, "font": HEAD_FONT,
                   "align": PP_ALIGN.CENTER}])
        add_text(s, x + Pt(40), y + Pt(36), box_w - Pt(72), bh - Pt(42),
                 bullets_spec([plain(i) for i in items], size=Pt(12),
                              space_after=Pt(2), line_spacing=1.08))
        if cond:
            arrow = s.shapes.add_shape(MSO_SHAPE.DOWN_ARROW,
                                       x + box_w / 2 - Pt(13),
                                       y + bh + Pt(3), Pt(26), Pt(22))
            _set_fill(arrow, NAVY)
            _no_line(arrow)
            _no_shadow(arrow)
            add_text(s, x + box_w / 2 + Pt(22), y + bh + Pt(4), Pt(280),
                     Pt(22),
                     [{"runs": plain(cond, color=ORANGE_DEEP), "size": Pt(11),
                       "bold": True, "font": HEAD_FONT}],
                     anchor=MSO_ANCHOR.MIDDLE)
        y += bh + Pt(30)
    footer(s, page, TOTAL)
    return s


def styled_table(slide, x, y, w, headers, rows, col_widths, row_h=Pt(46),
                 head_h=Pt(40), badge_col=None):
    n_rows = len(rows) + 1
    total_w = sum(col_widths)
    table_h = head_h + row_h * len(rows)
    gfx = slide.shapes.add_table(n_rows, len(headers), x, y, total_w, table_h)
    tbl = gfx.table
    tbl.first_row = False
    tbl.horz_banding = False
    # disable default style banding via style id swap is complex; set fills.
    for ci, cw in enumerate(col_widths):
        tbl.columns[ci].width = cw
    tbl.rows[0].height = head_h
    for ri in range(1, n_rows):
        tbl.rows[ri].height = row_h
    # header
    for ci, htext in enumerate(headers):
        cell = tbl.cell(0, ci)
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = Pt(12)
        cell.margin_right = Pt(8)
        p = cell.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = htext
        r.font.size = Pt(13)
        r.font.bold = True
        r.font.name = HEAD_FONT
        r.font.color.rgb = WHITE
    # body
    for ri, row in enumerate(rows, start=1):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if ri % 2 else PANEL
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Pt(12)
            cell.margin_right = Pt(8)
            cell.margin_top = Pt(4)
            cell.margin_bottom = Pt(4)
            p = cell.text_frame.paragraphs[0]
            r = p.add_run()
            r.text = val
            r.font.size = Pt(12.5)
            r.font.name = BODY_FONT
            r.font.color.rgb = INK
            if ci == 0:
                r.font.bold = True
    return gfx


def slide_caps_table(prs, page):
    s = new_slide(prs)
    bg(s)
    title_header(
        s, "Auto-Applied Control 3.2 Caps",
        "The engine autonomously selects the appropriate regulatory rule "
        "based on available peer data \u2014 no manual configuration required.",
    )
    headers = ["Rule Name", "Min Peers", "Max Concentration Cap",
               "Trigger Condition"]
    rows = [
        ["5/25", "5", "25%", "Baseline standard"],
        ["6/30", "6", "30%", "\u2265 3 participants at \u2265 7%"],
        ["7/35", "7", "35%", "\u2265 2 at \u2265 15%, plus \u2265 1 at \u2265 8%"],
        ["10/40", "10", "40%", "\u2265 2 at \u2265 20%, plus \u2265 1 at \u2265 10%"],
        ["4/35", "4", "35%", "Merchant benchmarking mode only"],
    ]
    widths = [Pt(150), Pt(150), Pt(255), Pt(329)]
    styled_table(s, MARGIN, Pt(178), CONTENT_W, headers, rows, widths,
                 row_h=Pt(48), head_h=Pt(42))
    footer(s, page, TOTAL)
    return s


def slide_presets(prs, page):
    s = new_slide(prs)
    bg(s)
    title_header(
        s, "Tailoring the Engine: Strategic Presets",
        "Out-of-the-box configurations mapped to specific business intents.",
    )
    presets = [
        ("Balanced Default", "balanced_default.yaml",
         "Day-to-day general business analysis.",
         "Optimal mix of speed, compliance, and accuracy."),
        ("Compliance Strict", "compliance_strict.yaml",
         "Regulatory and audit-first submissions.",
         "Zero tolerance for threshold deviations; robust audit logs."),
        ("Strategic Consistency", "strategic_consistency.yaml",
         "Executive dashboards and KPI tracking.",
         "Emphasizes consistent global weighting behavior over time."),
        ("Research Exploratory", "research_exploratory.yaml",
         "Hard, sparse, or highly skewed datasets.",
         "Higher flexibility to uncover underlying market trends."),
    ]
    top = Pt(168)
    h = Pt(300)
    gap = Pt(20)
    n = len(presets)
    cw = Emu(int((CONTENT_W - gap * (n - 1)) / n))
    x = MARGIN
    for name, yaml, use, posture in presets:
        add_rect(s, x, top, cw, h, fill=PANEL, line=PANEL_BORDER,
                 line_w=Pt(1), rounded=True)
        # accent top bar
        add_rect(s, x, top, cw, Pt(6), fill=ORANGE, rounded=False)
        add_text(s, x + Pt(16), top + Pt(24), cw - Pt(32), Pt(54),
                 [{"runs": plain(name, color=INK), "size": Pt(16),
                   "bold": True, "font": HEAD_FONT, "line_spacing": 1.0},
                  {"runs": plain(yaml, color=NAVY), "size": Pt(10.5),
                   "font": "Consolas"}])
        add_text(s, x + Pt(16), top + Pt(110), cw - Pt(32), Pt(200),
                 [{"runs": [("Use Case: ", {"bold": True, "color": INK}),
                            (use, {"color": GRAY})],
                   "size": Pt(12), "font": BODY_FONT, "line_spacing": 1.12,
                   "space_after": Pt(14)},
                  {"runs": [("Posture: ", {"bold": True, "color": INK}),
                            (posture, {"color": GRAY})],
                   "size": Pt(12), "font": BODY_FONT, "line_spacing": 1.12}])
        x += cw + gap
    footer(s, page, TOTAL)
    return s


def slide_tui(prs, page):
    s = new_slide(prs)
    bg(s)
    title_header(
        s, "The Analyst Experience: Visual Validation",
        "v3.0 introduces a robust TUI, eliminating pure-CLI friction.",
    )
    # mock TUI window centre
    win_x, win_y, win_w, win_h = Pt(300), Pt(178), Pt(440), Pt(290)
    add_rect(s, win_x, win_y, win_w, win_h, fill=WHITE, line=NAVY,
             line_w=Pt(1.25), rounded=True)
    add_rect(s, win_x, win_y, win_w, Pt(34), fill=NAVY, rounded=True)
    add_text(s, win_x, win_y, win_w, Pt(34),
             [{"runs": plain("ANALYST VALIDATION DASHBOARD \u2013 v3.0",
                             color=WHITE), "size": Pt(11), "bold": True,
               "font": "Consolas", "align": PP_ALIGN.CENTER}],
             anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, win_x + Pt(16), win_y + Pt(46), win_w - Pt(32), Pt(28),
             fill=PANEL, line=HAIRLINE, line_w=Pt(0.75))
    add_text(s, win_x + Pt(24), win_y + Pt(46), win_w - Pt(48), Pt(28),
             [{"runs": plain(
                 "SCHEMA CHECK: PASS      NULL DETECTION: PASS      "
                 "PEER CONSTRAINTS: VALIDATING...", color=INK),
               "size": Pt(8.5), "font": "Consolas"}],
             anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, win_x + Pt(16), win_y + Pt(84), Pt(150), Pt(150),
             fill=PANEL, line=HAIRLINE, line_w=Pt(0.75))
    add_text(s, win_x + Pt(24), win_y + Pt(92), Pt(140), Pt(140),
             [{"runs": plain("CONFIGURATION", color=GRAY), "size": Pt(8),
               "bold": True, "font": "Consolas", "space_after": Pt(6)},
              {"runs": plain("Entity ID: [SELECT]", color=INK), "size": Pt(8.5),
               "font": "Consolas", "space_after": Pt(4)},
              {"runs": plain("Metric:    [SELECT]", color=INK), "size": Pt(8.5),
               "font": "Consolas", "space_after": Pt(4)},
              {"runs": plain("Dimension: [SELECT]", color=INK), "size": Pt(8.5),
               "font": "Consolas"}])
    add_rect(s, win_x + Pt(178), win_y + Pt(84), win_w - Pt(194), Pt(150),
             fill=PANEL, line=HAIRLINE, line_w=Pt(0.75))
    add_text(s, win_x + Pt(186), win_y + Pt(92), win_w - Pt(210), Pt(140),
             [{"runs": plain("DATA PREVIEW", color=GRAY), "size": Pt(8),
               "bold": True, "font": "Consolas", "space_after": Pt(6)},
              {"runs": plain("E123  2024-05-20  150.5  VALID", color=INK),
               "size": Pt(8.5), "font": "Consolas", "space_after": Pt(3)},
              {"runs": plain("E124  2024-05-20  150.5  VALID", color=INK),
               "size": Pt(8.5), "font": "Consolas", "space_after": Pt(3)},
              {"runs": plain("E125  2024-05-20  150.5  VALID", color=INK),
               "size": Pt(8.5), "font": "Consolas"}])
    add_rect(s, win_x + Pt(16), win_y + Pt(244), win_w - Pt(32), Pt(44),
             fill=RGBColor(0x1B, 0x1B, 0x1B), line=None)
    add_text(s, win_x + Pt(24), win_y + Pt(244), win_w - Pt(48), Pt(44),
             [{"runs": plain("[10:00:02] WARN: schema mismatch, auto-fixing...",
                             color=RGBColor(0xF7, 0x9E, 0x1B)), "size": Pt(8),
               "font": "Consolas", "space_after": Pt(2)},
              {"runs": plain("[10:00:03] ERROR: peer constraint E456 < min_peers",
                             color=RGBColor(0xFF, 0x6B, 0x6B)), "size": Pt(8),
               "font": "Consolas"}],
             anchor=MSO_ANCHOR.MIDDLE)

    # left callouts
    add_text(s, MARGIN, Pt(190), Pt(245), Pt(110),
             [{"runs": plain("1. Validation-First Workflow", color=ORANGE_DEEP),
               "size": Pt(13), "bold": True, "font": HEAD_FONT,
               "space_after": Pt(4)},
              {"runs": plain(
                  "Catches nulls, schema errors, and peer constraints before "
                  "running heavy optimizations.", color=GRAY),
               "size": Pt(11.5), "font": BODY_FONT, "line_spacing": 1.12}])
    add_text(s, MARGIN, Pt(360), Pt(245), Pt(110),
             [{"runs": plain("2. Intuitive Configuration", color=ORANGE_DEEP),
               "size": Pt(13), "bold": True, "font": HEAD_FONT,
               "space_after": Pt(4)},
              {"runs": plain(
                  "Dropdown selections for Entity IDs, Metrics, and "
                  "Dimensions.", color=GRAY),
               "size": Pt(11.5), "font": BODY_FONT, "line_spacing": 1.12}])
    # right callouts
    rx = win_x + win_w + Pt(20)
    rw = SLIDE_W - rx - MARGIN
    add_text(s, rx, Pt(190), rw, Pt(110),
             [{"runs": plain("3. Real-time Diagnostics", color=ORANGE_DEEP),
               "size": Pt(13), "bold": True, "font": HEAD_FONT,
               "space_after": Pt(4)},
              {"runs": plain(
                  "Integrated log handling prevents UI freezes during "
                  "background thread processing.", color=GRAY),
               "size": Pt(11.5), "font": BODY_FONT, "line_spacing": 1.12}])
    add_text(s, rx, Pt(360), rw, Pt(110),
             [{"runs": plain("4. Instant Overrides", color=ORANGE_DEEP),
               "size": Pt(13), "bold": True, "font": HEAD_FONT,
               "space_after": Pt(4)},
              {"runs": plain(
                  "Toggle advanced panels (Ctrl+A) to inject custom rules "
                  "instantly.", color=GRAY),
               "size": Pt(11.5), "font": BODY_FONT, "line_spacing": 1.12}])
    footer(s, page, TOTAL)
    return s


def slide_resource(prs, page):
    s = new_slide(prs)
    bg(s)
    title_header(
        s, "Resource Management: Adaptive Batching & Lean Mode",
        "Engineered for memory-limited environments and massive datasets.",
    )
    steps = [
        ("1. Estimate & Project",
         "Reads header, drops unused columns, estimates memory load."),
        ("2. Adaptive Chunking",
         "Streams heavy CSVs in 100k-row chunks."),
        ("3. Pre-Aggregation",
         "Consolidates duplicate entity/dimension/time rows on the fly."),
        ("4. Lean Execution",
         "Disables heavy secondary artifacts to focus 100% compute on global "
         "optimization."),
    ]
    top = Pt(180)
    h = Pt(230)
    gap = Pt(20)
    n = len(steps)
    cw = Emu(int((CONTENT_W - gap * (n - 1)) / n))
    x = MARGIN
    for i, (name, desc) in enumerate(steps):
        add_rect(s, x, top, cw, h, fill=PANEL, line=PANEL_BORDER,
                 line_w=Pt(1), rounded=True)
        # number disc
        add_oval(s, x + Pt(18), top + Pt(20), Pt(40), Pt(40), NAVY)
        add_text(s, x + Pt(18), top + Pt(20), Pt(40), Pt(40),
                 [{"runs": plain(str(i + 1), color=WHITE), "size": Pt(16),
                   "bold": True, "font": HEAD_FONT, "align": PP_ALIGN.CENTER}],
                 anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, x + Pt(18), top + Pt(76), cw - Pt(36), Pt(40),
                 [{"runs": plain(name.split(". ", 1)[1], color=INK),
                   "size": Pt(14), "bold": True, "font": HEAD_FONT,
                   "line_spacing": 1.0}])
        add_text(s, x + Pt(18), top + Pt(126), cw - Pt(36), Pt(110),
                 [{"runs": plain(desc, color=GRAY), "size": Pt(12),
                   "font": BODY_FONT, "line_spacing": 1.15}])
        if i < n - 1:
            a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,
                                   x + cw + Pt(3), top + h / 2 - Pt(10),
                                   gap - Pt(6), Pt(20))
            _set_fill(a, ORANGE)
            _no_line(a)
            _no_shadow(a)
        x += cw + gap
    add_rect(s, MARGIN, SLIDE_H - Pt(118), CONTENT_W, Pt(58),
             fill=ORANGE, rounded=True)
    add_text(s, MARGIN, SLIDE_H - Pt(118), CONTENT_W, Pt(58),
             [{"runs": [("Takeaway: ", {"bold": True, "color": WHITE}),
                        ("Uncompromised privacy cap enforcement with a "
                         "fraction of the memory footprint.", {"color": WHITE})],
               "size": Pt(14), "font": BODY_FONT, "align": PP_ALIGN.CENTER}],
             anchor=MSO_ANCHOR.MIDDLE)
    footer(s, page, TOTAL)
    return s


def slide_distortion(prs, page):
    s = new_slide(prs)
    bg(s)
    title_header(
        s, "Unprecedented Visibility into Distortion Impact",
        "What is the true cost of meeting privacy caps?",
    )
    # left: schematic of raw vs balanced share
    cx, cy, cw, ch = MARGIN, Pt(180), Pt(500), Pt(300)
    add_rect(s, cx, cy, cw, ch, fill=PANEL, line=PANEL_BORDER, line_w=Pt(1),
             rounded=True)
    # axes
    ax = cx + Pt(40)
    ay = cy + ch - Pt(50)
    add_rect(s, ax, cy + Pt(30), Pt(1.5), ch - Pt(80), fill=HAIRLINE)
    add_rect(s, ax, ay, cw - Pt(80), Pt(1.5), fill=HAIRLINE)
    # two freeform-ish poly-lines approximated with connected segments
    raw_pts = [(0.05, 0.55), (0.22, 0.30), (0.40, 0.42), (0.58, 0.25),
               (0.78, 0.45), (0.95, 0.60)]
    bal_pts = [(0.05, 0.70), (0.22, 0.52), (0.40, 0.58), (0.58, 0.50),
               (0.78, 0.62), (0.95, 0.74)]
    plot_w = cw - Pt(90)
    plot_h = ch - Pt(110)
    px0 = ax + Pt(6)
    py0 = cy + Pt(40)

    def to_xy(pt):
        return (px0 + Emu(int(plot_w * pt[0])),
                py0 + Emu(int(plot_h * pt[1])))

    def polyline(pts, color, dash=False, width=Pt(2.25)):
        for a, b in zip(pts, pts[1:]):
            x1, y1 = to_xy(a)
            x2, y2 = to_xy(b)
            conn = s.shapes.add_connector(2, x1, y1, x2, y2)
            conn.line.color.rgb = color
            conn.line.width = width
            if dash:
                ln = conn.line._get_or_add_ln()
                d = ln.makeelement(qn("a:prstDash"), {"val": "dash"})
                ln.append(d)
    polyline(raw_pts, GRAY, dash=True)
    polyline(bal_pts, NAVY)
    add_text(s, cx + Pt(120), cy + Pt(20), Pt(160), Pt(24),
             [{"runs": plain("Raw Share", color=GRAY), "size": Pt(11),
               "bold": True, "font": BODY_FONT}])
    add_text(s, cx + Pt(160), cy + ch - Pt(96), Pt(180), Pt(24),
             [{"runs": plain("Balanced Share", color=NAVY), "size": Pt(11),
               "bold": True, "font": BODY_FONT}])
    add_text(s, cx + Pt(40), cy + Pt(150), Pt(160), Pt(22),
             [{"runs": plain("\u0394 Distortion", color=INK), "size": Pt(10),
               "italic": True, "font": BODY_FONT}])

    # right: three feature blocks + insight
    rx = cx + cw + Pt(30)
    rw = SLIDE_W - rx - MARGIN
    blocks = [
        ("Distortion Analysis",
         "v3.0 automatically calculates the percentage-point delta between raw "
         "market truth and compliant reporting."),
        ("Rank Change Tracking",
         "A dedicated output sheet tracks exact rank shifts before and after "
         "weighting."),
        ("Preset Comparison",
         "Run --compare-presets to generate a matrix showing which "
         "configuration yields the lowest mean distortion for a dataset."),
    ]
    by = Pt(180)
    bh = Pt(72)
    for title, desc in blocks:
        add_rect(s, rx, by, rw, bh, fill=WHITE, line=PANEL_BORDER,
                 line_w=Pt(1), rounded=True)
        add_rect(s, rx, by, Pt(5), bh, fill=ORANGE)
        add_text(s, rx + Pt(18), by + Pt(8), rw - Pt(34), bh - Pt(14),
                 [{"runs": plain(title, color=INK), "size": Pt(13.5),
                   "bold": True, "font": HEAD_FONT, "space_after": Pt(2)},
                  {"runs": plain(desc, color=GRAY), "size": Pt(10.5),
                   "font": BODY_FONT, "line_spacing": 1.08}])
        by += bh + Pt(10)
    add_rect(s, rx, by, rw, Pt(58), fill=PANEL, line=NAVY, line_w=Pt(1.25),
             rounded=True)
    add_text(s, rx + Pt(16), by, rw - Pt(32), Pt(58),
             [{"runs": [("Insight: ", {"bold": True, "color": NAVY}),
                        ("We don't just enforce rules; we quantify the "
                         "mathematical impact of those rules on our "
                         "intelligence.", {"color": INK})],
               "size": Pt(11.5), "font": BODY_FONT, "line_spacing": 1.12}],
             anchor=MSO_ANCHOR.MIDDLE)
    footer(s, page, TOTAL)
    return s


def slide_policy_table(prs, page):
    s = new_slide(prs)
    bg(s)
    title_header(
        s, "Embedded Policy Enforcement",
        "The system actively guards against unauthorized data combinations.",
    )
    headers = ["Data Scenario", "Policy Condition", "Status Badge"]
    rows = [
        ("Fraud/Chargebacks", "Must set privacy_basis: clearing_spend",
         "ENFORCED", NAVY),
        ("Digital Wallets", "Requires explicit Privacy team review",
         "MANUAL APPROVAL REQUIRED", ORANGE_DEEP),
        ("Dual-Entity-Axis", "Requires explicit Privacy team review",
         "MANUAL APPROVAL REQUIRED", ORANGE_DEEP),
        ("Top-Merchant Lists", "Strictly prohibited", "HARD BLOCKED",
         RGBColor(0x33, 0x33, 0x33)),
    ]
    widths = [Pt(260), Pt(420), Pt(220)]
    x = MARGIN
    y = Pt(180)
    head_h = Pt(40)
    row_h = Pt(58)
    # header row
    cx = x
    for htext, w in zip(headers, widths):
        add_rect(s, cx, y, w, head_h, fill=NAVY)
        add_text(s, cx + Pt(14), y, w - Pt(20), head_h,
                 [{"runs": plain(htext, color=WHITE), "size": Pt(13),
                   "bold": True, "font": HEAD_FONT}],
                 anchor=MSO_ANCHOR.MIDDLE)
        cx += w
    ry = y + head_h
    for i, (scenario, cond, badge, badge_color) in enumerate(rows):
        fill = WHITE if i % 2 == 0 else PANEL
        cx = x
        for ci, w in enumerate(widths):
            add_rect(s, cx, ry, w, row_h, fill=fill, line=HAIRLINE,
                     line_w=Pt(0.5))
            cx += w
        add_text(s, x + Pt(14), ry, widths[0] - Pt(20), row_h,
                 [{"runs": plain(scenario, color=INK), "size": Pt(13),
                   "bold": True, "font": BODY_FONT}],
                 anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, x + widths[0] + Pt(14), ry, widths[1] - Pt(20), row_h,
                 [{"runs": plain(cond, color=INK), "size": Pt(12.5),
                   "font": "Consolas"}],
                 anchor=MSO_ANCHOR.MIDDLE)
        # badge pill
        badge_w = Pt(min(200, 70 + len(badge) * 5.4))
        bx = x + widths[0] + widths[1] + (widths[2] - badge_w) / 2
        solid = badge in ("HARD BLOCKED",)
        add_rect(s, bx, ry + (row_h - Pt(26)) / 2, badge_w, Pt(26),
                 fill=badge_color if solid else WHITE,
                 line=badge_color, line_w=Pt(1.25), rounded=True)
        add_text(s, bx, ry + (row_h - Pt(26)) / 2, badge_w, Pt(26),
                 [{"runs": plain(f"[{badge}]",
                                 color=WHITE if solid else badge_color),
                   "size": Pt(9.5), "bold": True, "font": "Consolas",
                   "align": PP_ALIGN.CENTER}],
                 anchor=MSO_ANCHOR.MIDDLE)
        ry += row_h
    footer(s, page, TOTAL)
    return s


def slide_outputs(prs, page):
    s = new_slide(prs)
    bg(s)
    title_header(
        s, "Actionable Intelligence & Audit Readiness",
        "Three deliverables move compliant data straight into decisions and "
        "audits.",
    )
    cards = [
        ("1. The Excel Report", "(.xlsx)", [
            "Executive Summary & Metadata.",
            "Category-level comparisons (Target vs. Best-in-Class).",
            "Rank Changes & Weight Methods.",
        ]),
        ("2. The Balanced Export", "(.csv)", [
            "BI-Ready (Tableau, Power BI).",
            "Enriched with calculated metrics (Distortion_PP, Raw_Share).",
            "Schema-validated for parity with Excel.",
        ]),
        ("3. The Audit Package", "(.zip)", [
            "Immutable snapshot of inputs, config, and validation logs.",
            "Ready for immediate regulatory submission.",
        ]),
    ]
    top = Pt(178)
    h = Pt(296)
    gap = Pt(24)
    n = len(cards)
    cw = Emu(int((CONTENT_W - gap * (n - 1)) / n))
    x = MARGIN
    for title, ext, items in cards:
        add_rect(s, x, top, cw, h, fill=PANEL, line=PANEL_BORDER,
                 line_w=Pt(1), rounded=True)
        add_rect(s, x, top, cw, Pt(6), fill=ORANGE)
        add_text(s, x + Pt(20), top + Pt(28), cw - Pt(40), Pt(64),
                 [{"runs": plain(title, color=INK), "size": Pt(17),
                   "bold": True, "font": HEAD_FONT, "line_spacing": 1.0},
                  {"runs": plain(ext, color=NAVY), "size": Pt(13),
                   "font": "Consolas"}])
        add_rect(s, x + Pt(20), top + Pt(96), cw - Pt(40), Pt(1.2),
                 fill=HAIRLINE)
        add_text(s, x + Pt(20), top + Pt(112), cw - Pt(40), Pt(210),
                 bullets_spec([plain(i) for i in items], size=Pt(12.5),
                              space_after=Pt(10)))
        x += cw + gap
    footer(s, page, TOTAL)
    return s


def slide_zerotrust(prs, page):
    s = new_slide(prs)
    bg(s)
    title_header(
        s, "Zero Trust, Verified Execution",
        "Our release pipeline ensures absolute mathematical integrity.",
    )
    # process flow row
    nodes = ["Code Commit", "GitHub Actions", "Gate Tests",
             "Validated Release"]
    nw = Pt(188)
    nh = Pt(54)
    gap = Pt(38)
    total = nw * len(nodes) + gap * (len(nodes) - 1)
    x = MARGIN + (CONTENT_W - total) / 2
    y = Pt(180)
    centers = []
    for i, label in enumerate(nodes):
        add_rect(s, x, y, nw, nh, fill=PANEL, line=NAVY, line_w=Pt(1.25),
                 rounded=True)
        add_text(s, x, y, nw, nh,
                 [{"runs": plain(label, color=INK), "size": Pt(13.5),
                   "bold": True, "font": HEAD_FONT,
                   "align": PP_ALIGN.CENTER}],
                 anchor=MSO_ANCHOR.MIDDLE)
        centers.append((x, x + nw))
        if i < len(nodes) - 1:
            a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + nw + Pt(10),
                                   y + nh / 2 - Pt(9), gap - Pt(20), Pt(18))
            _set_fill(a, ORANGE)
            _no_line(a)
            _no_shadow(a)
        x += nw + gap
    # loop arrow back
    loop = s.shapes.add_shape(MSO_SHAPE.LEFT_ARROW, MARGIN + Pt(40),
                              y + nh + Pt(24), CONTENT_W - Pt(80), Pt(16))
    _set_fill(loop, HAIRLINE)
    _no_line(loop)
    _no_shadow(loop)
    add_text(s, MARGIN, y + nh + Pt(46), CONTENT_W, Pt(20),
             [{"runs": plain("continuous validation loop", color=LIGHT_GRAY),
               "size": Pt(10), "italic": True, "font": BODY_FONT,
               "align": PP_ALIGN.CENTER}])

    # three-column detail table
    headers = ["Gate Test Suite", "Mathematical Parity Validation",
               "Immutable Offline Deployments"]
    cells = [
        "17+ representative scenarios running on every commit.",
        "Automated cross-checking ensures CSV exports match Control 3.2 "
        "compliant Excel outputs to an exact 0.01% tolerance threshold.",
        "Secure, checksum-verified offline bundling (offline_packages/) for "
        "air-gapped or restricted server environments.",
    ]
    ty = Pt(312)
    th_h = Pt(38)
    tb_h = Pt(120)
    cw = Emu(int(CONTENT_W / 3))
    x = MARGIN
    for h_text, body in zip(headers, cells):
        add_rect(s, x, ty, cw, th_h, fill=NAVY, line=WHITE, line_w=Pt(0.5))
        add_text(s, x + Pt(14), ty, cw - Pt(24), th_h,
                 [{"runs": plain(h_text, color=WHITE), "size": Pt(12.5),
                   "bold": True, "font": HEAD_FONT}],
                 anchor=MSO_ANCHOR.MIDDLE)
        add_rect(s, x, ty + th_h, cw, tb_h, fill=PANEL, line=HAIRLINE,
                 line_w=Pt(0.5))
        add_text(s, x + Pt(14), ty + th_h + Pt(12), cw - Pt(28), tb_h - Pt(24),
                 [{"runs": plain(body, color=INK), "size": Pt(12),
                   "font": BODY_FONT, "line_spacing": 1.18}])
        x += cw
    footer(s, page, TOTAL)
    return s


def slide_value(prs, page):
    s = new_slide(prs)
    bg(s)
    add_text(s, MARGIN, Pt(40), CONTENT_W, Pt(60),
             [{"runs": plain("Autobench v3.0: Value Realization", color=INK),
               "size": Pt(30), "bold": True, "font": HEAD_FONT}])
    cols = [
        ("Absolute Compliance", [
            "100% adherence to Control 3.2 privacy caps.",
            "Cryptographically verifiable audit trails.",
        ]),
        ("Mathematical Superiority", [
            "Industry-leading LP solvers ensure the lowest possible data "
            "distortion.",
            "Unlocks insights in sparse datasets that legacy tools abandon.",
        ]),
        ("Operational Agility", [
            "TUI and Lean Mode democratize access and scale to massive "
            "datasets.",
            "Requires no infrastructure bloat.",
        ]),
    ]
    top = Pt(140)
    n = len(cols)
    gap = Pt(40)
    cw = Emu(int((CONTENT_W - gap * (n - 1)) / n))
    x = MARGIN
    for i, (title, items) in enumerate(cols):
        if i > 0:
            add_rect(s, x - gap / 2, top + Pt(4), Pt(1.2), Pt(225),
                     fill=HAIRLINE)
        add_text(s, x, top, cw, Pt(80),
                 [{"runs": plain(title, color=NAVY), "size": Pt(19),
                   "bold": True, "font": HEAD_FONT, "line_spacing": 1.0}])
        add_text(s, x, top + Pt(78), cw, Pt(210),
                 bullets_spec([plain(it) for it in items], size=Pt(13),
                              space_after=Pt(10), line_spacing=1.16))
        x += cw + gap
    add_rect(s, MARGIN, SLIDE_H - Pt(118), CONTENT_W, Pt(62),
             fill=ORANGE, rounded=True)
    add_text(s, MARGIN, SLIDE_H - Pt(118), CONTENT_W, Pt(62),
             [{"runs": plain(
                 "Compliant Data is no longer a compromise. "
                 "It is an exact science.", color=WHITE), "size": Pt(19),
               "bold": True, "font": HEAD_FONT, "align": PP_ALIGN.CENTER}],
             anchor=MSO_ANCHOR.MIDDLE)
    footer(s, page, TOTAL)
    return s


def slide_closing(prs):
    s = new_slide(prs)
    bg(s, DARK_BG)
    # large centred logo
    dia = Pt(150)
    overlap = dia * 0.42
    total_w = dia * 2 - overlap
    cx = (SLIDE_W - total_w) / 2
    cy = (SLIDE_H - dia) / 2 - Pt(20)
    add_oval(s, cx, cy, dia, dia, MC_RED)
    add_oval(s, cx + dia - overlap, cy, dia, dia, MC_YELLOW)
    lens = add_oval(s, cx + dia - overlap, cy, overlap, dia, MC_OVERLAP)
    _set_alpha(lens, 35)
    add_text(s, MARGIN, cy + dia + Pt(26), CONTENT_W, Pt(60),
             [{"runs": plain("Autobench v3.0 \u2014 Precision. Compliance. "
                             "Control.", color=WHITE), "size": Pt(20),
               "bold": True, "font": HEAD_FONT, "align": PP_ALIGN.CENTER}])
    add_text(s, MARGIN, cy + dia + Pt(64), CONTENT_W, Pt(30),
             [{"runs": plain("Mastercard Advisors \u2013 Performance Analytics",
                             color=RGBColor(0xB0, 0xB0, 0xB0)), "size": Pt(12),
               "font": BODY_FONT, "align": PP_ALIGN.CENTER}])
    return s


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
TOTAL = 13  # numbered content slides (title + closing are unnumbered)


def build(output: Path):
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    slide_title(prs)
    slide_paradox(prs, 2)
    slide_architecture(prs, 3)
    slide_solver(prs, 4)
    slide_caps_table(prs, 5)
    slide_presets(prs, 6)
    slide_tui(prs, 7)
    slide_resource(prs, 8)
    slide_distortion(prs, 9)
    slide_policy_table(prs, 10)
    slide_outputs(prs, 11)
    slide_zerotrust(prs, 12)
    slide_value(prs, 13)
    slide_closing(prs)

    output.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output))
    print(f"Saved {output} ({len(prs.slides._sldIdLst)} slides)")


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "docs/Autobench_v3.0_Precision_Compliance.pptx")
    build(out)


if __name__ == "__main__":
    main()
