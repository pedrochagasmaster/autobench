import manifest from "./tuiManifest";

/**
 * Narration, written to teach rather than to sell. Rendered as on-screen
 * captions while the composition has no recorded voice track; set
 * `showNarration` to false once a real read is dubbed over the video.
 *
 * The walkthrough lines come from `scripts/capture_tui.py`, so the caption and
 * the screenshot beside it can never describe different steps.
 */
const CHAPTER_NARRATION: Record<string, string | null> = {
  s01: null,
  s02: "A peer average is easy to skew. When one participant holds most of a category, the naive benchmark is really that one participant, and the concentration cap makes the comparison unpublishable.",
  s03: "Autobench solves for weights that scale dominant participants down and smaller ones up, only where it is needed, so every requested cut satisfies the rule while the market picture stays as close to reality as the constraints allow.",
  s04: "The Target entity field decides how your client is positioned. Name a target and it is compared against the balanced peers. Leave it blank and you get a market view instead.",
  s05: "Four steps, every time. Set up once, prepare the input, run only the cuts you need, then verify before anything moves on.",
  s06: "On an edge node, run the shared onboarding script once. It validates the Release Operator's runtime and installs two launchers: autobench for the terminal UI, autobench-cli for the command line. Same engine, same results.",
  s07: "Every day it is the same three steps. Extract with SQL, launch from the directory holding the data, then run and verify. The tool remembers safe preferences between sessions, but never your paths or your target: choose those fresh each time.",
  s08: "One row per entity, period, and requested cut. Aggregate before loading. The combined dimension is a column you compute in SQL, because Autobench will not invent a cross-cut for you.",
  s09: "Most first runs fail for one of five reasons, and all of them are in the data. Fix the data rather than disabling validation: a workbook built from bad input is not a benchmark.",
  s10: "The peer count selects the rule. Six peers means the thirty percent cap, and the demo file has six. You never choose the cap, and four thirty-five only applies to a declared anonymized merchant-spend scope.",
  s11: "Once a configuration is settled, this is the same run as one command. That is what you schedule.",
  s12: "Five things must be true before you trust the output. If any is false, go to troubleshooting rather than shipping the workbook.",
  s13: "Open Summary first. It records the preset, the posture, the privacy rule, and the verdict. Then read the dimension sheets, which are the actual answer to the business question.",
  s14: "Weight Methods tells you how each cut was solved. One global vector when the data allows it, a per-dimension fallback when it does not. A fallback is a property of the market structure, not a bug.",
  s15: "Analysis output is internal. Anything leaving the analysis environment has to be generated as publication, which Autobench sanitizes and then validates separately.",
  s16: "Start with compliance strict. Move to another preset only when strict is infeasible or the deliverable needs one reusable weight vector, and write down why.",
  s17: "Almost every first failure is an exact-value mismatch. Read the first concrete error and fix that, rather than loosening the configuration until something passes.",
  s18: "You are onboarded when you can run the demo, say which privacy rule applied, and point at the verdict in Summary.",
};

export const NARRATION: Record<string, string | null> = {
  ...CHAPTER_NARRATION,
  ...Object.fromEntries(
    manifest.steps.map((step, index) => [
      `t${String(index).padStart(2, "0")}`,
      step.caption,
    ]),
  ),
};
