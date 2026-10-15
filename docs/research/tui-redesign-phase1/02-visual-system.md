# TUI Redesign Phase 1: 02 Visual System

Phase 1 is a design spec. It changes no repo code. This document defines the
design tokens, the status language, the checkbox affordance, the typography and
density rules, and the copy guidelines with a glossary. Structure, keys, states
and flows are in [01](01-interaction-design.md). Mounting, workers and budgets
are in [03](03-performance-architecture.md). The evidence base is
[Phase 0](../tui-redesign-phase0/00-summary.md), mainly the CSS/token audit,
the NO_COLOR/ANSI findings (T4–T6) and the copy audit in
[03 Heuristic review](../tui-redesign-phase0/03-heuristic-review.md).

Line numbers refer to `tui_app.py` at `f6f47b6` (after the D1 validation-modal fix). Other branches are editing the file, so each reference also names the symbol or string.

**Evidence.** Every claim marked *(verified)* was checked in a throwaway
Textual 7.5.0 prototype on Python 3.13. Nothing below is in the repo:

| Artefact | Path (scratchpad) |
|---|---|
| Token stylesheet (draft of `tui/styles/autobench.tcss`) | `…/phase1-vs/autobench.tcss` |
| Prototype app: status gallery, step form, result card | `…/phase1-vs/proto_visual.py` |
| Capture script (6 modes per screen) | `…/phase1-vs/cap.sh` → `shots/*.svg`, `png/*.png` |
| Footer under ANSI, segment dump | `…/phase1-vs/proto_footer.py`, `footer_segs3.py` |
| TCSS variable scoping tests | `…/phase1-vs/t1/` |

`…` is `/tmp/claude-0/-home-user-autobench/d13cb994-08e3-5f72-b4d1-86adf775fd7d/scratchpad`.
All captures are 80x24. The modes are `textual-dark`, `tokyo-night`,
`textual-light`, `textual-ansi`, `NO_COLOR=1` (dark), and `NO_COLOR=1` with
`textual-ansi`. The status gallery was also captured with the ASCII glyph set.

## Decision summary

- **One stylesheet, loaded with `CSS_PATH`.** Textual 7.5 TCSS variables are
  *file-scoped* *(verified)*, so the token block and every component rule live
  in one file: `tui/styles/autobench.tcss`. All `$ab-*` colour tokens are
  aliases of Textual theme variables, so every theme re-resolves them, including
  `textual-ansi`. No literal colours remain, apart from 16-colour names inside
  `App:ansi` overrides.
- **NO_COLOR and ANSI get their own rules** through the built-in `App:nocolor`
  and `App:ansi` pseudo-classes *(verified)*. Under NO_COLOR, Textual's
  `Monochrome` filter turns every colour into grey luminance. That is why
  today's `[red]Blocked[/red]` turns into dark grey on dark grey (03 T5). The
  fix is to carry meaning in glyph + word + text style (bold, reverse), never
  colour.
- **Twelve run and readiness states**, each with a word, a glyph, an ASCII
  fallback and a colour role. The three outcomes that stop or withhold a
  publication (WITHHELD, BLOCKED, FAILED) are always a filled badge: reverse
  video under NO_COLOR, full-strength 16-colour fill under ANSI.
- **Checkboxes and selection lists draw `[x]` / `[ ]`.** A ten-line subclass of
  each replaces the stock `▐X▌`, which draws the same glyph in both states.
- **Compact density.** Form widgets use Textual's stock `compact=True` (one
  row, no border). Borders are kept only for things that frame content:
  modals, multi-row lists and the status/results panels. Focus is shown by a
  shape or reverse-video change, never by a tint alone.
- **Copy.** Internal codes are never primary text. A label table maps each
  code to a plain sentence, and the code stays visible as a dimmed `Code: …`
  line. Errors follow *what happened → why → what to do*, plus where the log
  is.
- **Two findings for the other specs.** Setting `self.theme` in `on_mount`
  (`on_mount`, `tui_app.py:1203`) costs a second full stylesheet pass at startup
  ([03 §1.3](03-performance-architecture.md#13-theme-assignment-moves-to-__init__)).
  The stock `Footer` under `textual-ansi` renders descriptions as `#000000` on
  `#000000` (§1.5).

---

## 1. Design tokens

### 1.1 What Textual 7.5 allows (found by prototype)

| Finding | Consequence for the token layer | Evidence |
|---|---|---|
| A `$variable` declared in one TCSS source is not visible in another `CSS_PATH` file, a `Screen.CSS` string or a `DEFAULT_CSS` block. A reference raises `UnresolvedVariableError`. | Tokens and every rule that uses them go in **one** file. Screens and modals get **no** `CSS =` strings of their own (today `PresetHelpScreen.CSS`, `tui_app.py:340`, has one). App-level `CSS_PATH` rules already style every screen. | `t1/a.tcss` + `t1/b.tcss` |
| A TCSS variable can alias a theme variable (`$ab-danger: $text-error;`). A theme switch re-resolves it. | Colour tokens are aliases, not values, so all themes work with no per-theme table. | `t1/test2.py`: `$ab-danger-file` resolved to `#b93c5b` under `textual-dark`, and to ANSI colour 1 after `app.theme = "textual-ansi"`. |
| Values returned from `App.get_theme_variable_defaults()` must be literal. `"$panel"` is rejected as a background. | Python-side tokens are only possible as computed literals. We don't need them (see the markup rule below). | `t1/test.py` |
| Content markup resolves **theme** variables (`[$text-error]`) but not TCSS-file variables. | Python code may use theme variables in markup, from a short allow-list, and never `[red]`/`[green]`. Status colour always comes from CSS classes on `StatusBadge`. | `t1/test2.py` |
| `App:nocolor` and `App:ansi` work as selector prefixes. | NO_COLOR and ANSI overrides sit next to the rule they override. | `t1/test3.py` |
| Border style keywords and multi-value spacing can be variables (`$ab-border-panel: round;`, `$ab-gutter-pane: 0 1;`). | Border styles and spacing are tokens too. | `t1/test3.py` |
| Under NO_COLOR, `App.__init__` adds `Monochrome()` (or `NoColor()` when `ansi_color` is set). Colours become grey luminance, while bold, italic, reverse and underline survive. | The NO_COLOR fallback for every state is a text style plus the glyph and word. | `textual/app.py:589-591`, `filter.py:77-121` |

### 1.2 The token block

This is the head of `tui/styles/autobench.tcss`, exactly as prototyped
*(verified in 6 modes)*:

```tcss
/* Autobench TUI: design tokens + component rules.
   TCSS variables are FILE-SCOPED in Textual 7.5. Keep every app rule in this
   one file. Colour tokens alias Textual theme variables, so every theme,
   including textual-ansi, re-resolves them. No literal colours, except
   16-colour names inside App:ansi overrides. */

/* ── Colour roles ─────────────────────────────────────────────────────── */
$ab-surface:        $background;      /* app canvas                        */
$ab-panel:          $surface;         /* cards, modals, status column      */
$ab-panel-raised:   $panel;           /* action bar, current rail step     */
$ab-field:          $boost;           /* input/select well                 */
$ab-border:         $primary 40%;     /* idle panel border                 */
$ab-border-strong:  $primary;         /* emphasised panel, modal frame     */
$ab-focus:          $accent;          /* focus ring and focus well         */
$ab-text:           $foreground;
$ab-muted:          $text-muted;      /* hints, secondary codes            */
$ab-accent:         $text-accent;     /* headings, step numbers            */
$ab-success:        $text-success;
$ab-warning:        $text-warning;
$ab-danger:         $text-error;
$ab-info:           $text-primary;
$ab-warning-fill:   $warning;         /* WITHHELD badge fill               */
$ab-danger-fill:    $error;           /* BLOCKED / FAILED badge fill       */
$ab-on-fill:        $text;            /* auto-contrast text on a fill      */
$ab-backdrop:       $background 60%;  /* modal backdrop                    */

/* ── Spacing scale (cells) ────────────────────────────────────────────── */
$ab-space-0: 0;
$ab-space-1: 1;
$ab-space-2: 2;
$ab-gutter-pane:  0 1;   /* pane and modal inner padding                  */
$ab-gutter-field: 0 1;   /* text inside a 1-row field well                */

/* ── Border styles ────────────────────────────────────────────────────── */
$ab-border-panel: round;   /* titled panels, idle                         */
$ab-border-focus: heavy;   /* list or panel holding focus (shape change)  */
$ab-border-modal: thick;   /* modal frame                                 */

/* ── Sizes ────────────────────────────────────────────────────────────── */
$ab-modal-sm: 60;
$ab-modal-md: 76;          /* fits 80 columns with a 2-column margin       */
$ab-list-rows: 6;
```

The component rules that follow in the same file are in §2 (status), §3
(checkboxes) and §4 (typography, fields, panels). The complete prototype file
is `…/phase1-vs/autobench.tcss`.

**Python-side rule (markup).** Python never writes `[red]`, `[green]`,
`[yellow]`, `[cyan]` or `[dim]`. Where inline markup is unavoidable, it uses
theme variables from this allow-list: `$text-muted`, `$text-accent`,
`$text-success`, `$text-warning`, `$text-error`, `$text-primary`, plus `b`,
`i` and `reverse`. Every dynamic string goes through `rich.markup.escape`, or
is built as `Content`/`Text` without markup (03 F31). Status never uses
markup at all. It is a `StatusBadge` widget whose CSS class picks the colour.

### 1.3 How the app loads it

```python
# tui_app.py (Phase 2)
from pathlib import Path

class BenchmarkApp(App):
    CSS_PATH = Path(__file__).parent / "tui" / "styles" / "autobench.tcss"
    # No CSS = """...""" string here, and none on any Screen subclass.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the default theme before the first stylesheet pass. Today's
        # self.theme = "tokyo-night" in on_mount (tui_app.py:1203) restyles all
        # 233 widgets a second time: 03 §1.3 measures startup stall 530 -> 280 ms.
        self.theme = os.environ.get("AUTOBENCH_THEME", "tokyo-night")
```

- **Packaging.** `tui_app.py` ships as a single module (`pyproject.toml:34`
  `py-modules`). The stylesheet needs:
  1. `tui` added to `[tool.setuptools.packages.find] include`.
  2. `[tool.setuptools.package-data] tui = ["styles/*.tcss"]`.
  3. `"tui/**/*.py"` and `"tui/**/*.tcss"` added to `runtime_paths` in
     `edge_deploy.yaml:7`.

  Item 3 is release tooling, so a Release Operator must confirm it (AGENTS.md).
  Without item 3, deployed installs fail at startup with a missing stylesheet.
  Add a test that `BenchmarkApp.CSS_PATH` exists and that `edge_deploy.yaml`
  globs match it.
- **Fallback** if the owners want no packaging change in the first PR: put the
  same text in `tui/styles.py` as `AUTOBENCH_TCSS = """…"""` and assign
  `App.CSS = AUTOBENCH_TCSS`. The variables stay file-scoped within that one
  string, so the rules are identical. The cost is editor TCSS support and
  `textual run --dev` live reload.
- **Theme choice.** `AUTOBENCH_THEME`, or the stock command-palette theme
  switcher, is respected. Today's forced `tokyo-night` on mount overrides the
  user's choice (03 T6). Persisting the theme in the session file is 01's
  decision (§8.1).

**Phase 2 PR 3 (as built).** The stylesheet ships as the Python module
`tui/styles.py` (`AUTOBENCH_TCSS`, assigned to `BenchmarkApp.CSS`), the
"Fallback" above, not as `tui/styles/autobench.tcss`. Only `*.py` globs reach
edge nodes (`edge_deploy.yaml` `runtime_paths`), so a `.tcss` file would need
a new glob plus `package-data` and would fail at startup if either were
missed. The rules are the same, because TCSS variables stay file-scoped
within the one string. The cost is editor TCSS support and `textual run --dev`
live reload. The packaging change is: `"tui/**/*.py"` in `runtime_paths`,
`tui` in `compile_targets` (and in the matching `compileall` lines of
`setup_remote_env.sh`, `tools/prod_tui/harness.py` and
`tools/dev/local_check.ps1`), and `tui*` in the `pyproject.toml`
`packages.find` include. Deploying it remains a Release Operator step.

Other as-built differences, all inside this PR's scope:

- The validation modal is `width: 90%; max-width: $ab-modal-lg` (110), not
  `$ab-modal-md`. At 76 columns long issue messages wrapped mid-phrase.
- `ToggleButton` and `SelectionList` subclasses are `BoxCheckbox` and
  `BoxSelectionList` in `tui/widgets.py`.
- The key bar (`tui/keybar.py`) maps clicks by cell range, not `@click`
  markup: a link style would override the key colour roles.
- Advanced and Export moved from `Ctrl+A`/`Ctrl+E` (taken by a focused
  `Input` for Home/End) to `F8`/`F9`; the old keys stay as hidden aliases.
  Textual 7.5 binds `Ctrl+C` to copy and only hints at quitting, so the app
  owns it: copy when text is selected, otherwise quit like `Ctrl+Q`.

### 1.4 Coverage of the Phase 0 CSS audit

Every hard-coded or ad-hoc value from 03 §3, mapped to its replacement:

| 03 audit item | Today (`tui_app.py`) | Replacement |
|---|---|---|
| `rgba(0,0,0,0.7)` ×4 (modal backdrops) | `:343, 792, 854, 912`: `PresetHelpScreen.CSS`, `ValidationModal`, `CsvPickerScreen`, `ConfirmScreen` blocks in `BenchmarkApp.CSS` | One rule: `ModalScreen { background: $ab-backdrop; align: center middle; }` |
| `[dim]` ×34 in Python | status lines, results, CSV meta (`_refresh_run_status` `:1441-1462`, `_format_safe_coverage_summary_markup` `:1673-1685`, `_update_csv_meta` `:1846`) | `.ab-hint` / `.ab-code` widgets, or `[$text-muted]` from the allow-list |
| `[red]` ×16, `[green]` ×7, `[yellow]` ×5, `[cyan]` ×3 | `_STATE_BADGES` `:1441-1448`, verdict colouring `:2864-2870`, withheld `:2887`, exception handlers `:2932-2943`, CSV ✓ `:1846` | `StatusBadge` with state classes (§2). No colour in markup. |
| `[b]` ×7 | badges, labels | `.ab-title`, or the badge's own bold. `b` stays allowed in markup. |
| Opacity steps 40% / 50% / 60% with no stated meaning | `$primary 40%` ×6, `$primary 50%` ×1, `$warning 60%`, `$accent 60%` | Only two alpha uses remain: `$ab-border` (idle border, 40%) and `$ab-backdrop` (60%). |
| `$warning` used as decoration (`.adv-group-title`, Compliance border) | `:761` `.adv-group-title { color: $warning }`, `#compliance_declarations { border: round $warning 60% }` | `.ab-section` (`$ab-accent`). Warning colour is reserved for warnings. |
| `$accent 60%` Advanced border | `#advanced_opt` | Removed: Expert settings is its own screen (01 §2). |
| `$secondary`, `$boost` on lists | `#issue_list`, `#picker_quick_list` | `.ab-list` (`$ab-panel`, `$ab-border`) |
| `margin-bottom: 1` ×22, `margin-top: 1` ×7, `margin-right: 1/2` | global `Input`/`Select` margins, `.section-title`, `.field-label`, etc. | `.ab-field { margin: 0 0 $ab-space-1 0 }` only. No global widget margins. |
| Padding `1 2`, `0 1`, `0 2`, `1` (4 values) | sections, modals, log | `$ab-gutter-pane` (`0 1`) everywhere. Modals no longer spend 2 rows on vertical padding. |
| Widths `58%`, `70%`, `80%`, `84%`, `40%`, `60`; max-widths `100`/`110`/`120`; min-widths `64`/`42`/`28`/`16` | panes and modals | `$ab-modal-sm` / `$ab-modal-md` with `max-width: 100%`. Pane widths come from 01's 110-column breakpoint (01 §3.1), not from min-widths that add up to more than 80 (T1). |
| Heights `80%`, `70%`; magic `7`, `14`, `5`, `8` | `.multi-select { height: 7 }`, `#results_panel { max-height: 14 }`, `min-height: 5/8` | `$ab-list-rows` (6). Modals size by `height: auto; max-height: 100%`. Results become a view at <110 (01). |
| Duplicated trio `border: round $primary 40%; border-title-color: $text-accent; border-title-style: bold` ×4 | `.form-section`, `#run_status`, `#results_panel`, `#log_output` | `.ab-panel` component class |
| Modal centring ×4 | four `align: center middle` blocks | `ModalScreen` rule above |
| Identical `.input-group …` / `.split-inputs …` rules | `:639-652` | Gone: fields stack vertically (F22) |
| About 30 `#id` selectors | throughout | Component classes: `.ab-panel`, `.ab-modal`, `.ab-field`, `.ab-label`, `.ab-hint`, `.ab-code`, `.ab-path`, `.ab-section`, `.ab-title`, `.ab-list`, `StatusBadge`. IDs stay for queries, not for styling. |
| Focus as tint only: `.form-section:focus-within` 40% → 100% | `:604` | `.ab-field:focus-within > .ab-label { text-style: bold reverse }` plus `.ab-list:focus { border: $ab-border-focus $ab-focus }`. This is also the performance fix (03 §2). |
| `self.theme = "tokyo-night"` forced in `on_mount` | `:1203` | Default set in `__init__`, overridable (§1.3) |
| `PresetHelpScreen.CSS` separate block | `:340` | Removed. Its rules move into `autobench.tcss` (file scoping). |

### 1.5 ANSI-specific rules (03 T6)

The stock `Footer` already has `:ansi` rules. In Textual 7.5 they still
resolve the description to `#000000 on #000000` (*verified* by dumping the
footer strip's segments: `'Run ' #000000 on #000000`). The descriptions are
invisible in a real terminal too, not just in screenshots. This override
renders `color(15) on color(0)` *(verified)*:

```tcss
App:ansi Footer, App:ansi Footer FooterKey { background: ansi_black; }
App:ansi Footer FooterKey .footer-key--key { background: ansi_black; color: ansi_bright_cyan; text-style: bold; }
App:ansi Footer FooterKey .footer-key--description { background: ansi_black; color: ansi_bright_white; }
App:nocolor Footer FooterKey .footer-key--key { text-style: bold reverse; }
```

Under ANSI, alpha blends collapse to the base colour. `$primary 40%` becomes
plain `ansi_blue`. That is acceptable for borders. Focus wells and fills use
explicit 16-colour pairs in `App:ansi` rules (§2.3, §4.3).

---

## 2. Status language

### 2.1 The states

Every state has a **word** (upper case in badges and the action bar, so it is
distinct without colour), a **glyph**, an **ASCII fallback**, a **colour role**
and a **NO_COLOR treatment**. Glyph and word always appear together.
Neither ever appears alone.

| State | Badge word | Glyph | ASCII | Colour role (CSS) | NO_COLOR | ANSI | Used for (internal source) |
|---|---|---|---|---|---|---|---|
| ready | `READY` | `●` U+25CF | `(*)` | `$ab-success`, bold | bold | green, bold | Form complete, `^R` will run (`_run_state="idle"` and no blockers) |
| not ready | `NOT READY` | `!` | `(!)` | `$ab-warning`, bold | bold | yellow, bold | A blocker exists (01 §5.2) |
| loading | `LOADING` (or the task: `READING HEADERS`) | `◌` U+25CC | `(~)` | `$ab-info`, italic | italic | blue, italic | CSV header read, entity values worker (`ENTITY_LOADING_PROMPT`), posture resolve |
| running | `RUNNING n/4` | `▸` U+25B8 | `(>)` | `$ab-info`, bold | bold | blue, bold | `validating`, `running` (`_STATE_BADGES`), 01 stages |
| awaiting | `WAITING FOR YOU` | `?` | `(?)` | `$ab-warning`, bold | bold | yellow, bold | A consent, attestation or validation dialog is open (03 F02) |
| success | `DONE` | `✓` U+2713 | `(+)` | `$ab-success`, bold | bold | green, bold | Run finished and the report was written (`success`) |
| compliant | `COMPLIANT` | `◆` U+25C6 | `(=)` | `$ab-success`, bold | bold | green, bold | Verdict `fully_compliant` (a second badge next to DONE) |
| warning | `WARNING` | `▲` U+25B2 | `(^)` | `$ab-warning`, bold | bold | yellow, bold | Done but labelled: `best_effort` violations, `accuracy_first` diagnostic, validation warnings |
| withheld | `WITHHELD` | `◐` U+25D0 | `(-)` | **fill** `$ab-warning-fill` / `$ab-on-fill` | **bold reverse** | black on yellow | `privacy_sink_authorized is not True`: publication withheld (any `control3_*` reason) |
| blocked | `BLOCKED` | `⊘` U+2298 | `(/)` | **fill** `$ab-danger-fill` / `$ab-on-fill` | **bold reverse** | bright white on red | `RunBlocked`, `compliance_verdict="blocked"` |
| error | `FAILED` | `✗` U+2717 | `(x)` | **fill** `$ab-danger-fill` / `$ab-on-fill` | **bold reverse** | bright white on red | `RunAborted`, unexpected exception, validation error that stops the run |
| cancelled | `CANCELLED` | `■` U+25A0 | `(#)` | `$ab-muted`, bold | bold | default, bold | Operator cancel before the engine (01 §7.2) |

Glyph choice rules:

- All glyphs are one cell in Rich (`cell_len == 1`). None of them has an
  emoji variant. `⚠` (U+26A0) and `⏵` (U+23F5) were rejected. `⚠` has an
  emoji presentation that some terminals draw two cells wide, which breaks
  column alignment. `⏵` (Miscellaneous Technical, Unicode 6.0) has patchier
  monospace font coverage than the Geometric Shapes and Dingbats glyphs used
  here. Neither risk was reproduced in this headless environment; both are
  avoided by choice.
- `●` `◆` `▲` `◐` `■` are East-Asian-*ambiguous* width, so CJK-locale
  terminals set to "ambiguous = wide" draw them two cells wide. The ASCII set
  covers that case.
- Each glyph is distinct by shape: filled circle, bang, dotted circle,
  triangle-right, question mark, tick, diamond, triangle-up, half circle,
  circle-slash, ballot X, square.

**Reconciliation with 01.** 01 already uses `✓ READY`, `⏵ RUNNING`,
`⚠ DONE`, `✗ WITHHELD`, `✗ FAILED` and `■ CANCELLED`. This table is the
canonical set (01 points here for glyphs). The 01 wireframes should change:
- `⏵` → `▸` (font coverage).
- `⚠` → `▲` (emoji width).
- READY `✓` → `●`, so READY and DONE do not share a glyph.
- WITHHELD `✗` → `◐`, so WITHHELD is distinguishable from FAILED without
  reading the word.

The words and the action-bar layout in 01 are unchanged.

**ASCII mode** is used when `AUTOBENCH_GLYPHS=ascii` is set, when
`sys.stdout.encoding` is not UTF-8, or when `TERM=linux` (the kernel
console). It only swaps glyphs. Words and styles stay the same.

### 2.2 Implementation

```python
# tui/status.py (Phase 2)
@dataclass(frozen=True)
class StatusSpec:
    word: str
    glyph: str
    ascii: str

STATUS: Mapping[str, StatusSpec] = {
    "ready": StatusSpec("READY", "●", "(*)"),
    "notready": StatusSpec("NOT READY", "!", "(!)"),
    "loading": StatusSpec("LOADING", "◌", "(~)"),
    "running": StatusSpec("RUNNING", "▸", "(>)"),
    "awaiting": StatusSpec("WAITING FOR YOU", "?", "(?)"),
    "success": StatusSpec("DONE", "✓", "(+)"),
    "compliant": StatusSpec("COMPLIANT", "◆", "(=)"),
    "warning": StatusSpec("WARNING", "▲", "(^)"),
    "withheld": StatusSpec("WITHHELD", "◐", "(-)"),
    "blocked": StatusSpec("BLOCKED", "⊘", "(/)"),
    "error": StatusSpec("FAILED", "✗", "(x)"),
    "cancelled": StatusSpec("CANCELLED", "■", "(#)"),
}

class StatusBadge(Static):
    """Glyph + WORD. Colour comes only from the -<state> CSS class."""
    state: reactive[str] = reactive("ready")
    detail: reactive[str] = reactive("")          # e.g. "2/4"

    def watch_state(self, state: str) -> None:
        for name in STATUS:
            self.set_class(name == state, f"-{name}")
        self._render_badge()
    # _render_badge(): Content(f"{glyph} {word}{' ' + detail if detail else ''}")
```

The TCSS rules, exactly as prototyped:

```tcss
StatusBadge { width: auto; height: 1; padding: 0 1; text-style: bold; }
StatusBadge.-ready     { color: $ab-success; }
StatusBadge.-notready  { color: $ab-warning; }
StatusBadge.-loading   { color: $ab-info; text-style: italic; }
StatusBadge.-running   { color: $ab-info; }
StatusBadge.-awaiting  { color: $ab-warning; }
StatusBadge.-success   { color: $ab-success; }
StatusBadge.-compliant { color: $ab-success; }
StatusBadge.-warning   { color: $ab-warning; }
StatusBadge.-cancelled { color: $ab-muted; }
/* Outcomes that stop or withhold publication: a filled badge in every mode. */
StatusBadge.-withheld  { background: $ab-warning-fill; color: $ab-on-fill; }
StatusBadge.-blocked   { background: $ab-danger-fill;  color: $ab-on-fill; }
StatusBadge.-error     { background: $ab-danger-fill;  color: $ab-on-fill; }

/* NO_COLOR: Monochrome turns colour into grey luminance, so the meaning is
   carried by glyph + word + text style. */
App:nocolor StatusBadge           { color: $ab-text; background: $ab-surface; }
App:nocolor StatusBadge.-loading  { text-style: italic; }
App:nocolor StatusBadge.-ready,    App:nocolor StatusBadge.-notready,
App:nocolor StatusBadge.-cancelled, App:nocolor StatusBadge.-running,
App:nocolor StatusBadge.-awaiting, App:nocolor StatusBadge.-success,
App:nocolor StatusBadge.-compliant, App:nocolor StatusBadge.-warning { text-style: bold; }
App:nocolor StatusBadge.-withheld, App:nocolor StatusBadge.-blocked,
App:nocolor StatusBadge.-error    { text-style: bold reverse; }
App:nocolor .ab-hint, App:nocolor .ab-code { color: $ab-text; text-style: italic; }
App:nocolor .ab-panel, App:nocolor .ab-list { border-title-color: $ab-text; }

/* textual-ansi: 16 colours, alpha collapses, so use full-strength pairs. */
App:ansi StatusBadge.-withheld { background: ansi_yellow; color: ansi_black; text-style: bold; }
App:ansi StatusBadge.-blocked,
App:ansi StatusBadge.-error    { background: ansi_red; color: ansi_bright_white; text-style: bold; }
```

The same badge is used in the action bar, the status/results column, the step
rail (glyph only there, with the step name as the word), the validation list
(it extends the reverse-video `ERROR`/`WARNING` badge that `f29f85f` added) and
the terminal title (`Autobench — ✓ DONE`).

### 2.3 Verification (prototype screenshots)

| Capture | What it shows | Result |
|---|---|---|
| `png/gallery_dark.png`, `gallery_tokyo.png`, `gallery_light.png` | All 12 badges plus their internal code | Each state reads by glyph, word and colour. Fills stay legible in a light theme (`$text` gives auto-contrast on the fill). |
| `png/gallery_nocolor.png` | `NO_COLOR=1` | All 12 words are readable white or bold. WITHHELD, BLOCKED and FAILED are reverse-video blocks, the most prominent items on screen. Today's `[red]Blocked` is dark grey on dark grey (03 `15_blocked_privacy_denial_120x40_nocolor.png`). **Pass.** |
| `png/gallery_ansi.png`, `gallery_ansi_nocolor.png` | `textual-ansi`, with and without NO_COLOR | 16-colour fills: black on yellow and bright white on red. With NO_COLOR the `NoColor` filter strips colour and reverse still marks the three fills. **Pass.** |
| `png/gallery_ascii_nocolor.png` | ASCII glyphs plus NO_COLOR, the worst case | `(*) READY` … `(#) CANCELLED`. Every state is still distinct. **Pass.** |
| `png/result_nocolor.png`, `result_ansi.png` | Result card for a withheld run (§5.4 copy) | Badge, headline, why, next, `Code:` line and the quarantined log path all readable at 80x24. |
| `png/form_nocolor.png`, `form_ansi.png` | Step form, focus on "Output file name" | The focused field's label is reverse video, so focus is visible with no colour (03 T3). Checked list items read `[x]`. |
| `png/footer_ansi_stock.png` / `footer_ansi_fix.png` | Footer under ANSI | Stock: descriptions invisible. Fixed: readable (§1.5). |

The checks were by eye on the PNGs, plus segment-style dumps for the Footer.
Phase 2 should turn them into `pytest-textual-snapshot`-style SVG snapshot
tests for three modes (default theme, `NO_COLOR=1`, `textual-ansi`), so
regressions show up in CI (03 T6 asked for this).

---

## 3. Checkbox and selection affordance (03 T4)

**Stock options checked first.**

| Option | Result |
|---|---|
| `Checkbox.BUTTON_INNER` (class variable) | One glyph for both states (`X`). It can't tell on from off. |
| `RadioButton` | Same mechanism, `●` in both states |
| `Switch` | The knob position is drawn as a colour block. Under NO_COLOR the two halves are similar greys. |
| `compact=True` | Removes the border but keeps the `▐X▌` glyph |
| `SelectionList` | `render_line` hard-codes `ToggleButton.BUTTON_INNER` for every row (`_selection_list.py:561-563`) |

None of these differ without colour, so two small subclasses are needed
*(verified, `proto_visual.py`)*:

```python
class BoxCheckbox(Checkbox):
    """Draws [x] / [ ] so the state never depends on colour."""

    @property
    def _button(self) -> Content:  # ToggleButton._button, textual 7.5
        fg = Style(foreground=self.get_visual_style("toggle--label").foreground,
                   bold=self.value)
        return Content.assemble(("[", fg), ("x" if self.value else " ", fg), ("]", fg))


class BoxSelectionList(SelectionList):
    """Same [x] / [ ] gutter. Width stays 3 cells, so the gutter width is unchanged."""

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        segments = list(strip)
        if len(segments) < 4:
            return strip
        try:
            option = self.get_option_at_index(self.scroll_offset.y + y)
        except OptionDoesNotExist:
            return strip
        base = segments[3].style or RichStyle()
        mark = RichStyle(bold=True, color=base.color, bgcolor=base.bgcolor,
                         meta=segments[1].style.meta if segments[1].style else None)
        box = "x" if option.value in self._selected else " "
        return Strip([Segment("[", mark), Segment(box, mark), Segment("]", mark), *segments[3:]],
                     strip.cell_length)
```

- **Checked rows also get a bold label** (`Checkbox.-on > .toggle--label { text-style: bold; }`),
  a second cue that doesn't depend on colour.
- **Mouse clicks still work.** The click target is the option `meta`, which
  is copied onto the new segments.
- **Private API.** `_button` and `_selected` are private in Textual 7.5. Pin
  them with a unit test that renders both widgets and asserts that `[x]` and
  `[ ]` are in the output, so a Textual upgrade inside `<8` fails loudly
  rather than silently showing `X` again.
- Use these subclasses for every checkbox and multi-select in the app,
  including attestations (`citi_competitor_receives_output` and the
  merchant-spend declaration). Those are exactly the controls where "is it
  ticked?" has compliance weight.

---

## 4. Typography and density

A terminal has one font size and one weight axis (bold). Hierarchy comes from
case, weight, colour role, position and white space. Everything here is
specified for 80x24 first.

### 4.1 Type roles

| Role | Class | Style | Casing and length | Example |
|---|---|---|---|---|
| Screen or step title | `.ab-title` | bold, `$ab-text` | Sentence case, ≤ 40 chars | `Analysis & mode` |
| Section heading inside a step | `.ab-section` | bold, `$ab-accent`, 1 blank row above | Sentence case, ≤ 30 chars, no numbering (the rail numbers steps) | `Dimensions` |
| Field label | `.ab-label` | `$ab-text` | Sentence case, ≤ 28 chars, noun phrase. Required: trailing ` *`. Optional fields carry no "(optional)" suffix. | `Primary metric *` |
| Hint | `.ab-hint` | `$ab-muted`. NO_COLOR: italic, full text colour. | One line, ≤ 74 chars at 80 cols. Says what the field *does* or its consequence, not how to fill it. | `Leave blank to name the file automatically.` |
| Secondary code | `.ab-code` | italic, `$ab-muted` | Prefixed `Code:` | `Code: control3_numeric_policy_blocked` |
| Path or filename | `.ab-path` | `$ab-text`, no wrap, own line | Full path, never basename-only (03 T9). 01 §3.3 defines wrapping at `/` and `_` in the results view. | `/home/op/outputs/benchmark_share_ACME_….xlsx` |
| Status | `StatusBadge` | §2 | UPPER-CASE word | `◐ WITHHELD` |
| Button | `Button` (compact) | bold when focused, reverse on focus | Verb first, sentence case | `Run share analysis`, `Yes, it is clearing spend` |
| Inline error under a field | `.ab-hint` + `StatusBadge` glyph | `$ab-danger` text, `✗`/`!` glyph | One line: problem + fix | `✗ Not a number. Use a value like 2.0.` |

### 4.2 Spacing rules

| Rule | Value |
|---|---|
| Between label and its field | 0 rows |
| Between fields | 1 row (`.ab-field` bottom margin) |
| Hint | Directly under its field, then the 1-row field gap |
| Before a section heading | 1 row |
| Pane and modal inner padding | `$ab-gutter-pane` = 0 vertical, 1 horizontal |
| Side-by-side fields | Never at <110 columns. At ≥110 only Approved/Fraud may pair (F22, F23). |
| Checkboxes | One per row, never two (F22) |
| Global widget margins | None (removes `Input { margin-bottom: 1 }`, `Select { margin-bottom: 1 }`) |

**Budget at 80x24.** A compact field is 2 rows (label + well), or 3 with a
hint, plus 1 gap. Below 01's header, rail, action bar and footer (5 rows in
total) about 19 rows remain, which holds 5–6 fields per step without
scrolling. Today's 3-row tall inputs plus margins (5 rows per field) fit 4
widgets in total (01 summary). The form prototype (`png/form_*.png`) shows a
title, a hint, two fields, a 4-row list and a checkbox in 19 rows.

### 4.3 Borders: which widgets get one

| Gets a border | Style | Why |
|---|---|---|
| Modal frame | `$ab-border-modal` (thick) `$ab-border-strong` | Separates the dialog from the dimmed backdrop, including under NO_COLOR, where the backdrop dimming is lost |
| Multi-row list (dimensions, secondary metrics, entity results, picker lists, validation issues) | `round $ab-border`. Focus: `heavy $ab-focus`. | The box shows the scroll region's extent. The **shape** change round → heavy shows focus without colour. |
| Status/results panels (column at ≥110, view at <110) | `.ab-panel`: `round $ab-border`, bold `$ab-accent` title | Groups an outcome, a path and its actions |
| Log view | `.ab-panel` | Same |
| **No border** | | |
| Form sections and steps | heading + white space | Saves 2 rows and 4 columns per section. Today four bordered sections cost 8 rows at 80x24. |
| Inputs, Selects, Buttons, Checkboxes | `compact=True` (stock): a 1-row well on `$ab-field` | Density (F26). Focus via §4.4. |
| Action bar, footer, rail | background `$ab-panel-raised` | Always-visible chrome, set apart by background (and position under NO_COLOR) |

### 4.4 Focus treatment

| Widget | Focused looks like | Survives NO_COLOR? |
|---|---|---|
| Input, Select (compact) | Well background `$ab-focus 25%`, bold value. **Plus the field's label in bold reverse video** via `.ab-field:focus-within > .ab-label`. ANSI: `ansi_blue` well with `ansi_bright_white` text. | Yes: the reverse-video label (`png/form_nocolor.png`) |
| Checkbox | Stock compact focus (block-cursor label) | Yes: reverse label |
| List | Border round → heavy, plus the highlighted row | Yes: shape change |
| Button | Bold + reverse | Yes |
| Rail step | Reverse | Yes |

`:focus-within` is only allowed on `.ab-field`, a 2–3 widget container.
Textual restyles the whole subtree of the outermost `:focus-within` ancestor
on every focus change. Scoped this way, Tab latency p50 falls from 104 ms to
11–15 ms (03 §2).

---

## 5. Copy guidelines and glossary

### 5.1 Voice and style

1. **Sentence case** everywhere except the UPPER-CASE badge words. No Title
   Case log prefixes (`Execution Error:` → plain sentence).
2. **Buttons start with a verb and name the act:** `Run share analysis`,
   `Cancel run`, `Yes, it is clearing spend`, `Run with diagnostic consent`.
   Never a bare `Confirm`, `OK` or `Proceed` (03 F11, F12).
3. **One term per concept.** Use these terms:

   | Concept | Term |
   |---|---|
   | Advanced / Advanced Optimization / Export Adv / Advanced Overrides | **Expert settings** |
   | Entity being benchmarked | **Target entity** |
   | The others | **Peer group** |
   | Outputs not released | **Withheld** |
   | Run refused | **Blocked** |
   | Crashed or aborted | **Failed** |
   | Preset posture | **Privacy posture** (`Strict`, `Best effort`, `Accuracy first`) |
   | Release mode | **Release** (`Complete output`, `Verified safe coverage`) |
   | Quarantined log | **Internal run log (do not share)** |

4. **Never show an enum, reason code, widget ID or exception class as primary
   text.** Primary text comes from the label table (§5.2). The code is shown
   once, dimmed, as `Code: <code>`, so operators can quote it to support and
   search the docs.
5. **Unicode ellipsis `…`** for "in progress" and truncation. Never `...`.
6. **Numbers with units and denominators:** `120 of 140 units released (86%)`,
   not `120/140`. Rows are **1-based**, say so (`Rows 4, 17, 31`, with
   `Row numbers count from 1` in the validation dialog hint) (03 F29).
7. **Escape everything dynamic** (paths, column names, exception text) or
   build it as `Content`/`Text` (03 F31).
8. **Errors and outcomes never live only in a toast** (01 §5.3).
9. **Full paths, on their own line.** Never `export_path.name` only (03 T9).

### 5.2 Glossary: internal codes → plain language

The table is data: `LABELS[(kind, code)] -> (primary, detail)`. **Where it
lives:** recommended as a new pure-data module, **`core/labels.py`** (no
imports from the engine), so the CLI can use the same words later (03 F06
asked for a shared `core/` table). Adding a module changes no core behaviour,
but it is a `core/` diff, so it needs owner sign-off. If the owners want zero
`core/` diff in Phase 2, put it in `tui/labels.py` and move it later.

Either way, add an **exhaustiveness test**. It iterates `PrivacyReleaseMode`,
`PrivacyRuleStrategy`, `PrivacySweepStatus`, `ValidationSeverity`, the
`CONTROL3_*` constants in `core/privacy_output_policy.py:31-38`, the verdicts
and run statuses in `core/compliance.py:207-255`, the postures in
`presets/*.yaml`, and the preset names, and fails if any of them has no label.
A new code can then never reach the screen raw. Unknown codes at run time
fall back to `Unrecognised status` with `Code: <raw>`, never to a bare code.

**Compliance verdict** (`summary["compliance_verdict"]`, `core/compliance.py:233-241, 213`; shown today at `tui_app.py:2859, 2873`)

| Code | Badge | Primary text | Detail / next step |
|---|---|---|---|
| `fully_compliant` | `◆ COMPLIANT` | Privacy checks passed | Every published cell meets the peer-count and concentration rules. |
| `violations_detected` | `▲ WARNING` (best_effort, accuracy_first) / `◐ WITHHELD` (strict, when the sink is not authorised) | Some cells break the privacy rules | Strict: nothing was published. Best effort: the report labels those cells non-compliant. Next: remove a dimension or use fewer, larger categories. |
| `not_publishable_input` | `◐ WITHHELD` | The input data isn't fit to publish | Data validation found errors under the Strict posture. Next: fix the rows listed in the validation step and run again. |
| `structural_infeasibility` | `▲ WARNING` | Some categories can't meet the rules with any weighting | Too few peers in some categories. Next: merge or drop those categories. |
| `blocked` | `⊘ BLOCKED` | The run was stopped by a policy check | See the reason below. |

**Run status** (`summary["run_status"]`, `core/compliance.py:226-232, 212`; audit `run_status="withheld"` in `core/privacy_output_policy.py:484`)

| Code | Primary text |
|---|---|
| `compliant` | Completed, compliant |
| `non_compliant` | Completed with privacy violations (Strict posture) |
| `completed_with_warnings` | Completed, some outputs labelled non-compliant |
| `completed_accuracy_first` | Completed as a non-publishable diagnostic |
| `completed` | Completed |
| `blocked` | Blocked |
| `withheld` | Publication withheld |

**Privacy posture** (`compliance_posture`, `presets/*.yaml:3`; today `posture=strict` at `tui_app.py:2859, 2873`, and `accuracy_first` in the consent dialog `:1597`)

| Code | Primary text | Detail |
|---|---|---|
| `strict` | Strict | Nothing is published unless every cell passes. |
| `best_effort` | Best effort | Completes even with violations, and labels them in the report. |
| `accuracy_first` | Accuracy first | Favours accurate numbers over the privacy rules. The report is a non-publishable diagnostic, and every run needs your consent. |

**Consent state** (`acknowledgement_state`, `core/compliance.py:214, 243`; today at `tui_app.py:2859`)

| Code | Primary text |
|---|---|
| `acknowledged` | You consented for this run |
| `not_required` | No consent needed |
| `required_missing` | Consent is required and was not given |

**Withholding reason** (`privacy_decision.withholding_reason`, `core/privacy_output_policy.py:31-38`; today raw in the log at `tui_app.py:2824-2835` and the results card at `:2887`; the toast at `:2911` omits the reason)

| Code | Primary text | What to do next |
|---|---|---|
| `control3_numeric_policy_blocked` | Results were withheld to protect peer privacy: some cells had too few peers, or one peer was too large a share. | Remove a dimension, choose **Verified safe coverage** (share analysis), or pick a preset with tighter weights, then run again. |
| `control3_mandatory_overlay_blocked` | Results were withheld because a mandatory overlay failed (the Citi 25% cap). | Check the Citibank entity name in step 4, or reduce the dimensions where Citibank's share is high. |
| `control3_invalid_privacy_evidence` | Results were withheld because the privacy check couldn't confirm the outputs. | This is a safeguard, not a data problem. Run again; if it repeats, send the internal run log path to support. |
| `control3_safe_coverage_verifier_failed` | Verified safe coverage was withheld: the independent check didn't confirm the safe set. | Run again with Complete output, or contact support with the log path. |
| `control3_safe_coverage_search_incomplete` | Verified safe coverage was withheld: the search for a safe set didn't finish. | Use fewer dimensions, or run with Complete output. |
| `control3_safe_coverage_empty_release` | Verified safe coverage found no units that are safe to publish. | Use fewer or broader dimensions. |

**Blocked reason** (`summary["reason"]`, `core/analysis_run.py:1722`, `core/global_weight_optimizer.py:110`, `core/compliance.py:323`)

| Code or message | Primary text | Next |
|---|---|---|
| `insufficient_peers` | Not enough peers to benchmark safely | Choose a broader peer group (a different entity column) or fewer filters. |
| `optimization_aborted` | The weighting step couldn't find a valid solution | Try a preset with more tolerance, or fewer dimensions. |
| `acknowledgement required` / `"accuracy_first compliance_posture requires explicit acknowledgement…"` (`core/analysis_run.py:1246`) | This preset needs your consent for each run | Run again and choose **Run with diagnostic consent** when asked. 01 §8.2 fixes the path that skipped the dialog (D2). |
| `"Configuration could not be resolved for Control 3 policy evaluation"` (`:1252`) | The settings couldn't be combined into a valid configuration | Reset Expert settings to the preset (palette: *Reset expert settings*) and run again. |

**Run aborted messages** (`RunAborted`, `core/analysis_run.py:1309-1365, 1495, 1958, 1993, 2167-2214`). These are the TUI's own preflight
failures. 01 prevents most of them in the form (VSC hidden for rate analysis,
for example). For the rest, the TUI maps the exception type plus a message
prefix:

| Message starts with | Primary text |
|---|---|
| `privacy_release_mode=verified-safe-coverage is not supported for rate` | Verified safe coverage works for share analysis only. |
| `privacy_release_mode=verified-safe-coverage requires one global weight vector` | Verified safe coverage needs one set of weights for all dimensions. |
| `privacy_release_mode=verified-safe-coverage requires privacy_rule_strategy=` | Verified safe coverage needs the privacy rule sweep. It is switched on automatically. Run again. |
| `verified-safe-coverage requires a non-empty governed peer population` | Verified safe coverage found no peers to work with. |
| `Metric column '…' not found` / `Total column '…' not found` / `Rate column '…' not found` | The column "…" isn't in this CSV. Reload the file or pick another column. |
| `No analysis results generated` | The analysis produced no results. Check that the dimensions have data for the target entity. |
| *(anything else)* | The run stopped: *{core message, escaped}* |

**Release mode, rule strategy and sweep status** (`core/contracts.py:41-75`)

| Code | Primary text |
|---|---|
| `complete-output` | Complete output |
| `verified-safe-coverage` | Verified safe coverage: publishes only units proven safe, and suppresses the rest |
| `select_by_peer_count` | Rule chosen by peer count (standard) |
| `sweep_any_applicable` | Privacy rule sweep: try every rule that applies |
| `numerically_compliant` | Meets the numeric privacy rules |
| `numerically_noncompliant` | Fails the numeric privacy rules |
| `not_subject_to_benchmark_numeric_rules` | Not subject to the numeric rules |
| `invalid_or_incomplete_evidence` | Privacy evidence incomplete |
| `blocked_by_mandatory_overlay` | Blocked by a mandatory overlay |
| `5/25`, `6/30`, `7/35`, `10/40`, `4/35` | Rule *N*/*P*: at least *N* peers, and no peer above *P*% of the total. `4/35` applies only to anonymised, aggregated merchant spend. |

**Modes, presets, output and severities**

| Code | Primary text |
|---|---|
| `share` / `rate` / `privacy-sweep` (`_refresh_run_status` `tui_app.py:1460`, `_run_mode`) | Share analysis / Rate analysis / Privacy rule sweep |
| `analysis` / `publication` / `both` (output format) | Analysis workbook / Publication workbook (client-facing) / Both workbooks |
| `compliance_strict` | Compliance strict · Strict |
| `balanced_default` | Balanced (default) · Best effort |
| `strategic_consistency` | Strategic consistency · Best effort |
| `research_exploratory` | Research, exploratory · Best effort |
| `low_distortion` | Low distortion · Accuracy first, consent each run |
| `minimal_distortion` | Minimal distortion · Accuracy first, consent each run |
| Preset descriptions with `(formerly …)` (`presets/*.yaml:4`) | Strip the `(formerly …)` suffix and any posture jargon when displayed (03 F27). The YAML is unchanged. |
| `ValidationSeverity.ERROR` / `WARNING` / `INFO` | `✗ ERROR` / `▲ WARNING` / `INFO` (these badges already exist since `f29f85f`) |
| `Control 3`, `Control 3.2` (`SUB_TITLE` `:939`, log lines) | Not shown as primary text. The subtitle becomes `Peer benchmark`. "Control 3" may appear in `Code:` and in Help → Privacy terms. |

### 5.3 Error message structure

Every error, block and withheld outcome renders in this order (result card,
inline error or dialog; toasts never carry these):

```
<BADGE>  <What happened: one sentence, past tense, no code>
Why:     <cause in the operator's terms: one sentence>
Next:    <one to three concrete actions, imperative, the most likely first>
Code:    <internal code or exception class>            (dimmed)
Log:     <full path>  [^Y Copy]                         (internal log if quarantined)
```

Rules:

- **One error, one place.** The action bar carries the badge and the
  headline. The result card or inline error carries the full structure. The
  log carries the technical line.
- **Tracebacks never reach the main view** (03 F28). The UI shows
  `✗ FAILED  Something went wrong inside the analysis`, with the exception
  *class* as `Code:` and the log path. The traceback goes to the file log
  only.
- For withheld and blocked outcomes, **"Next" must be one of the actions the
  glossary lists for that code**. Actions that weaken privacy are never
  suggested (for example "switch to accuracy_first to see the numbers").

### 5.4 Rewrites: before → after

Locations refer to `tui_app.py` at `f6f47b6`.

| # | Where | Before | After |
|---|---|---|---|
| 1 | Log `:2859` | `Compliance: posture=strict verdict=violations_detected acknowledgement=not_required` | Results card: `▲ WARNING  Some cells break the privacy rules` / `Posture: Strict · Consent: not needed` / `Code: violations_detected`. Log: `Compliance: Strict posture · verdict violations_detected · consent not required`. |
| 2 | Log `:2832-2835` | `Control 3 privacy denial: all benchmark-bearing outputs withheld (control3_numeric_policy_blocked).` | `◐ WITHHELD  Results were withheld to protect peer privacy.` / `Why: some cells had too few peers, or one peer was too large a share.` / `Next: remove a dimension, or choose Verified safe coverage, then run again.` / `Code: control3_numeric_policy_blocked` (`png/result_*.png`) |
| 3 | Toast `:2911`, title `Publication Withheld` | `Control 3 privacy denial: publication withheld.` | No toast. Action bar: `◐ WITHHELD  privacy rules blocked publication` (01 §5.2). The card has the full text (#2). |
| 4 | Log `:2824-2827` | `… A consented accuracy_first diagnostic report was written; it is NON-PUBLISHABLE.` | `▲ DONE (diagnostic)  A diagnostic report was written. Do not share it: it does not meet the privacy rules.` plus the path on its own line. |
| 5 | Log `:2838`, `:2958` | `Non-publishable run log (do not share): /path` | `Internal run log (do not share):` then the full path on the next line, plus `^Y Copy` |
| 6 | Log + Last Run `:2941-2943` | `Execution Error: 'card_type_input_mode'` + raw traceback; Last Run `[red]'card_type_input_mode'[/red]` | `✗ FAILED  Something went wrong inside the analysis.` / `Why: an unexpected error (KeyError) stopped the run. Your data was not changed.` / `Next: check that the CSV has the columns this preset expects, then run again. If it repeats, send the log to support.` / `Code: KeyError: 'card_type_input_mode'` / `Log: <path>` |
| 7 | `:2931-2933` | `Execution Blocked: <exc>` (+ toast title `Blocked`) | `⊘ BLOCKED  <glossary primary text for the reason>` / `Why:` / `Next:` / `Code: RunBlocked: <reason>`. No toast. |
| 8 | `:2936-2938` | `Execution Error: <exc>` (+ toast title `Failed`) | `✗ FAILED  <mapped RunAborted text (§5.2)>` / `Next:` / `Code: RunAborted`. No toast. |
| 9 | `:2776-2777` | `Initialization Error: {exc}` / `Initialization error: {exc}` | `✗ FAILED  The run couldn't start.` / `Why: {escaped exc}` / `Next: check the CSV path and settings, then run again.` (one casing, one wording) |
| 10 | `:2762-2764` | Toast `Validation failed. Fix the data and retry.` + `Validation error: {exc}` | Inline in the validation step: `✗ FAILED  The data check couldn't finish.` / `Why: {escaped exc}` / `Next: open the CSV in a spreadsheet, check the columns named above, reload.` No toast. |
| 11 | `:2608` | `WARNING: best_effort posture may complete with labeled non-compliant outputs.` (log only, after Run) | Shown **before** the run, under the preset in step 4: `▲ Best effort: the run can finish with some outputs labelled non-compliant.` |
| 12 | Consent dialog `:1597-1601` | `This preset uses the accuracy_first compliance posture: … NON-PUBLISHABLE diagnostic report. Proceed with this run?` / `I understand — proceed` (red, focused) | Title `Consent needed for this run`. Body: `Low distortion uses the Accuracy first posture. It favours accurate numbers over the privacy rules, so the report is a diagnostic you must not share. Consent applies to this run only.` Buttons: `Cancel run` (focused) · `Run with diagnostic consent` (01 §6) |
| 13 | Clearing-spend dialog `ClearingSpendConfirmScreen` `:324-332` | ``Fraud analysis requires Total column `{total_col}` to contain clearing-spend amounts. Continue?`` / `Confirm` | Title `Confirm the fraud basis`. Body: `Fraud rates are measured against the Total column "txn_amt". It must hold clearing-spend amounts.` (literal text, no backticks) Buttons: `Cancel run` (focused) · `Yes, it is clearing spend` |
| 14 | Label `:1025` | `Anonymized aggregated merchant-spend context (enables 4/35)` | Label `Merchant data is anonymised and aggregated`. Hint `Allows the 4/35 rule (at least 4 peers, none above 35%). Declare this run by run.` |
| 15 | Label `:1020` | `Privacy rule sweep mode` | `Try every applicable privacy rule`. Hint `Picks the first rule each cell can pass. Always on with Verified safe coverage.` When locked: `(on: required by Verified safe coverage)` |
| 16 | Hint `:1013-1015` | `Verified safe coverage publishes only verified safe units. Missing units are privacy-suppressed. Coverage is not a maximum claim.` | `Publishes only the units proven safe. Others are suppressed. More units may be safe than shown.` |
| 17 | Labels `:987`, `:991`, `:1169` | `Analyze impact` · `Include calc. metrics (CSV)` · `Fraud in BPS` | `Show how the weighting changed results` · `Add calculated metrics to the balanced CSV` (disabled with `(needs Export balanced CSV)` when off) · `Show fraud in basis points (publication workbook)` |
| 18 | Label `:967` | `Target entity (blank = peer-only)` | Label `Target entity`. Empty-state option `None: peer group only`. |
| 19 | Subtitle `:939` | `Control 3.2 dimensional analysis` | `Peer benchmark` |
| 20 | Toast `_warn_missing_widget` `:1937` | `Advanced widget missing: adv_lp_tolerance` | Not user-facing: log a warning. If an expert value can't be shown: inline `Couldn't show this setting; the preset value is used.` |
| 21 | Toast `:2535` | `Failed export: {e}` | Inline in Expert settings: `✗ Couldn't export the settings file.` / `Why: {escaped e}` / `Next: check that the folder is writable.` / full target path |
| 22 | Toast `:2065` | `Failed to write overrides: {e}` | `✗ Couldn't save Expert settings for this run.` / `Why:` / `Next:` + the full temp path |
| 23 | Toast `:2506` | `Expanding advanced section to ensure values are current` (title `Export Adv`) | Removed (implementation narration). On success: toast `Expert settings exported to <full path>` (01 §5.3). |
| 24 | Label `:1122` | `Values override preset when applied.` | `These values replace the preset's for every run until you reset them.` + `Reset to preset` action |
| 25 | Log `:2551` | `Starting analysis sequence...` | `Run started · share analysis · 14:02:11` |
| 26 | `:2566` | `Target entity values are still loading; wait for the list to finish.` | `! NOT READY  Target entity list is still loading…` (action bar). It clears itself when the list lands. |
| 27 | Toast `_resolve_csv_path` `:1734` + log | `CSV file not found: {path}` (title `Invalid Path`) | Inline under the path: `✗ Not found: {escaped path}. Check the folder, or press ^O to browse.` |
| 28 | Toast `:1818` | `Failed to read CSV: {e}` | Inline: `✗ Can't read this file as CSV: {escaped first line of e}. Check that it is comma-separated text.` |
| 29 | Toast `:1808` | `Loaded 9 columns from demo.csv` (repeated on every Tab-out) | No toast. Meta line: `✓ demo.csv · 9 columns · 70.1 MB` (01 §5.3; the repeat is fixed by the reload guard in 03 §3) |
| 30 | Toast `:1415` | `Saved privacy release mode was unknown or stale; fell back to Complete output.` | `Release reset to Complete output: the saved choice is no longer available.` (warning toast, once) |
| 31 | Startup toast `:1228` | `Ctrl+O browse · Ctrl+R run · Ctrl+A advanced · Ctrl+E export adv · Ctrl+L clear log · F1 preset guide` | Removed. The footer plus F1 Help replace it (01 §4.4). |
| 32 | `_fail_launch` `:2613` | `accuracy_first run cancelled: operator consent was not given.` | `■ CANCELLED  Run cancelled: consent was not given. Nothing was written.` |
| 33 | Validation dialog title `:438` | `Data Validation Results` / `Errors: 2  Warnings: 1` | `Check your data` / `2 errors must be fixed · 1 warning to review` |

### 5.5 Preset help

Generate preset help from the preset YAML (03 F33): name, description
(stripped as in §5.2), the posture label from the glossary, and for
accuracy-first presets, "needs your consent for each run". The hard-coded
Markdown at `tui_app.py:371-402` is removed. That is 01's F1 Help → Presets
tab, with the wording rules above.
