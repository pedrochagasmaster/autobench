"""Embed TrueType fonts into a .pptx so it renders identically everywhere.

PowerPoint/OOXML font embedding works by:
  * adding the raw TTFs as ``/ppt/fonts/fontN.fntdata`` parts,
  * declaring a ``fntdata`` default content-type,
  * relating each part from ``presentation.xml`` (relationship type ``/font``),
  * listing them under ``<p:embeddedFontLst>`` in ``presentation.xml`` and
    flipping ``embedTrueTypeFonts="1"``.

This module also rewrites the theme's major/minor Latin fonts so the editing
experience (and any unstyled text) defaults to the deck's typefaces.

Everything is done by rewriting the package zip in place; the result still
opens cleanly in python-pptx, LibreOffice, and PowerPoint.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from lxml import etree

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
FONT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"

# Order of children in CT_Presentation (subset that python-pptx emits) used to
# splice embeddedFontLst into a schema-valid position.
PRES_ORDER = [
    "sldMasterIdLst", "notesMasterIdLst", "handoutMasterIdLst", "sldIdLst",
    "sldSz", "notesSz", "smartTags", "embeddedFontLst", "custShowLst",
    "photoAlbum", "custDataLst", "kinsoku", "defaultTextStyle",
    "modifyVerifier", "extLst",
]


def _q(ns, tag):
    return f"{{{ns}}}{tag}"


def embed_fonts(pptx_path, font_dir, embed_map, theme_major=None,
                theme_minor=None):
    """Embed fonts and (optionally) set theme major/minor Latin typefaces.

    Parameters
    ----------
    pptx_path : str | Path
    font_dir : str | Path
        Directory holding the TTF files referenced by ``embed_map``.
    embed_map : dict[str, dict[str, str]]
        ``{typeface_name: {"regular": file, "bold": file, ...}}``. Slot keys are
        ``regular``/``bold``/``italic``/``boldItalic``.
    """
    pptx_path = Path(pptx_path)
    font_dir = Path(font_dir)
    tmp = pptx_path.with_suffix(".tmp.pptx")

    zin = zipfile.ZipFile(pptx_path, "r")
    names = zin.namelist()
    ct_xml = zin.read("[Content_Types].xml")
    pres_xml = zin.read("ppt/presentation.xml")
    rels_xml = zin.read("ppt/_rels/presentation.xml.rels")
    theme_name = "ppt/theme/theme1.xml"
    theme_xml = zin.read(theme_name) if theme_name in names else None

    # ---- collect font parts ------------------------------------------------
    slot_order = ["regular", "bold", "italic", "boldItalic"]
    font_parts = []  # (part_name, bytes)
    embed_entries = []  # (typeface, {slot: part_name})
    idx = 1
    file_cache = {}
    for typeface, slots in embed_map.items():
        slot_parts = {}
        for slot in slot_order:
            if slot not in slots:
                continue
            fname = slots[slot]
            if fname not in file_cache:
                part = f"ppt/fonts/font{idx}.fntdata"
                idx += 1
                file_cache[fname] = part
                font_parts.append((part, (font_dir / fname).read_bytes()))
            slot_parts[slot] = file_cache[fname]
        embed_entries.append((typeface, slot_parts))

    # ---- [Content_Types].xml ----------------------------------------------
    ct = etree.fromstring(ct_xml)
    has_fnt = any(
        el.get("Extension") == "fntdata"
        for el in ct.findall(_q(CT_NS, "Default"))
    )
    if not has_fnt:
        d = etree.SubElement(ct, _q(CT_NS, "Default"))
        d.set("Extension", "fntdata")
        d.set("ContentType", "application/x-fontdata")
    ct_out = etree.tostring(ct, xml_declaration=True, encoding="UTF-8",
                            standalone=True)

    # ---- presentation.xml.rels --------------------------------------------
    rels = etree.fromstring(rels_xml)
    max_id = 0
    for rel in rels:
        rid = rel.get("Id", "")
        if rid.startswith("rId") and rid[3:].isdigit():
            max_id = max(max_id, int(rid[3:]))
    part_to_rid = {}
    for part, _ in font_parts:
        max_id += 1
        rid = f"rId{max_id}"
        part_to_rid[part] = rid
        rel = etree.SubElement(rels, _q(REL_NS, "Relationship"))
        rel.set("Id", rid)
        rel.set("Type", FONT_REL)
        rel.set("Target", "fonts/" + Path(part).name)
    rels_out = etree.tostring(rels, xml_declaration=True, encoding="UTF-8",
                              standalone=True)

    # ---- presentation.xml --------------------------------------------------
    pres = etree.fromstring(pres_xml)
    pres.set("embedTrueTypeFonts", "1")
    pres.set("saveSubsetFonts", "0")
    # build embeddedFontLst
    lst = etree.Element(_q(P_NS, "embeddedFontLst"))
    for typeface, slot_parts in embed_entries:
        ef = etree.SubElement(lst, _q(P_NS, "embeddedFont"))
        fnt = etree.SubElement(ef, _q(P_NS, "font"))
        fnt.set("typeface", typeface)
        for slot in slot_order:
            if slot in slot_parts:
                se = etree.SubElement(ef, _q(P_NS, slot))
                se.set(_q(R_NS, "id"), part_to_rid[slot_parts[slot]])
    # splice into schema-correct position
    existing = {etree.QName(c).localname: c for c in pres
                if isinstance(c.tag, str)}
    insert_at = len(pres)
    target_pos = PRES_ORDER.index("embeddedFontLst")
    for later in PRES_ORDER[target_pos + 1:]:
        if later in existing:
            insert_at = list(pres).index(existing[later])
            break
    pres.insert(insert_at, lst)
    pres_out = etree.tostring(pres, xml_declaration=True, encoding="UTF-8",
                              standalone=True)

    # ---- theme1.xml (major/minor latin) -----------------------------------
    theme_out = None
    if theme_xml is not None and (theme_major or theme_minor):
        theme = etree.fromstring(theme_xml)
        scheme = theme.find(f".//{_q(A_NS, 'fontScheme')}")
        if scheme is not None:
            for tag, name in (("majorFont", theme_major),
                              ("minorFont", theme_minor)):
                if not name:
                    continue
                fb = scheme.find(_q(A_NS, tag))
                if fb is not None:
                    latin = fb.find(_q(A_NS, "latin"))
                    if latin is not None:
                        latin.set("typeface", name)
        theme_out = etree.tostring(theme, xml_declaration=True,
                                   encoding="UTF-8", standalone=True)

    # ---- write new package -------------------------------------------------
    replacements = {
        "[Content_Types].xml": ct_out,
        "ppt/presentation.xml": pres_out,
        "ppt/_rels/presentation.xml.rels": rels_out,
    }
    if theme_out is not None:
        replacements[theme_name] = theme_out

    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = replacements.get(item.filename, zin.read(item.filename))
            zout.writestr(item, data)
        for part, data in font_parts:
            zout.writestr(part, data)
    zin.close()
    shutil.move(str(tmp), str(pptx_path))
    return len(font_parts)
