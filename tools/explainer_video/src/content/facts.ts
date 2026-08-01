/**
 * Every string and number the video renders.
 *
 * The teaching order follows `docs/autobench-onboarding.html`; the values are
 * taken from the code that runs, not from prose. Entity labels are the generic
 * `Target` / `P1…P6` of `docs/autobench_demo.csv`. No real institution is named
 * anywhere in the composition.
 */

export const CONFIG_MODEL = "config model v3.0";

/** The onboarding handbook's own headline. */
export const HEADLINE = "Build a benchmark you can explain.";

export const SUBHEAD =
  "From first access to a verified first run, using the demo file.";

/** README already names the control publicly; gated by a composition prop. */
export const CONTROL_REFERENCE = "concentration caps enforce Mastercard Control 3.2";

// ---------------------------------------------------------------------------
// The problem, shown on the demo peer group
// ---------------------------------------------------------------------------

export const DEMO_FILE = "autobench_demo.csv";

/**
 * A concentrated peer group, used to show why a naive peer average is not
 * publishable. Volumes are illustrative; the labels are the demo file's.
 */
type PeerInput = { name: string; volume: number; multiplier: number };

const PEER_INPUTS: PeerInput[] = [
  { name: "P1", volume: 980_000, multiplier: 0.29 },
  { name: "P2", volume: 210_000, multiplier: 1.0 },
  { name: "P3", volume: 150_000, multiplier: 1.0 },
  { name: "P4", volume: 110_000, multiplier: 1.18 },
  { name: "P5", volume: 90_000, multiplier: 1.25 },
  { name: "P6", volume: 66_000, multiplier: 1.4 },
];

export type Peer = PeerInput & {
  adjustedVolume: number;
  baseSharePct: number;
  adjustedSharePct: number;
};

const baseTotal = PEER_INPUTS.reduce((sum, peer) => sum + peer.volume, 0);
const adjustedTotal = PEER_INPUTS.reduce(
  (sum, peer) => sum + peer.volume * peer.multiplier,
  0,
);

export const PEERS: Peer[] = PEER_INPUTS.map((peer) => ({
  ...peer,
  adjustedVolume: peer.volume * peer.multiplier,
  baseSharePct: (peer.volume / baseTotal) * 100,
  adjustedSharePct: ((peer.volume * peer.multiplier) / adjustedTotal) * 100,
}));

export const PEER_COUNT = PEERS.length;

/** Six peers select 6/30, so the cap the demo runs under is 30%. */
export const DEMO_RULE = "6/30";
export const DEMO_CAP_PCT = 30;

export const TOP_PEER = PEERS.reduce((top, peer) =>
  peer.baseSharePct > top.baseSharePct ? peer : top,
);

const worstAdjusted = Math.max(...PEERS.map((peer) => peer.adjustedSharePct));

// The scenes claim a breach before balancing and a pass after it. If the
// numbers ever stop saying that, fail the render instead of teaching a lie.
if (TOP_PEER.baseSharePct <= DEMO_CAP_PCT) {
  throw new Error(
    `Scene 2 needs a cap breach; top peer is ${TOP_PEER.baseSharePct.toFixed(1)}%.`,
  );
}

if (worstAdjusted > DEMO_CAP_PCT) {
  throw new Error(
    `Scene 3 claims the balanced set passes ${DEMO_RULE}; worst share is ${worstAdjusted.toFixed(
      1,
    )}%.`,
  );
}

if (PEER_COUNT !== 6) {
  throw new Error(`The demo file has six peers; the chart shows ${PEER_COUNT}.`);
}

// ---------------------------------------------------------------------------
// Client vs. market
// ---------------------------------------------------------------------------

export const TARGET_MODES = [
  {
    title: "Target set",
    body: "The client is separated from the market. Peers are balanced on their own, and the client is compared against that adjusted benchmark.",
    hint: "over- and under-performance",
  },
  {
    title: "Target blank",
    body: "The whole population is balanced together. You get a market view with no target comparison.",
    hint: "peer-only market view",
  },
];

// ---------------------------------------------------------------------------
// The run path
// ---------------------------------------------------------------------------

export const RUN_PATH = [
  { index: "01", title: "Set up", body: "Connect to the shared runtime." },
  { index: "02", title: "Prepare", body: "Aggregate a clear input contract." },
  { index: "03", title: "Run", body: "Choose only the cuts you need." },
  { index: "04", title: "Verify", body: "Read methods, verdict, and output type." },
];

// ---------------------------------------------------------------------------
// 1 · First access
// ---------------------------------------------------------------------------

export const FIRST_ACCESS_COMMANDS = [
  "/ads_storage/autobench/onboard.sh",
  'export PATH="$HOME/.local/bin:$PATH"',
  "which autobench",
  "which autobench-cli",
];

export const LAUNCHERS = [
  { name: "autobench", note: "the terminal UI" },
  { name: "autobench-cli", note: "the command line" },
];

export const FIRST_ACCESS_WARNING =
  "If onboarding reports the shared runtime is missing or invalid, send the exact error to a Release Operator. Analysts do not run install.sh or pip themselves.";

// ---------------------------------------------------------------------------
// 2 · Daily workflow
// ---------------------------------------------------------------------------

export const DAILY_WORKFLOW = [
  "Extract the data with SQL and land the aggregated CSV in a working directory.",
  "Go to that directory and launch autobench. Outputs are written next to your data.",
  "Configure and run the analysis, then verify the workbook before anything moves on.",
];

export const SESSION_MEMORY = {
  remembers: "preset, output format, ordinary option checkboxes",
  forgets: "CSV and output paths, target entities, per-run compliance declarations",
};

/** Verbatim from `BenchmarkApp.BINDINGS` in tui_app.py. */
export const SHORTCUTS = [
  { key: "Ctrl+O", label: "Open CSV" },
  { key: "Ctrl+R", label: "Run" },
  { key: "F1", label: "Preset Guide" },
  { key: "Ctrl+A", label: "Advanced" },
  { key: "Ctrl+E", label: "Export Adv" },
  { key: "Ctrl+L", label: "Clear Log" },
];

// ---------------------------------------------------------------------------
// 3 · Prepare the CSV
// ---------------------------------------------------------------------------

export const INPUT_CONTRACT = [
  { role: "Entity", meaning: "Target and peer identifier.", column: "issuer_name" },
  { role: "Period key", meaning: "Optional grouping key.", column: "year_month" },
  {
    role: "Base dimensions",
    meaning: "Independent requested cuts.",
    column: "card_type, input_mode",
  },
  {
    role: "Combined dimension",
    meaning: "A precomputed cross-cut; Autobench does not invent it.",
    column: "card_type_input_mode",
  },
  {
    role: "Metrics",
    meaning: "Share volume or rate denominator and numerators.",
    column: "txn_cnt, total, approved, fraud",
  },
];

export const INPUT_CONTRACT_HEADERS = ["Role", "Meaning", "Demo column"];

/** Wrapped to fit beside the input-contract table without clipping. */
export const PREPARE_SQL = [
  "SELECT",
  "  issuer_name, year_month,",
  "  card_type, input_mode,",
  "  CONCAT(card_type, ' + ', input_mode)",
  "    AS card_type_input_mode,",
  "  SUM(txn_cnt)  AS txn_cnt,",
  "  SUM(total)    AS total,",
  "  SUM(approved) AS approved,",
  "  SUM(fraud)    AS fraud",
  "FROM source_table",
  "GROUP BY",
  "  issuer_name, year_month,",
  "  card_type, input_mode;",
];

export const FIRST_FAILURES = [
  {
    rule: "Entity names are case-sensitive.",
    detail: "Target and target are different entities.",
  },
  {
    rule: "Column names are normalized.",
    detail: "Card Type becomes card_type. Refer to them that way.",
  },
  {
    rule: "No nulls in entity or metric columns.",
    detail: "Clean them in SQL, or drop the dimension.",
  },
  {
    rule: "Units must be consistent.",
    detail: "Same currency and the same count definition on every row.",
  },
  {
    rule: "You need at least 5 peers.",
    detail: "Fewer peers means no privacy rule can be satisfied.",
  },
];

export const VALIDATION_WARNING =
  "If validation fails, fix the data. A workbook produced from bad input is not a usable benchmark.";

// ---------------------------------------------------------------------------
// Privacy rules (core/privacy_validator.py, config/privacy_rules.yaml)
// ---------------------------------------------------------------------------

export type PrivacyRule = {
  name: string;
  minPeers: number;
  maxShare: string;
  extra: string;
  conditional?: boolean;
};

export const PRIVACY_RULES: PrivacyRule[] = [
  { name: "5/25", minPeers: 5, maxShare: "25%", extra: "General rule." },
  { name: "6/30", minPeers: 6, maxShare: "30%", extra: "At least 3 participants at ≥7%." },
  { name: "7/35", minPeers: 7, maxShare: "35%", extra: "At least 2 at ≥15%, plus 1 at ≥8%." },
  {
    name: "10/40",
    minPeers: 10,
    maxShare: "40%",
    extra: "At least 2 at ≥20%, plus 1 at ≥10%.",
  },
  {
    name: "4/35",
    minPeers: 4,
    maxShare: "35%",
    extra: "Declared anonymized, aggregated merchant spend.",
    conditional: true,
  },
];

export const PRIVACY_RULE_HEADERS = ["Rule", "Minimum", "Maximum share", "Additional applicability"];

export const RULE_SELECTION_NOTE =
  "The engine reads the peer count and selects the rule. You do not set the cap.";

// ---------------------------------------------------------------------------
// Weighting
// ---------------------------------------------------------------------------

export const WEIGHT_METHODS = [
  { name: "Global-LP", note: "one weight vector across every requested cut" },
  { name: "Per-Dimension-LP", note: "compliant fallback when the global solve is infeasible" },
  { name: "Per-Dimension-Bayesian", note: "fallback when the LP has no solution" },
];

export const WEIGHT_METHODS_NOTE =
  "Weight Methods records which one each cut used. A fallback is a property of the data, not a bug.";

// ---------------------------------------------------------------------------
// The CLI equivalent of the TUI run
// ---------------------------------------------------------------------------

export const CLI_COMMAND = [
  "autobench-cli share \\",
  "  --csv autobench_demo.csv \\",
  "  --entity Target \\",
  "  --metric txn_cnt \\",
  "  --dimensions card_type input_mode card_type_input_mode \\",
  "  --time-col year_month \\",
  "  --preset compliance_strict \\",
  "  --output autobench_demo_share.xlsx",
];

export const RATE_COMMAND_NOTE =
  "The rate subcommand swaps --metric for --total-col plus --approved-col or --fraud-col.";

// ---------------------------------------------------------------------------
// 6 · Check that it worked
// ---------------------------------------------------------------------------

export const SUCCESS_CHECKS = [
  "The CLI exited 0, or the TUI log ends with Analysis completed successfully.",
  "The output file exists in your working directory.",
  "Summary shows Input Validation: pass and Compliance Verdict: fully_compliant.",
  "Weight Methods tells you whether each cut used global or per-dimension weights.",
  "Dimension sheets reconcile with the requested cuts and period keys.",
];

/**
 * The Summary sheet the demo run actually writes, label and value, checked
 * against the workbook produced by the command in `CLI_COMMAND`.
 */
export const SUMMARY_ROWS = [
  { label: "Analysis Type:", value: "SHARE" },
  { label: "Entity:", value: "Target" },
  { label: "Privacy Rule:", value: "6/30 (6 participants, 30% max)" },
  { label: "Compliance Posture:", value: "strict" },
  { label: "Run Status:", value: "compliant" },
  { label: "Input Validation:", value: "pass", good: true },
  { label: "Compliance Verdict:", value: "fully_compliant", good: true },
];

export const WORKBOOK_GUIDE = [
  { sheet: "Summary", meaning: "Run inputs, preset, validation result, and compliance verdict. Check this first." },
  { sheet: "One sheet per dimension", meaning: "Target vs. balanced peers per category. The answer to the business question." },
  { sheet: "Weight Methods", meaning: "Which weighting strategy each cut used." },
  { sheet: "Rank Changes", meaning: "How the reweighting shifted peer ranks: a distortion check." },
  { sheet: "Balanced CSV", meaning: "Balanced metrics for BI tools. Written with --export-balanced-csv." },
  { sheet: "Audit package", meaning: "Workbooks, CSV, audit log, config snapshot, validation summary. Written with --audit-package." },
];

export const WORKBOOK_HEADERS = ["Sheet or file", "What it tells you"];

export const ARTIFACT_HYGIENE =
  "The generated .xlsx, .csv, and benchmark_log_*.txt files are local artifacts. An analysis workbook stays internal even when every numeric check passes.";

// ---------------------------------------------------------------------------
// Output contracts
// ---------------------------------------------------------------------------

export const OUTPUT_CONTRACTS = [
  {
    name: "analysis",
    body: "Internal diagnostic workbook. May contain identities and detailed weights. Never send it to a client.",
  },
  {
    name: "publication",
    body: "A sanitized client-facing candidate, validated after transformation, written only if both stages pass.",
  },
  {
    name: "both",
    body: "Separate analysis and publication artifacts. Only the publication candidate may leave the analysis environment.",
  },
];

// ---------------------------------------------------------------------------
// Preset quick choice
// ---------------------------------------------------------------------------

export const PRESET_CHOICES = [
  { need: "Normal or regulated work", preset: "compliance_strict", note: "Default everywhere.", primary: true },
  { need: "One reusable vector", preset: "strategic_consistency", note: "The only preset that guarantees a single global vector." },
  { need: "Explicit best-effort exploration", preset: "balanced_default", note: "Controlled slack; not the default." },
  { need: "Difficult sparse data", preset: "research_exploratory", note: "More flexible search for diagnosis." },
  { need: "Accuracy-first diagnosis", preset: "low_distortion", note: "Requires explicit consent; warned reports are non-publishable." },
];

export const PRESET_HEADERS = ["Need", "Preset", "Meaning"];

export const PRESET_RULE =
  "Run compliance_strict first. Move to another preset only when strict is infeasible or the deliverable needs one reusable weight vector, and record why.";

// ---------------------------------------------------------------------------
// Troubleshooting
// ---------------------------------------------------------------------------

export const TROUBLESHOOTING = [
  {
    symptom: "autobench: command not found",
    fix: "Add ~/.local/bin to PATH, open a new session, or rerun onboarding.",
  },
  {
    symptom: "No target entities, or “Entity not found”",
    fix: "The target must match the CSV exactly, including case. Pick it from the dropdown.",
  },
  {
    symptom: "“Column not found”",
    fix: "Names are normalized to lowercase with underscores. Load the file and read the headers it lists.",
  },
  {
    symptom: "Balancing keeps failing",
    fix: "Usually the data. Drop the sparsest dimension, clean nulls in SQL, get a simple run to pass first.",
  },
  {
    symptom: "LP infeasibility or high distortion",
    fix: "Some market structures cannot satisfy every constraint. Read Weight Methods and Analyze impact.",
  },
];

export const TROUBLESHOOTING_HEADERS = ["Symptom", "First thing to try"];

// ---------------------------------------------------------------------------
// Go deeper
// ---------------------------------------------------------------------------

export const ONBOARDED_WHEN =
  "You are onboarded when you can run the demo, explain which privacy rule applied, and point to the verdict in Summary.";

export const GO_DEEPER = [
  { path: "docs/autobench-onboarding.html", note: "this handbook, in full" },
  { path: "docs/autobench_demo.csv", note: "the known-good demo file" },
  { path: "README.md", note: "CLI cookbook and output reference" },
  { path: "docs/CORE_TECHNICAL_DOC.md", note: "how the engine works inside" },
];
