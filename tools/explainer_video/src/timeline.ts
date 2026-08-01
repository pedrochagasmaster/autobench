import manifest from "./content/tuiManifest";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** Crossfade between chapters. */
export const TRANSITION_FRAMES = 12;
/** Shorter dissolve between consecutive screenshots of the same TUI session. */
export const TUI_TRANSITION_FRAMES = 10;

type ScenePlan = {
  id: string;
  label: string;
  frames: number;
  /** Chapter shown in the corner marker. */
  chapter?: string;
  /** Index into the captured TUI manifest, for the walkthrough scenes. */
  tuiStep?: number;
  transitionFrames?: number;
  hardCutAfter?: boolean;
};

/**
 * Time given to each captured TUI screen, in frames: long enough to read the
 * caption that goes with it, and no longer.
 */
const TUI_BEAT_FRAMES = [
  270, 210, 240, 225, 255, 180, 255, 210, 270, 225, 225, 225, 240, 225, 270,
];

const tuiScenes: ScenePlan[] = manifest.steps.map((step, index) => ({
  id: `t${String(index).padStart(2, "0")}`,
  label: step.slug.replace(/_/g, " "),
  frames: TUI_BEAT_FRAMES[index] ?? 210,
  chapter: "Run · the terminal UI",
  tuiStep: index,
  transitionFrames: TUI_TRANSITION_FRAMES,
  // Two dense terminal screenshots dissolving through each other ghosts badly.
  // Inside a single session, cut the way the app itself changes.
  hardCutAfter: index < manifest.steps.length - 1,
}));

if (tuiScenes.length !== TUI_BEAT_FRAMES.length) {
  throw new Error(
    `Captured ${tuiScenes.length} TUI steps but timed ${TUI_BEAT_FRAMES.length}. Re-run scripts/capture_tui.py or update TUI_BEAT_FRAMES.`,
  );
}

const PLAN: ScenePlan[] = [
  { id: "s01", label: "Title", frames: 105 },
  { id: "s02", label: "Why a peer average is not enough", frames: 300, chapter: "What it does" },
  { id: "s03", label: "What balancing changes", frames: 300, chapter: "What it does" },
  { id: "s04", label: "Client or market", frames: 285, chapter: "What it does" },
  { id: "s05", label: "The run path", frames: 225, chapter: "What it does" },
  { id: "s06", label: "First access", frames: 270, chapter: "Set up" },
  { id: "s07", label: "Daily workflow", frames: 300, chapter: "Set up" },
  { id: "s08", label: "Prepare the CSV", frames: 285, chapter: "Prepare" },
  { id: "s09", label: "What breaks a first run", frames: 240, chapter: "Prepare" },
  { id: "s10", label: "Privacy rules at a glance", frames: 270, chapter: "Prepare" },
  ...tuiScenes,
  { id: "s11", label: "The same run, one command", frames: 240, chapter: "Run · the CLI" },
  { id: "s12", label: "Check that it worked", frames: 210, chapter: "Verify" },
  { id: "s13", label: "Read the workbook", frames: 255, chapter: "Verify" },
  { id: "s14", label: "Which weights were used", frames: 285, chapter: "Verify" },
  { id: "s15", label: "Output contracts", frames: 270, chapter: "Verify" },
  { id: "s16", label: "Choosing a preset", frames: 285, chapter: "Verify" },
  { id: "s17", label: "When it fails", frames: 255, chapter: "Verify" },
  { id: "s18", label: "Go deeper", frames: 270 },
];

export type Scene = ScenePlan & {
  /** Position on the finished timeline. */
  start: number;
  /**
   * Length inside the TransitionSeries. Scenes followed by a crossfade are
   * extended by the transition length, because the transition consumes frames
   * from both neighbours.
   */
  sequenceFrames: number;
};

export const SCENES: Scene[] = PLAN.map((scene, index) => {
  const isLast = index === PLAN.length - 1;
  const overlapsNext = !isLast && !scene.hardCutAfter;
  return {
    ...scene,
    start: PLAN.slice(0, index).reduce((sum, prev) => sum + prev.frames, 0),
    sequenceFrames:
      scene.frames + (overlapsNext ? scene.transitionFrames ?? TRANSITION_FRAMES : 0),
  };
});

export const TOTAL_FRAMES = PLAN.reduce((sum, scene) => sum + scene.frames, 0);

/** Update deliberately; the check exists to catch accidental drift. */
export const EXPECTED_TOTAL_FRAMES = 8175;

if (TOTAL_FRAMES !== EXPECTED_TOTAL_FRAMES) {
  throw new Error(
    `Scene plan sums to ${TOTAL_FRAMES} frames, expected ${EXPECTED_TOTAL_FRAMES}.`,
  );
}

export const sceneById = (id: string): Scene => {
  const scene = SCENES.find((candidate) => candidate.id === id);
  if (!scene) {
    throw new Error(`Unknown scene id: ${id}`);
  }
  return scene;
};

/** Converts a frame quoted against the finished timeline to scene-local. */
export const localFrame = (sceneId: string, absoluteFrame: number): number =>
  absoluteFrame - sceneById(sceneId).start;
