"""The form model: one app-owned source of truth for every form value.

TUI redesign Phase 2 PR 5 (01 §2.2, 03 §1.1). ``BenchmarkApp.form`` is a
``FormState``. Widgets bind to it: a widget's change handler writes the field,
and a field change re-syncs the widget, if that widget is mounted. Everything
else reads the model, never a widget: the ``RunInputs`` snapshot, readiness,
the rail, the Review step and session save/restore. That is what lets a step's
widgets be mounted only when the step is first shown.

Assigning a field notifies the app (``set_listener``) only when the value
really changes, so the bind loop ends after one echo.

Privacy rules carried by this module (unchanged from the widget-based form):

- ``SESSION_FIELDS`` lists what a session may store. Governed data references
  (CSV path, output file), the target entity, the compliance declarations and
  the Citibank entity, consent and the expert diff are never in it.
- Column choices are restored only after a CSV header load, and only where the
  column exists in that file (D4).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from core.contracts import PrivacyReleaseMode

SHARE = "share"
RATE = "rate"
MODES = (SHARE, RATE)

COMPLETE_OUTPUT = PrivacyReleaseMode.COMPLETE_OUTPUT.value
VERIFIED_SAFE_COVERAGE = PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE.value


@dataclass(eq=False)
class FormState:
    """Every value the operator sets on the main screen."""

    # 1 · Data
    csv_path: str = ""
    # 2 · Entity
    entity_col: Optional[str] = None
    # Target entity. Small lists: the Select choice. Large lists (above the
    # Select limit): the exact value typed in the filter, or None.
    entity: Optional[str] = None
    # Large lists only: the filter text as typed (a typo must never become a
    # peer-only run, so readiness checks it against the loaded values).
    entity_filter: str = ""
    # 3 · Analysis & mode
    mode: str = SHARE
    metric: Optional[str] = None
    total_col: Optional[str] = None
    approved_col: Optional[str] = None
    fraud_col: Optional[str] = None
    # One dimensions list for both modes (01 §2.2); columns that hold a role
    # in the active mode are hidden from it and never sent.
    dimensions: Tuple[str, ...] = ()
    auto_dims: bool = False
    secondary: Tuple[str, ...] = ()
    # 3 · More options
    time_col: Optional[str] = None
    output_format: str = "analysis"
    output_file: str = ""
    validate_input: bool = True
    analyze_distortion: bool = True
    compare_presets: bool = False
    # Owner decision 5: off by default for share, rate and the CLI.
    export_balanced_csv: bool = False
    include_calculated: bool = False
    fraud_in_bps: bool = True
    # Expert screen · Output sheets (D5: the one debug-sheets control).
    debug: bool = True
    # 4 · Privacy & compliance
    preset: Optional[str] = None
    release_mode: str = COMPLETE_OUTPUT
    # The operator's own rule-sweep value. Verified safe coverage on a share
    # run locks the sweep on without changing it (owner decision 6).
    rule_sweep: bool = False
    # Declarations: per run, never saved or restored.
    merchant_spend: bool = False
    citi_competitor: bool = False
    citibank_entity: Optional[str] = None
    citibank_filter: str = ""
    # Expert settings: an in-memory diff against the current preset
    # (01 §8.2), keyed by ConfigFieldSpec.widget_id. Never saved.
    expert: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_listener", None)
        # Dataset facts from the last header load (not form values).
        object.__setattr__(self, "columns", ())
        object.__setattr__(self, "numeric_columns", frozenset())
        # Fields holding a value restored from the last session (rail and ↺).
        object.__setattr__(self, "restored", set())

    def set_listener(self, listener: Optional[Callable[[str, Any, Any], None]]) -> None:
        object.__setattr__(self, "_listener", listener)

    def __setattr__(self, name: str, value: Any) -> None:
        if name not in FIELD_NAMES:
            object.__setattr__(self, name, value)
            return
        value = _normalise(name, value)
        old = getattr(self, name, _MISSING)
        if old is not _MISSING and old == value:
            return
        object.__setattr__(self, name, value)
        listener = getattr(self, "_listener", None)
        if listener is not None and old is not _MISSING:
            listener(name, old, value)

    def update(self, **values: Any) -> None:
        for name, value in values.items():
            if name not in FIELD_NAMES:
                raise AttributeError(f"FormState has no field {name!r}")
            setattr(self, name, value)

    def set_columns(self, columns: Sequence[str], numeric: Iterable[str]) -> None:
        object.__setattr__(self, "columns", tuple(columns))
        object.__setattr__(self, "numeric_columns", frozenset(numeric))

    # ── Derived values (pure; no widgets) ──────────────────────────────

    @property
    def is_share(self) -> bool:
        return self.mode == SHARE

    @property
    def sweep_locked(self) -> bool:
        """Verified safe coverage forces the rule sweep, on share runs only."""
        return self.mode == SHARE and self.release_mode == VERIFIED_SAFE_COVERAGE

    @property
    def effective_sweep(self) -> bool:
        return True if self.sweep_locked else bool(self.rule_sweep)

    def role_columns(self) -> FrozenSet[str]:
        """Columns already assigned a role in the active mode."""
        roles = {self.entity_col, self.time_col}
        if self.mode == SHARE:
            roles.add(self.metric)
        else:
            roles.update((self.total_col, self.approved_col, self.fraud_col))
        return frozenset(r for r in roles if r)

    def dimension_options(self) -> Tuple[str, ...]:
        """Dimensions list: every column without a role, text columns first."""
        roles = self.role_columns()
        free = [c for c in self.columns if c not in roles]
        return tuple(sorted(free, key=lambda c: c in self.numeric_columns))

    def secondary_options(self) -> Tuple[str, ...]:
        """Secondary metrics: numeric columns without a role."""
        roles = self.role_columns()
        return tuple(c for c in self.columns if c in self.numeric_columns and c not in roles)

    def effective_dimensions(self) -> Tuple[str, ...]:
        options = set(self.dimension_options())
        return tuple(d for d in self.dimensions if d in options)

    def effective_secondary(self) -> Tuple[str, ...]:
        options = set(self.secondary_options())
        return tuple(m for m in self.secondary if m in options)

    def numeric_first(self, columns: Optional[Sequence[str]] = None) -> Tuple[List[str], List[str]]:
        """(numeric, other) columns in file order, for the metric and total Selects."""
        cols = self.columns if columns is None else columns
        numeric = [c for c in cols if c in self.numeric_columns]
        return numeric, [c for c in cols if c not in self.numeric_columns]

    def more_options_changed(self) -> int:
        """How many "More options" values differ from their defaults."""
        defaults = FormState()
        names = MORE_OPTIONS_FIELDS if self.mode == RATE else tuple(
            n for n in MORE_OPTIONS_FIELDS if n != "fraud_in_bps"
        )
        changed = sum(1 for name in names if getattr(self, name) != getattr(defaults, name))
        return changed


_MISSING = object()
FIELD_NAMES: FrozenSet[str] = frozenset(f.name for f in fields(FormState))

_TUPLE_FIELDS = frozenset({"dimensions", "secondary"})
_BOOL_FIELDS = frozenset(
    {
        "auto_dims",
        "validate_input",
        "analyze_distortion",
        "compare_presets",
        "export_balanced_csv",
        "include_calculated",
        "fraud_in_bps",
        "debug",
        "rule_sweep",
        "merchant_spend",
        "citi_competitor",
    }
)
_OPTIONAL_TEXT_FIELDS = frozenset(
    {
        "entity_col",
        "entity",
        "metric",
        "total_col",
        "approved_col",
        "fraud_col",
        "time_col",
        "preset",
        "citibank_entity",
    }
)


def _normalise(name: str, value: Any) -> Any:
    if name in _TUPLE_FIELDS:
        seen: List[str] = []
        for item in value or ():
            if item not in seen:
                seen.append(item)
        return tuple(seen)
    if name in _BOOL_FIELDS:
        return bool(value)
    if name in _OPTIONAL_TEXT_FIELDS:
        return None if value in (None, "") else value
    if name == "expert":
        return dict(value or {})
    if name == "mode" and value not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {value!r}")
    return value


# "More options" disclosure on step 3 (01 §2.2 tier M).
MORE_OPTIONS_FIELDS: Tuple[str, ...] = (
    "time_col",
    "secondary",
    "output_format",
    "fraud_in_bps",
    "output_file",
    "validate_input",
    "analyze_distortion",
    "compare_presets",
    "export_balanced_csv",
    "include_calculated",
)

# Fields that name CSV columns: restored only after a header load, and only
# where the column exists in that file (D4).
COLUMN_FIELDS: FrozenSet[str] = frozenset(
    {"entity_col", "time_col", "metric", "total_col", "approved_col", "fraud_col"}
)
COLUMN_LIST_FIELDS: FrozenSet[str] = frozenset({"dimensions", "secondary"})

# Session file keys. The scalar keys keep their pre-PR 5 names (they were
# widget ids), so a session saved by an older build restores here too.
SESSION_KEYS: Dict[str, str] = {
    "entity_col": "entity_col",
    "time_col": "time_col",
    "preset": "preset_select",
    "output_format": "output_format",
    "release_mode": "privacy_release_mode",
    "metric": "share_metric",
    "total_col": "rate_total",
    "approved_col": "rate_approved",
    "fraud_col": "rate_fraud",
    "analyze_distortion": "analyze_distortion",
    "compare_presets": "compare_presets",
    "validate_input": "validate_input",
    "include_calculated": "include_calculated",
    "fraud_in_bps": "fraud_in_bps",
    "rule_sweep": "privacy_rule_sweep_mode",
    "auto_dims": "auto_dims",
    "debug": "debug",
    "export_balanced_csv": "export_balanced_csv",
    "dimensions": "dimensions",
    "secondary": "secondary_metrics",
}
SESSION_MODE_KEY = "analysis_mode"

# Pre-PR 5 per-tab keys, read and mapped to the merged controls (01 §8.1).
LEGACY_SESSION_KEYS: Dict[str, Tuple[str, str]] = {
    "auto_dims": ("share_auto_dim", "rate_auto_dim"),
    "debug": ("share_debug", "rate_debug"),
    "export_balanced_csv": ("share_export_csv", "rate_export_csv"),
    "dimensions": ("share_dims", "rate_dims"),
    "secondary": ("share_secondary", "rate_secondary"),
}

# Never written to or read from a session (privacy rule; 01 §8.1).
NEVER_RESTORED: FrozenSet[str] = frozenset(
    {
        "csv_path",
        "output_file",
        "entity",
        "entity_filter",
        "merchant_spend",
        "citi_competitor",
        "citibank_entity",
        "citibank_filter",
        "expert",
    }
)
assert not NEVER_RESTORED & set(SESSION_KEYS), "a never-restored field has a session key"

# Smart defaults applied after a header load to fields that are still empty
# (01 §2.2). Owner decision 4: the rate Total column never gets one.
SMART_DEFAULTS: Tuple[Tuple[str, str], ...] = (
    ("entity_col", "issuer_name"),
    ("metric", "txn_cnt"),
    ("approved_col", "app_cnt"),
)
assert "total_col" not in dict(SMART_DEFAULTS), "owner decision 4: no Total default"

# The step each field lives on (rail glyphs, Review, "jump to field").
FIELD_STEPS: Dict[str, str] = {
    "csv_path": "data",
    "entity_col": "entity",
    "entity": "entity",
    "entity_filter": "entity",
    "mode": "analysis",
    "metric": "analysis",
    "total_col": "analysis",
    "approved_col": "analysis",
    "fraud_col": "analysis",
    "dimensions": "analysis",
    "auto_dims": "analysis",
    **{name: "analysis" for name in MORE_OPTIONS_FIELDS},
    "debug": "analysis",
    "expert": "analysis",
    "preset": "privacy",
    "release_mode": "privacy",
    "rule_sweep": "privacy",
    "merchant_spend": "privacy",
    "citi_competitor": "privacy",
    "citibank_entity": "privacy",
    "citibank_filter": "privacy",
}
assert set(FIELD_STEPS) == set(FIELD_NAMES), set(FIELD_NAMES) ^ set(FIELD_STEPS)


def session_payload(form: FormState, pending: Mapping[str, Any]) -> Dict[str, Any]:
    """What ``_save_session`` writes: preferences and column roles only.

    ``pending`` holds column choices restored from the last session that no
    header load has applied yet; they are kept so a quit before loading a file
    does not erase them.
    """
    payload: Dict[str, Any] = {}
    for name, key in SESSION_KEYS.items():
        value = getattr(form, name)
        if name in COLUMN_FIELDS | COLUMN_LIST_FIELDS and not value and name in pending:
            value = pending[name]
        payload[key] = list(value) if isinstance(value, tuple) else value
    payload[SESSION_MODE_KEY] = form.mode
    return payload


def read_session(session: Mapping[str, Any]) -> Dict[str, Any]:
    """Field values a stored session holds, legacy keys mapped, governed keys dropped."""
    values: Dict[str, Any] = {}
    mode = session.get(SESSION_MODE_KEY)
    if mode in MODES:
        values["mode"] = mode
    active = 1 if mode == RATE else 0
    for name, key in SESSION_KEYS.items():
        if key in session and session[key] is not None:
            values[name] = session[key]
            continue
        legacy = LEGACY_SESSION_KEYS.get(name)
        if legacy is None:
            continue
        # The active tab's legacy value wins; the other tab's is the fallback.
        for legacy_key in (legacy[active], legacy[1 - active]):
            if legacy_key in session and session[legacy_key] not in (None, []):
                values[name] = session[legacy_key]
                break
    for name in list(values):
        if name in COLUMN_LIST_FIELDS:
            raw = values[name]
            values[name] = [str(v) for v in raw] if isinstance(raw, list) else []
            if not values[name]:
                del values[name]
        elif name in _BOOL_FIELDS:
            values[name] = bool(values[name])
    return values
