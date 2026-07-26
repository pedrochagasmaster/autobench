export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** Crossfade length between scenes, per the script. */
export const TRANSITION_FRAMES = 12;

export const EXPECTED_TOTAL_FRAMES = 3390;

type ScenePlan = {
  id: string;
  label: string;
  frames: number;
  /** Scene 6 cuts straight into scene 7 with no crossfade. */
  hardCutAfter?: boolean;
};

const PLAN: ScenePlan[] = [
  { id: "s01", label: "One peer is the benchmark", frames: 180 },
  { id: "s02", label: "Title", frames: 105 },
  { id: "s03", label: "What it actually computes", frames: 330 },
  { id: "s04", label: "The rule picks itself", frames: 390 },
  { id: "s05", label: "How the weights are solved", frames: 420 },
  { id: "s06", label: "Share or rate", frames: 270, hardCutAfter: true },
  { id: "s07", label: "What lands on disk", frames: 390 },
  { id: "s08", label: "Before and after", frames: 360 },
  { id: "s09", label: "Presets and big inputs", frames: 240 },
  { id: "s10", label: "Three ways in, one engine", frames: 330 },
  { id: "s11", label: "Getting started", frames: 240 },
  { id: "s12", label: "Outro", frames: 135 },
];

export type Scene = ScenePlan & {
  /** Position on the finished timeline, which the script quotes absolutely. */
  start: number;
  /**
   * Sequence length inside the TransitionSeries. Scenes followed by a
   * crossfade are extended by the transition length, because the transition
   * consumes frames from both neighbours.
   */
  sequenceFrames: number;
};

export const SCENES: Scene[] = PLAN.map((scene, index) => {
  const isLast = index === PLAN.length - 1;
  const overlapsNext = !isLast && !scene.hardCutAfter;
  return {
    ...scene,
    start: PLAN.slice(0, index).reduce((sum, prev) => sum + prev.frames, 0),
    sequenceFrames: scene.frames + (overlapsNext ? TRANSITION_FRAMES : 0),
  };
});

export const TOTAL_FRAMES = PLAN.reduce((sum, scene) => sum + scene.frames, 0);

if (TOTAL_FRAMES !== EXPECTED_TOTAL_FRAMES) {
  throw new Error(
    `Scene plan sums to ${TOTAL_FRAMES} frames, expected ${EXPECTED_TOTAL_FRAMES}.`,
  );
}

export const sceneStart = (id: string): number => {
  const scene = SCENES.find((candidate) => candidate.id === id);
  if (!scene) {
    throw new Error(`Unknown scene id: ${id}`);
  }
  return scene.start;
};

/** Converts a frame number quoted against the finished timeline to scene-local. */
export const localFrame = (sceneId: string, absoluteFrame: number): number =>
  absoluteFrame - sceneStart(sceneId);
