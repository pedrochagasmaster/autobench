"""Plain-language labels for internal codes (TUI redesign 02 §5.2).

Pure data: this module imports nothing from the engine, so the TUI and the
CLI can share the same words without loading the analysis stack. Every
internal code shown to an operator maps to primary text here; the code itself
stays visible as secondary ``Code: ...`` detail so it can be quoted to
support. Unknown codes never reach the screen bare: ``label_for`` falls back
to ``Unrecognised status``.

Wording rule: a "Next" step never suggests weakening privacy (for example
switching to a looser posture to see the numbers).
"""

from __future__ import annotations

from typing import Dict, Mapping, NamedTuple, Optional, Tuple


class Label(NamedTuple):
    """Primary text, an optional cause ("Why") and an optional next step."""

    primary: str
    why: str = ""
    next: str = ""


UNRECOGNISED = "Unrecognised status"

# Kinds of code. Keys of LABELS are (kind, code).
COMPLIANCE_VERDICT = "compliance_verdict"
RUN_STATUS = "run_status"
POSTURE = "posture"
CONSENT_STATE = "consent_state"
WITHHOLDING_REASON = "withholding_reason"
RELEASE_MODE = "release_mode"
RULE_STRATEGY = "rule_strategy"
SWEEP_STATUS = "sweep_status"
ANALYSIS_MODE = "analysis_mode"
OUTPUT_FORMAT = "output_format"
PRESET = "preset"
VALIDATION_SEVERITY = "validation_severity"

LABELS: Mapping[Tuple[str, str], Label] = {
    # ── Compliance verdict (summary["compliance_verdict"]) ──────────────
    (COMPLIANCE_VERDICT, "fully_compliant"): Label(
        "Privacy checks passed",
        "Every published cell meets the peer-count and concentration rules.",
    ),
    (COMPLIANCE_VERDICT, "violations_detected"): Label(
        "Some cells break the privacy rules",
        "Strict posture: nothing was published. Best effort: the report labels those cells non-compliant.",
        "Remove a dimension, or use fewer, larger categories.",
    ),
    (COMPLIANCE_VERDICT, "not_publishable_input"): Label(
        "The input data isn't fit to publish",
        "Data validation found errors under the Strict posture.",
        "Fix the rows listed by the data check and run again.",
    ),
    (COMPLIANCE_VERDICT, "structural_infeasibility"): Label(
        "Some categories can't meet the rules with any weighting",
        "Too few peers in some categories.",
        "Merge or drop those categories.",
    ),
    (COMPLIANCE_VERDICT, "blocked"): Label(
        "The run was stopped by a policy check",
    ),
    # ── Run status (summary["run_status"]) ──────────────────────────────
    (RUN_STATUS, "compliant"): Label("Completed, compliant"),
    (RUN_STATUS, "non_compliant"): Label("Completed with privacy violations (Strict posture)"),
    (RUN_STATUS, "completed_with_warnings"): Label("Completed, some outputs labelled non-compliant"),
    (RUN_STATUS, "completed_accuracy_first"): Label("Completed as a non-publishable diagnostic"),
    (RUN_STATUS, "completed"): Label("Completed"),
    (RUN_STATUS, "blocked"): Label("Blocked"),
    (RUN_STATUS, "withheld"): Label("Publication withheld"),
    # ── Privacy posture (preset compliance_posture) ─────────────────────
    (POSTURE, "strict"): Label(
        "Strict",
        "Nothing is published unless every cell passes.",
    ),
    (POSTURE, "best_effort"): Label(
        "Best effort",
        "Completes even with violations, and labels them in the report.",
    ),
    (POSTURE, "accuracy_first"): Label(
        "Accuracy first",
        "Favours accurate numbers over the privacy rules. The report is a "
        "non-publishable diagnostic, and every run needs your consent.",
    ),
    # ── Consent state (summary["acknowledgement_state"]) ────────────────
    (CONSENT_STATE, "acknowledged"): Label("You consented for this run"),
    (CONSENT_STATE, "not_required"): Label("No consent needed"),
    (CONSENT_STATE, "required_missing"): Label("Consent is required and was not given"),
    # ── Withholding reason (privacy_output_decision.withholding_reason) ─
    (WITHHOLDING_REASON, "control3_numeric_policy_blocked"): Label(
        "Results were withheld to protect peer privacy.",
        "Some cells had too few peers, or one peer was too large a share.",
        "Remove a dimension, choose Verified safe coverage (share analysis), "
        "or pick a preset with tighter weights, then run again.",
    ),
    (WITHHOLDING_REASON, "control3_mandatory_overlay_blocked"): Label(
        "Results were withheld because a mandatory overlay failed (the Citi 25% cap).",
        "Citibank's share is above the cap in some cells.",
        "Check the Citibank entity name in Compliance declarations, or reduce "
        "the dimensions where Citibank's share is high.",
    ),
    (WITHHOLDING_REASON, "control3_invalid_privacy_evidence"): Label(
        "Results were withheld because the privacy check couldn't confirm the outputs.",
        "This is a safeguard, not a data problem.",
        "Run again; if it repeats, send the internal run log path to support.",
    ),
    (WITHHOLDING_REASON, "control3_safe_coverage_verifier_failed"): Label(
        "Verified safe coverage was withheld: the independent check didn't confirm the safe set.",
        "",
        "Run again with Complete output, or contact support with the log path.",
    ),
    (WITHHOLDING_REASON, "control3_safe_coverage_search_incomplete"): Label(
        "Verified safe coverage was withheld: the search for a safe set didn't finish.",
        "",
        "Use fewer dimensions, or run with Complete output.",
    ),
    (WITHHOLDING_REASON, "control3_safe_coverage_empty_release"): Label(
        "Verified safe coverage found no units that are safe to publish.",
        "",
        "Use fewer or broader dimensions.",
    ),
    # ── Release mode, rule strategy, sweep status (core.contracts) ──────
    (RELEASE_MODE, "complete-output"): Label("Complete output"),
    (RELEASE_MODE, "verified-safe-coverage"): Label(
        "Verified safe coverage",
        "Publishes only units proven safe, and suppresses the rest.",
    ),
    (RULE_STRATEGY, "select_by_peer_count"): Label("Rule chosen by peer count (standard)"),
    (RULE_STRATEGY, "sweep_any_applicable"): Label("Privacy rule sweep: try every rule that applies"),
    (SWEEP_STATUS, "numerically_compliant"): Label("Meets the numeric privacy rules"),
    (SWEEP_STATUS, "numerically_noncompliant"): Label("Fails the numeric privacy rules"),
    (SWEEP_STATUS, "not_subject_to_benchmark_numeric_rules"): Label("Not subject to the numeric rules"),
    (SWEEP_STATUS, "invalid_or_incomplete_evidence"): Label("Privacy evidence incomplete"),
    (SWEEP_STATUS, "blocked_by_mandatory_overlay"): Label("Blocked by a mandatory overlay"),
    # ── Analysis modes and output formats ───────────────────────────────
    (ANALYSIS_MODE, "share"): Label("Share analysis"),
    (ANALYSIS_MODE, "rate"): Label("Rate analysis"),
    (ANALYSIS_MODE, "privacy-sweep"): Label("Privacy rule sweep"),
    (OUTPUT_FORMAT, "analysis"): Label("Analysis workbook"),
    (OUTPUT_FORMAT, "publication"): Label("Publication workbook (client-facing)"),
    (OUTPUT_FORMAT, "both"): Label("Both workbooks"),
    # ── Presets (presets/*.yaml) ─────────────────────────────────────────
    (PRESET, "compliance_strict"): Label("Compliance strict · Strict"),
    (PRESET, "balanced_default"): Label("Balanced (default) · Best effort"),
    (PRESET, "strategic_consistency"): Label("Strategic consistency · Best effort"),
    (PRESET, "research_exploratory"): Label("Research, exploratory · Best effort"),
    (PRESET, "low_distortion"): Label("Low distortion · Accuracy first, consent each run"),
    (PRESET, "minimal_distortion"): Label("Minimal distortion · Accuracy first, consent each run"),
    # ── Data validation severities (core.data_loader.ValidationSeverity) ─
    (VALIDATION_SEVERITY, "ERROR"): Label("ERROR"),
    (VALIDATION_SEVERITY, "WARNING"): Label("WARNING"),
    (VALIDATION_SEVERITY, "INFO"): Label("INFO"),
}

# Status-language state (tui.status) used for each compliance verdict when
# the run itself finished and its output was authorised.
VERDICT_STATUS: Mapping[str, str] = {
    "fully_compliant": "compliant",
    "violations_detected": "warning",
    "not_publishable_input": "withheld",
    "structural_infeasibility": "warning",
    "blocked": "blocked",
}

# RunBlocked messages: a substring of the core message → plain label.
BLOCKED_REASONS: Tuple[Tuple[str, Label], ...] = (
    (
        "insufficient_peers",
        Label(
            "Not enough peers to benchmark safely",
            "",
            "Choose a broader peer group (a different entity column) or fewer filters.",
        ),
    ),
    (
        "optimization_aborted",
        Label(
            "The weighting step couldn't find a valid solution",
            "",
            "Try a preset with more tolerance, or fewer dimensions.",
        ),
    ),
    (
        "requires explicit acknowledgement",
        Label(
            "This preset needs your consent for each run",
            "",
            "Run again and give consent when the dialog asks for it.",
        ),
    ),
    (
        "acknowledgement required",
        Label(
            "This preset needs your consent for each run",
            "",
            "Run again and give consent when the dialog asks for it.",
        ),
    ),
    (
        "Configuration could not be resolved",
        Label(
            "The settings couldn't be combined into a valid configuration",
            "",
            "Reload the preset's advanced values (choose the preset again), then run again.",
        ),
    ),
    (
        "Structural infeasibility",
        Label(
            "Some categories can't meet the rules with any weighting",
            "Too few peers in some categories.",
            "Merge or drop those categories, or choose a broader peer group.",
        ),
    ),
)

BLOCKED_FALLBACK = Label(
    "The run was stopped by a policy check",
    "",
    "Read the reason in the code line below, adjust the settings, then run again.",
)

# RunAborted messages: a message prefix → plain label.
ABORTED_PREFIXES: Tuple[Tuple[str, Label], ...] = (
    (
        "privacy_release_mode=verified-safe-coverage is not supported for rate",
        Label("Verified safe coverage works for share analysis only.", "", "Choose Complete output."),
    ),
    (
        "privacy_release_mode=verified-safe-coverage requires one global weight vector",
        Label("Verified safe coverage needs one set of weights for all dimensions.", "", ""),
    ),
    (
        "privacy_release_mode=verified-safe-coverage requires privacy_rule_strategy=",
        Label(
            "Verified safe coverage needs the privacy rule sweep.",
            "",
            "It is switched on automatically. Run again.",
        ),
    ),
    (
        "verified-safe-coverage requires a non-empty governed peer population",
        Label("Verified safe coverage found no peers to work with.", "", "Choose a broader peer group."),
    ),
    (
        "Metric column",
        Label("A selected column isn't in this CSV.", "", "Reload the file or pick another column."),
    ),
    (
        "Total column",
        Label("A selected column isn't in this CSV.", "", "Reload the file or pick another column."),
    ),
    (
        "Rate column",
        Label("A selected column isn't in this CSV.", "", "Reload the file or pick another column."),
    ),
    (
        "No analysis results generated",
        Label(
            "The analysis produced no results.",
            "",
            "Check that the dimensions have data for the target entity.",
        ),
    ),
)

ABORTED_FALLBACK = Label(
    "The run stopped before it could finish.",
    "",
    "Read the reason in the code line below, fix it, then run again.",
)

UNEXPECTED_ERROR = Label(
    "Something went wrong inside the analysis.",
    "An unexpected error stopped the run. The input file was not changed.",
    "Check that the CSV has the columns this preset expects, then run again. "
    "If it repeats, send the run log to support.",
)

START_FAILED = Label(
    "The run couldn't start.",
    "",
    "Check the CSV path and settings, then run again.",
)

DATA_CHECK_FAILED = Label(
    "The data check couldn't finish.",
    "",
    "Open the CSV in a spreadsheet, check the columns named above, then reload it.",
)

# A cancelled run (Quit, or a cancel request) writes no output at all.
RUN_CANCELLED_BEFORE_START = Label(
    "Run cancelled · nothing was written",
    "The run was stopped before the analysis started.",
    "Run again when you are ready.",
)

RUN_CANCELLED = Label(
    "Run cancelled · nothing was written",
    "The run stopped at a safe checkpoint, before any output was written.",
    "Run again when you are ready.",
)


def label_for(kind: str, code: Optional[object]) -> Label:
    """Return the label for ``(kind, code)``; unknown codes get a safe fallback."""
    if code is None:
        return Label(UNRECOGNISED)
    key = (kind, str(getattr(code, "value", code)))
    return LABELS.get(key, Label(UNRECOGNISED))


def text_for(kind: str, code: Optional[object]) -> str:
    """Primary text for ``(kind, code)``."""
    return label_for(kind, code).primary


def blocked_label(message: str) -> Label:
    """Plain label for a ``RunBlocked`` message."""
    for needle, label in BLOCKED_REASONS:
        if needle in message:
            return label
    return BLOCKED_FALLBACK


def aborted_label(message: str) -> Label:
    """Plain label for a ``RunAborted`` message."""
    for prefix, label in ABORTED_PREFIXES:
        if message.startswith(prefix):
            return label
    return ABORTED_FALLBACK


def strip_preset_description(description: str) -> str:
    """Drop the ``(formerly ...)`` suffix from a preset description for display."""
    text = description.strip()
    index = text.find("(formerly ")
    if index != -1 and text.endswith(")"):
        text = text[:index].rstrip()
    return text


def kinds() -> Dict[str, Tuple[str, ...]]:
    """Codes per kind, for exhaustiveness tests and documentation."""
    out: Dict[str, list] = {}
    for kind, code in LABELS:
        out.setdefault(kind, []).append(code)
    return {kind: tuple(codes) for kind, codes in out.items()}
