import manifest from "./tuiManifest";

/**
 * Narration, written to teach rather than to sell, and kept short enough to be
 * read on screen at the pace the scene holds for. Rendered as captions while
 * the composition has no recorded voice track; set `showNarration` to false
 * once a real read is dubbed over the video.
 *
 * The walkthrough lines come from `scripts/capture_tui.py`, so the caption and
 * the screenshot beside it can never describe different steps.
 */
const CHAPTER_NARRATION: Record<string, string | null> = {
  s01: null,
  s02: "One participant holds most of this category. A naive peer average is really just that participant, and the concentration cap makes it unpublishable.",
  s03: "Autobench solves for weights that scale dominant peers down and smaller ones up, only where needed, so every requested cut clears the cap.",
  s04: "Name a target and it is compared against the balanced peers. Leave it blank and you get a market view instead.",
  s05: "Four steps, every time: set up once, prepare the input, run only the cuts you need, then verify.",
  s06: "Run the shared onboarding script once. It installs two launchers: autobench for the terminal UI, autobench-cli for the command line.",
  s07: "The same three steps every day. The tool remembers safe preferences, but never your paths or your target: choose those fresh each session.",
  s08: "One row per entity, period, and requested cut. Aggregate before loading. The combined dimension is a column you compute in SQL.",
  s09: "Most first runs fail on the data, not the tool. Fix the data rather than disabling validation.",
  s10: "The peer count selects the rule. Six peers means the thirty percent cap. You never choose the cap yourself.",
  s11: "Once the configuration is settled, the same run is one command. That is what you schedule.",
  s12: "Five things must be true before you trust the output. If any is false, go to troubleshooting.",
  s13: "Open Summary first: preset, posture, privacy rule, verdict. Then read the dimension sheets, which answer the business question.",
  s14: "Weight Methods records how each cut was solved. A per-dimension fallback is a property of the market structure, not a bug.",
  s15: "Analysis output is internal. Anything leaving the environment must be generated as publication, which is sanitized and validated separately.",
  s16: "Start with compliance strict. Change preset only when strict is infeasible or the deliverable needs one reusable vector, and record why.",
  s17: "Almost every first failure is an exact-value mismatch. Fix the first concrete error rather than loosening the configuration.",
  s18: "You are onboarded when you can run the demo, name the privacy rule that applied, and point at the verdict.",
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
