export const COLORS = {
  bg: "#0f1519",
  bgDeep: "#090e11",
  panel: "#182026",
  panelSoft: "#141c21",
  edge: "#27343c",
  edgeBright: "#3b4c56",
  text: "#e8ecee",
  textDim: "#a3aeb4",
  textFaint: "#6d7c85",
  accent: "#8fb3d4",
  // Muted like the onboarding page, but saturated enough that a pass and a
  // failure are still distinguishable after video compression.
  good: "#86cb92",
  warn: "#f0907f",
  amber: "#d8b26a",
  grid: "rgba(163, 174, 180, 0.06)",
} as const;

export const SIZES = {
  kicker: 28,
  headline: 96,
  lead: 58,
  body: 42,
  mono: 38,
  monoSmall: 32,
  label: 30,
  micro: 26,
} as const;

/** Content box, leaving room for the narration band along the bottom. */
export const SAFE = {
  top: 84,
  side: 140,
  bottom: 212,
} as const;

export const NARRATION_BAND = {
  top: 916,
  height: 124,
} as const;
