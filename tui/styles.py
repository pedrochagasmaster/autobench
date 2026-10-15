"""Autobench TUI stylesheet: design tokens plus every component rule.

TUI redesign 02 §1. Textual 7.5 TCSS variables are FILE-SCOPED: a
``$variable`` declared in one stylesheet source is not visible from another
``CSS_PATH`` file, a ``Screen.CSS`` string or a ``DEFAULT_CSS`` block. So the
token block and every app rule live in this one string, which
``BenchmarkApp.CSS`` loads. Screens and modals carry no CSS of their own.

This is a Python module rather than the ``tui/styles/autobench.tcss`` file in
02 §1.3, so it reaches edge nodes through the existing ``*.py`` runtime globs
and needs no package-data entry (02 §1.3 "Fallback").

Colour tokens alias Textual theme variables, so every theme (including
``textual-ansi``) re-resolves them. No literal colours remain except the
16-colour names inside ``App:ansi`` overrides. Meaning never depends on
colour: ``App:nocolor`` rules carry it with glyph + word + bold/reverse.
"""

from __future__ import annotations

TOKENS = """
/* ── Colour roles ─────────────────────────────────────────────────────── */
$ab-surface:        $background;      /* app canvas                        */
$ab-panel:          $surface;         /* cards, modals, status column      */
$ab-panel-raised:   $panel;           /* key bar                           */
$ab-field:          $boost;           /* input/select well                 */
$ab-border:         $primary 40%;     /* idle panel border                 */
$ab-border-strong:  $primary;         /* emphasised panel, modal frame     */
$ab-focus:          $accent;          /* focus ring and focus well         */
$ab-text:           $foreground;
$ab-muted:          $text-muted;      /* hints, secondary codes            */
$ab-accent:         $text-accent;     /* headings                          */
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
$ab-modal-lg: 110;         /* CSV picker: two panes and full paths         */
$ab-results-column: 42;    /* status/results column at 110+ columns (01)  */
$ab-list-rows: 6;
$ab-toast-width: 40;
$ab-label-column: 18;      /* label column of a compact field row (01 §3.2) */       /* toasts, top right (01 §5.3)                 */
"""

COMPONENTS = """
/* ═══ Base ═══════════════════════════════════════════════════════════════ */
Screen { background: $ab-surface; }
ModalScreen { background: $ab-backdrop; align: center middle; }
.hidden { display: none; }

/* ═══ Typography roles (02 §4.1) ═════════════════════════════════════════ */
.ab-title    { text-style: bold; color: $ab-text; }
.ab-section  { text-style: bold; color: $ab-accent; margin: $ab-space-1 0 0 0; }
.ab-label    { color: $ab-text; }
.ab-hint     { color: $ab-muted; }
.ab-code     { color: $ab-muted; text-style: italic; }
.ab-path     { color: $ab-text; }

/* ═══ Panels (02 §4.3: borders frame content only) ═══════════════════════ */
.ab-panel {
    border: $ab-border-panel $ab-border;
    border-title-color: $ab-accent;
    border-title-style: bold;
    background: $ab-panel;
    padding: $ab-gutter-pane;
    height: auto;
}
.ab-modal {
    border: $ab-border-modal $ab-border-strong;
    background: $ab-panel;
    padding: $ab-gutter-pane;
    max-width: 100%;
}

/* Multi-row lists: the border SHAPE changes on focus (round -> heavy). */
.ab-list {
    height: $ab-list-rows;
    border: $ab-border-panel $ab-border;
    background: $ab-panel;
}
.ab-list:focus { border: $ab-border-focus $ab-focus; }

/* ═══ Status language (02 §2) ════════════════════════════════════════════ */
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

/* ═══ Key bar (03 §2, replaces the stock Footer) ═════════════════════════ */
KeyBar { background: $ab-panel-raised; color: $ab-text; }
KeyBar > .keybar--key   { color: $ab-accent; text-style: bold; }
KeyBar > .keybar--label { color: $ab-text; }

/* ═══ Fields (02 §4.2: compact wells, no global widget margins) ══════════ */
Input.-textual-compact, Select.-textual-compact > SelectCurrent {
    background: $ab-field;
    padding: $ab-gutter-field;
}
Input.-textual-compact:focus, Select.-textual-compact:focus > SelectCurrent {
    background: $ab-focus 25%;
    text-style: bold;
}
/* Focus marker that survives NO_COLOR: the focused pair's label turns
   reverse-video. BenchmarkApp._mark_field_pair sets -pair-focus on focus and
   blur; no :focus-within, which restyles a whole subtree on every Tab (03 §2). */
.field-pair > .field-label.-pair-focus { text-style: bold reverse; }

BoxCheckbox.-on > .toggle--label { text-style: bold; }
Button.-textual-compact { min-width: 10; }

/* ═══ Layout shell (01 §3.1): rail · step body | results · action bar ═══ */
#app_body { height: 1fr; }

StepRail { background: $ab-panel-raised; color: $ab-text; padding: 0 1; }
StepRail > .rail--current   { text-style: bold reverse; }
StepRail > .rail--done      { color: $ab-success; }
StepRail > .rail--attention { color: $ab-warning; text-style: bold; }
StepRail > .rail--restored  { color: $ab-info; }
StepRail > .rail--pending   { color: $ab-muted; }

#setup_pane { width: 1fr; height: 1fr; }
.step {
    height: 1fr;
    padding: $ab-gutter-pane;
    scrollbar-gutter: stable;
}
.step-title { text-style: bold; color: $ab-accent; }
/* Toasts (01 §5.3): top right below the header and rail, 40 columns, at
   most two. When the focused field is up there they move to just above the
   action bar (ToastRack.-bottom, set by BenchmarkApp._place_toasts), so
   they never cover the focused field, the rail or the action bar. Modals
   never show toasts: they wait until the modal closes. */
ToastRack { dock: top; align: right top; margin: 2 0 0 0; }
ToastRack.-bottom { dock: bottom; align: right bottom; margin: 0 0 2 0; }
Toast { width: $ab-toast-width; max-width: 50%; margin: 0 0 $ab-space-1 0; }

/* Step contents (PR 5): compact rows, a label column then the field
   (01 §3.2). Hints sit under the field, indented to its column. */
.field-block { height: auto; }
.field-row { layout: horizontal; height: auto; }
.field-row > .field-label { width: $ab-label-column; margin: 0; }
.field-row > Select, .field-row > Input, .field-row > EntityChooser,
.field-row > ModeSwitch, .field-row > Static, .field-row > Checkbox { width: 1fr; }
.field-hint-indented { padding: 0 0 0 $ab-label-column; }
.dims-block { margin: $ab-space-1 0 0 0; }
.step-title { margin: 0 0 $ab-space-1 0; }
#csv_meta { padding: 0 0 0 11; }
/* Step contents (PR 5): groups size to their content. */
.mode-fields, .nested-option, #more_options_form, #review_buttons, #expert_row,
#section_data, #section_entity, #section_mode, #section_privacy { height: auto; }
.nested-option { padding: 0 0 0 4; }
#more_options { margin: $ab-space-1 0 0 0; padding: 0; border: none; background: $ab-surface; }
#more_options > CollapsibleTitle { padding: 0; }
#more_options > Contents { padding: 0 0 0 2; }
#more_options_form .field-label { margin: 0; }
#expert_row { margin: $ab-space-1 0 0 0; }
#expert_row > Static { width: 1fr; padding: 0 1; }
#launch_folder { margin: $ab-space-1 0 0 0; }
ModeSwitch { height: 1; }
ModeSwitch:focus { background: $ab-focus 25%; }
#review_status { height: auto; margin: $ab-space-1 0 0 0; }
#review_blockers { height: auto; max-height: 8; border: none; background: $ab-surface; }
#review_blockers:focus { background: $ab-field; }
#review_blockers_hint { margin: 0 0 $ab-space-1 0; }
#review_summary { height: auto; margin: 0 0 $ab-space-1 0; }
#review_buttons > Button { margin: 0 $ab-space-2 0 0; }

/* A run locks the form (01 §5.2); this line says why. */
#form_lock_note { height: auto; padding: 0 1; text-style: bold; color: $ab-info; background: $ab-panel; }

/* Run log view: the log takes the whole body at any width (Show run log). */
#btn_show_log { margin: 0 0 $ab-space-1 0; }
#btn_show_log { width: auto; }

/* The status/results pane: a right-hand column at 110+ columns, a full-width
   view toggled by ^T below that (it then replaces the step body). */
#activity_pane {
    display: none;
    padding: $ab-gutter-pane;
    overflow-y: auto;
}
Screen.-wide #activity_pane { display: block; width: $ab-results-column; }
Screen.-narrow.-show-results #activity_pane { display: block; width: 1fr; }
Screen.-narrow.-show-results #setup_pane { display: none; }
/* Below 110 columns an outcome card replaces the idle status panel, so the
   verdict, the report path and Copy fit at 80x24 (heuristic T1). */
Screen.-narrow.-has-outcome #run_status { display: none; }
/* Run log view (PR 5): the log takes the whole body at any width. */
Screen.-show-log #setup_pane { display: none; }
Screen.-wide.-show-log #activity_pane,
Screen.-narrow.-show-log #activity_pane { display: block; width: 1fr; }
Screen.-show-log #run_status, Screen.-show-log #last_run { display: none; }

ActionBar { height: 1; background: $ab-panel-raised; }
ActionBar #action_badge { width: auto; }
ActionBar #action_message {
    width: 1fr;
    height: 1;
    text-wrap: nowrap;
    text-overflow: ellipsis;
    color: $ab-text;
}
ActionBar #action_key { width: auto; height: 1; padding: 0 1; text-style: bold; color: $ab-accent; }
ActionBar #action_key.-dim { color: $ab-muted; text-style: none; }
.form-section {
    height: auto;
    padding: $ab-space-0;
    margin: 0 0 $ab-space-1 0;
}
.section-title { text-style: bold; color: $ab-text; margin: 0 0 $ab-space-1 0; }
.subsection-title { color: $ab-muted; text-style: italic; margin: $ab-space-1 0 0 0; }
.field-label { color: $ab-text; margin: $ab-space-1 0 0 0; }
.field-hint, #csv_meta { color: $ab-muted; }
/* Inline error under a field (02 §4.1): danger text; the ✗ glyph carries it
   under NO_COLOR. */
.field-hint.-error { color: $ab-danger; }
.field-pair { height: auto; }

/* Fields stack one per row below 110 columns (02 §4.2). Rows that really
   are side by side (a field and its button) use .ab-row. */
.input-group, .split-inputs { layout: vertical; height: auto; }
.ab-row { layout: horizontal; height: auto; }
.ab-row > Input, .ab-row > Select { width: 1fr; }
.ab-row > Button { margin: 0 $ab-space-1 0 0; }
.ab-checks { layout: vertical; height: auto; margin: $ab-space-1 0 0 0; }

#btn_run { width: 100%; margin: $ab-space-1 0; }
TabbedContent { height: auto; }

.multi-select {
    height: $ab-list-rows;
    border: $ab-border-panel $ab-border;
    background: $ab-panel;
}
.multi-select:focus { border: $ab-border-focus $ab-focus; }

/* Large-entity filter picker (03 §6): replaces the Select above 2,000
   values. #entity_matches is an .ab-list (round -> heavy on focus). */
#entity_picker { height: auto; }
#entity_matches { height: $ab-list-rows; }

/* Advanced settings collapsible: no decorative border. The compliance
   declarations are an always-open titled panel on step 4. Warning colour is
   reserved for warnings (02 §1.4). */
#compliance_declarations, #advanced_opt { margin: 0 0 $ab-space-1 0; }
#compliance_form, #advanced_form { height: auto; }
.adv-group-title { text-style: bold; color: $ab-accent; margin: $ab-space-1 0 0 0; }
.adv-field-label { color: $ab-text; }

#run_status { margin: 0 0 $ab-space-1 0; }
#last_run { margin: 0 0 $ab-space-1 0; }
#results_badges { height: auto; }
#results_panel { height: auto; }
#results_copy { height: auto; }
#results_path { height: auto; }
#btn_copy_path { margin: $ab-space-1 0 0 0; }
#log_output { height: 1fr; min-height: 6; }

/* ═══ Modals: one frame rule, no per-screen CSS (02 §1.1) ═══════════════ */
#validation_container {
    /* A reading surface: as wide as the screen allows, up to the large size. */
    width: 90%;
    max-width: $ab-modal-lg;
    /* Sized so the list keeps several rows and both buttons stay visible at 80x24. */
    height: 90%;
    max-height: 36;
}
#validation_title { text-style: bold; width: 100%; text-align: center; }
#validation_counts { color: $ab-text; }
#validation_hint { width: 100%; color: $ab-muted; }
#issue_list { height: 1fr; min-height: 3; }
/* Rows size to their content; a 1fr child would swallow the whole list. */
#issue_list > .issue-item {
    height: auto;
    padding: $ab-gutter-pane;
    border-bottom: solid $ab-border;
}
#issue_list .issue-text { height: auto; width: 1fr; }
#validation_buttons { layout: horizontal; height: auto; margin: $ab-space-1 0 0 0; }
#validation_buttons Button { margin: 0 $ab-space-2 0 0; }
.issue-error { color: $ab-danger; text-style: bold; }
.issue-warning { color: $ab-warning; }

#picker_container { width: $ab-modal-lg; height: 80%; }
#picker_title { text-style: bold; text-align: center; width: 100%; }
#picker_filter { margin: 0 0 $ab-space-1 0; }
#picker_body { height: 1fr; }
#picker_quick { width: 40%; margin: 0 $ab-space-1 0 0; }
#picker_tree_pane { width: 1fr; }
.picker-subtitle { text-style: bold; color: $ab-accent; }
.picker-hint { color: $ab-muted; }
#picker_quick_list, #picker_browse_list { height: 1fr; }
#btn_picker_cancel { width: 100%; }

#confirm_container { width: $ab-modal-sm; height: auto; }
#confirm_message { width: 100%; margin: 0 0 $ab-space-1 0; }
#confirm_buttons { height: auto; align-horizontal: center; }
#confirm_buttons Button { margin: 0 $ab-space-2 0 0; }

#help_container { width: $ab-modal-md; height: 80%; }

/* Expert settings (F8): a full screen over the main screen. */
#expert_container { width: 100%; height: 100%; border: none; }
#expert_header { height: auto; }
#expert_hint { height: auto; }
#expert_buttons { height: auto; margin: $ab-space-1 0 0 0; }
#expert_buttons > Button { margin: 0 $ab-space-2 0 0; }
#expert_export_path { height: auto; }
#expert_body { height: 1fr; }
.expert-grid { grid-size: 3; grid-columns: 34 16 1fr; grid-rows: 1; height: auto; }
.expert-label { width: 1fr; }
.expert-grid > Input, .expert-grid > Checkbox { width: 1fr; }
.expert-source { width: 1fr; padding: 0 0 0 2; color: $ab-muted; }
#help_text { height: 1fr; margin: $ab-space-1 0; overflow-y: auto; }
#btn_close_help { width: 100%; dock: bottom; }

/* ═══ NO_COLOR (Monochrome filter): glyph + word + text style only ═══════ */
App:nocolor StatusBadge           { color: $ab-text; background: $ab-surface; }
App:nocolor StatusBadge.-loading  { text-style: italic; }
App:nocolor StatusBadge.-ready,
App:nocolor StatusBadge.-notready,
App:nocolor StatusBadge.-cancelled,
App:nocolor StatusBadge.-running,
App:nocolor StatusBadge.-awaiting,
App:nocolor StatusBadge.-success,
App:nocolor StatusBadge.-compliant,
App:nocolor StatusBadge.-warning  { text-style: bold; }
App:nocolor StatusBadge.-withheld,
App:nocolor StatusBadge.-blocked,
App:nocolor StatusBadge.-error    { text-style: bold reverse; }
App:nocolor .ab-hint, App:nocolor .ab-code,
App:nocolor .field-hint, App:nocolor #csv_meta,
App:nocolor .subsection-title, App:nocolor #validation_hint,
App:nocolor .expert-source { color: $ab-text; text-style: italic; }
App:nocolor ModeSwitch:focus { text-style: bold reverse; }
App:nocolor #review_blockers:focus > .option-list--option-highlighted { text-style: bold reverse; }
App:nocolor .ab-panel, App:nocolor .ab-list, App:nocolor .multi-select { border-title-color: $ab-text; }
App:nocolor KeyBar > .keybar--key { color: $ab-text; text-style: bold reverse; }
App:nocolor StepRail > .rail--done,
App:nocolor StepRail > .rail--restored,
App:nocolor StepRail > .rail--pending { color: $ab-text; }
App:nocolor StepRail > .rail--attention { color: $ab-text; text-style: bold; }
App:nocolor ActionBar #action_key { color: $ab-text; text-style: bold reverse; }
App:nocolor ActionBar #action_key.-dim { text-style: none; }
App:nocolor Input:focus, App:nocolor Select:focus > SelectCurrent { text-style: bold reverse; }
App:nocolor Checkbox:focus > .toggle--label { text-style: bold reverse; }
App:nocolor Button:focus { text-style: bold reverse; }
App:nocolor CollapsibleTitle:focus { text-style: bold reverse; }
App:nocolor Tab.-active { text-style: bold reverse; }
App:nocolor ListView:focus > ListItem.-highlight { text-style: bold reverse; }
App:nocolor .multi-select:focus > .option-list--option-highlighted,
App:nocolor .ab-list:focus > .option-list--option-highlighted,
App:nocolor #issue_list:focus > .issue-item.-highlight { text-style: bold reverse; }
App:nocolor .issue-error, App:nocolor .issue-warning { color: $ab-text; }
App:nocolor .field-hint.-error { color: $ab-text; text-style: bold; }

/* ═══ textual-ansi: 16 colours, alpha collapses; full-strength pairs ═════ */
App:ansi StatusBadge.-withheld { background: ansi_yellow; color: ansi_black; text-style: bold; }
App:ansi StatusBadge.-blocked,
App:ansi StatusBadge.-error    { background: ansi_red; color: ansi_bright_white; text-style: bold; }
App:ansi Input:focus,
App:ansi Select:focus > SelectCurrent { background: ansi_blue; color: ansi_bright_white; }
App:ansi KeyBar { background: ansi_black; color: ansi_bright_white; }
App:ansi KeyBar > .keybar--key { color: ansi_bright_cyan; text-style: bold; }
App:ansi KeyBar > .keybar--label { color: ansi_bright_white; }
App:ansi StepRail, App:ansi ActionBar { background: ansi_black; color: ansi_bright_white; }

/* Stock Footer under textual-ansi resolves descriptions to #000000 on
   #000000 in Textual 7.5 (02 §1.5). The app uses KeyBar, but any screen that
   still mounts a Footer gets a readable pair. */
App:ansi Footer, App:ansi Footer FooterKey { background: ansi_black; }
App:ansi Footer FooterKey .footer-key--key { background: ansi_black; color: ansi_bright_cyan; text-style: bold; }
App:ansi Footer FooterKey .footer-key--description { background: ansi_black; color: ansi_bright_white; }
App:nocolor Footer FooterKey .footer-key--key { text-style: bold reverse; }
"""

AUTOBENCH_TCSS = TOKENS + COMPONENTS
"""The one stylesheet for ``BenchmarkApp.CSS``."""
