# Operational Gains Review - Findings (2026-01-29)

## Scope
Reviewed the operational gains narrative in `docs/OPERATIONAL_GAINS.md` against the current implementation in:
- `benchmark.py`
- `tui_app.py`
- `core/`
- `utils/`
- `presets/`
- `old/bench_old.py`

The focus here is on the qualitative gains (and the related claims in the summary sections) and their alignment with actual behavior and outputs.

## Summary of findings
| ID | Severity | Issue | Primary impact |
| --- | --- | --- | --- |
| F1 | High | Privacy rule enforcement is limited to max concentration caps by peer count; additional Control 3.2 constraints are not applied in the analyzer or validation outputs. | Claims about full Control 3.2 enforcement and pass/fail validation are too strong. |
| F2 | Medium | Transparency artifacts are conditional (debug/export flags, consistent weights, and target entity requirements). | Statements read as always-available outputs when they are not. |
| F3 | Medium | "Audit-ready" outputs and audit trails are overstated, especially for publication outputs. | Public-facing or default outputs may not include audit artifacts. |
| F4 | Medium | Quantitative time and staffing gains lack evidence in the repo. | These should be labeled as estimates or supported by sources. |

## Detailed findings

### F1 (High): Privacy rule enforcement is limited to max concentration by peer count
**What the doc claims**
- "Privacy caps enforced by design" and "most up-to-date privacy validation concepts" imply full Control 3.2 rule enforcement. `docs/OPERATIONAL_GAINS.md:3` `docs/OPERATIONAL_GAINS.md:70-76` `docs/OPERATIONAL_GAINS.md:86`

**What the code does**
- The analyzer derives a single max concentration cap based on peer count and uses that in LP constraints. Additional rule conditions (e.g., 6/30 requires >= 3 participants at >= 7%) are not applied in the analyzer. `core/dimensional_analyzer.py:1007-1016`
- The privacy validation dataframe checks only the cap and tolerance, not the additional constraints. `core/dimensional_analyzer.py:1773-1831`
- Additional constraints are defined in `PrivacyValidator`, but the analyzer does not call this class in the main weighting pipeline. `core/privacy_validator.py:61-83` `core/privacy_validator.py:224-292`
- A repo-wide search shows `PrivacyValidator` only in its module and exports, not in the share/rate analysis flow. `core/privacy_validator.py` `core/__init__.py`

**Why it matters**
Current outputs can be compliant with the max concentration cap while still violating the additional Control 3.2 constraints. The document should not imply full rule enforcement unless the analyzer uses `PrivacyValidator` (or equivalent logic) in the weighting and validation stages.

**Affected doc lines**
- `docs/OPERATIONAL_GAINS.md:3`
- `docs/OPERATIONAL_GAINS.md:22-23`
- `docs/OPERATIONAL_GAINS.md:70-76`
- `docs/OPERATIONAL_GAINS.md:80-86`

**Affected code paths**
- `core/dimensional_analyzer.py:1007-1016`
- `core/dimensional_analyzer.py:1773-1831`
- `core/privacy_validator.py:61-83`
- `core/privacy_validator.py:224-292`

---

### F2 (Medium): Transparency outputs are conditional (not always present)
**What the doc claims**
- "Analysts can understand and debug every decision behind peer weights" with items such as distortion analysis, solver used per dimension, rank changes, and privacy validation pass/fail. `docs/OPERATIONAL_GAINS.md:58-66`

**What the code does**
- Distortion analysis (raw vs balanced) only runs when `include_distortion_summary` is enabled and a target entity is provided (share analysis only). `benchmark.py:949-991`
- Rate analysis uses weight effect analysis (not distortion) when `include_distortion_summary` is enabled. `benchmark.py:1456`
- Privacy validation output is built only if `debug_mode` OR `export_balanced_csv` is enabled, and only when `consistent_weights` is true. `benchmark.py:874` `benchmark.py:1374` `core/dimensional_analyzer.py:1775`
- The Weight Methods sheet is built only in `consistent_weights` mode; it is not created for per-dimension weight mode. `benchmark.py:880-920` `benchmark.py:1380-1421`

**Why it matters**
The transparency list reads as unconditional. In practice, many items appear only when specific flags are used or when the analysis is in a specific mode. The doc should clarify that these artifacts are conditional and that rate analysis uses weight-effect summaries rather than distortion.

**Affected doc lines**
- `docs/OPERATIONAL_GAINS.md:58-64`

**Affected code paths**
- `benchmark.py:874`
- `benchmark.py:949-991`
- `benchmark.py:1456`
- `benchmark.py:1374`
- `benchmark.py:880-920`
- `core/dimensional_analyzer.py:1775`

---

### F3 (Medium): "Audit-ready" and audit trail claims are overstated for default outputs
**What the doc claims**
- "Audit-ready outputs" and "Debug and validation sheets provide audit trails." `docs/OPERATIONAL_GAINS.md:3` `docs/OPERATIONAL_GAINS.md:83`

**What the code does**
- Publication workbooks explicitly remove debug sheets, weight details, and technical metadata. `core/report_generator.py:487-503`
- Data Quality sheets are only added when validation runs (and when `validation_issues` is not None). `benchmark.py:2269-2276` `benchmark.py:2804-2810`
- A dedicated audit log writer exists but is not called from the share/rate flows. `core/report_generator.py:447` (no usage elsewhere)

**Why it matters**
The claim is accurate only for analysis workbooks with debug/validation enabled. Publication output is intentionally stripped of audit detail, so calling it "audit-ready" is misleading.

**Affected doc lines**
- `docs/OPERATIONAL_GAINS.md:3`
- `docs/OPERATIONAL_GAINS.md:83-86`

**Affected code paths**
- `core/report_generator.py:487-503`
- `benchmark.py:2269-2276`
- `benchmark.py:2804-2810`
- `core/report_generator.py:447`

---

### F4 (Medium): Quantitative time and staffing claims lack evidence in the repo
**What the doc claims**
- 75 percent reduction in balancing time per peer and multi-peer project timelines.
- Single L7/L8 analyst can execute end-to-end.
`docs/OPERATIONAL_GAINS.md:3` `docs/OPERATIONAL_GAINS.md:10-12` `docs/OPERATIONAL_GAINS.md:19-21` `docs/OPERATIONAL_GAINS.md:31-35`

**What the repo shows**
- No benchmark data, timing studies, or references backing these numbers.
- No documentation or dataset tying the claims to measured outcomes.

**Why it matters**
If this document is used externally, these statements should be labeled as internal estimates or supported by references. As written, they read as empirical results.

**Affected doc lines**
- `docs/OPERATIONAL_GAINS.md:3`
- `docs/OPERATIONAL_GAINS.md:10-12`
- `docs/OPERATIONAL_GAINS.md:19-21`
- `docs/OPERATIONAL_GAINS.md:31-35`

**Affected files**
- `docs/OPERATIONAL_GAINS.md`

---

## Affected files (by area)
- Documented claims: `docs/OPERATIONAL_GAINS.md`
- Privacy enforcement and validation logic: `core/dimensional_analyzer.py`, `core/privacy_validator.py`
- Output gating (distortion, validation, weight methods): `benchmark.py`
- Publication output behavior and audit log support: `core/report_generator.py`

## Notes on alignment (non-blocking)
- Distortion analysis is a share-only artifact; rate analysis uses weight effect summaries. `benchmark.py:949-991` `benchmark.py:1456`
- Privacy validation output is capped to max concentration and tolerance only; additional Control 3.2 constraints are not evaluated in the analyzer path. `core/dimensional_analyzer.py:1773-1831` `core/privacy_validator.py:224-292`

## Suggested doc-level tightening (not applied)
- Add conditional language to transparency and auditability bullets (debug mode, export flags, consistent weights, target entity required for distortion).
- Reframe Control 3.2 wording to "max concentration cap by peer count" unless full rule constraints are enforced in the analyzer.
- Mark time and staffing gains as internal estimates or cite supporting sources.
