import manifest from "./content/tuiManifest";
import { HAS_VOICEOVER, voiceClip } from "./content/voiceoverManifest";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** Silence before the narration of a scene starts, and after it ends. */
export const VO_LEAD_FRAMES = 9;
export const VO_TAIL_FRAMES = 24;

/** Crossfade between chapters. */
export const TRANSITION_FRAMES = 12;
/** Shorter dissolve between consecutive screenshots of the same TUI session. */
export const TUI_TRANSITION_FRAMES = 10;

type ScenePlan = {
  id: string;
  label: string;
  /**
   * How long the scene runs with no voice track: long enough to read its
   * caption. When a narration clip exists, the read sets the length instead.
   */
  frames: number;
  /**
   * Frames the scene's own animation needs before it is just holding. Acts as
   * the floor when narration is shorter than the build.
   */
  minFrames?: number;
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
  270, 210, 240, 225, 255, 255, 255, 210, 345, 225, 225, 225, 240, 225, 270,
];

const tuiScenes: ScenePlan[] = manifest.steps.map((step, index) => ({
  id: `t${String(index).padStart(2, "0")}`,
  label: step.slug.replace(/_/g, " "),
  frames: TUI_BEAT_FRAMES[index] ?? 210,
  minFrames: 150,
  chapter: "Run · the terminal UI",
  tuiStep: index,
  transitionFrames: TUI_TRANSITION_FRAMES,
  // Two dense terminal screenshots dissolving through each other ghosts badly,
  // and so does a chapter slide dissolving into the terminal. Cut in, cut
  // between steps, cut out.
  hardCutAfter: true,
}));

if (tuiScenes.length !== TUI_BEAT_FRAMES.length) {
  throw new Error(
    `Captured ${tuiScenes.length} TUI steps but timed ${TUI_BEAT_FRAMES.length}. Re-run scripts/capture_tui.py or update TUI_BEAT_FRAMES.`,
  );
}

const PLAN: ScenePlan[] = [
  { id: "s01", label: "Title", frames: 105, minFrames: 105 },
  { id: "s02", label: "Why a peer average is not enough", frames: 300, minFrames: 130, chapter: "What it does" },
  { id: "s03", label: "What balancing changes", frames: 300, minFrames: 120, chapter: "What it does" },
  { id: "s04", label: "Client or market", frames: 285, minFrames: 110, chapter: "What it does" },
  { id: "s05", label: "The run path", frames: 405, minFrames: 110, chapter: "What it does" },
  { id: "s06", label: "First access", frames: 510, minFrames: 150, chapter: "Set up" },
  { id: "s07", label: "Daily workflow", frames: 465, minFrames: 180, chapter: "Set up" },
  { id: "s08", label: "Prepare the CSV", frames: 345, minFrames: 170, chapter: "Prepare" },
  { id: "s09", label: "What breaks a first run", frames: 405, minFrames: 180, chapter: "Prepare" },
  {
    id: "s10",
    label: "Privacy rules at a glance",
    frames: 270,
    minFrames: 185,
    chapter: "Prepare",
    hardCutAfter: true,
  },
  ...tuiScenes,
  { id: "s11", label: "The same run, one command", frames: 240, minFrames: 165, chapter: "Run · the CLI" },
  { id: "s12", label: "Check that it worked", frames: 435, minFrames: 150, chapter: "Verify" },
  { id: "s13", label: "Read the workbook", frames: 255, minFrames: 155, chapter: "Verify" },
  { id: "s14", label: "Which weights were used", frames: 285, minFrames: 145, chapter: "Verify" },
  { id: "s15", label: "Output contracts", frames: 270, minFrames: 140, chapter: "Verify" },
  { id: "s16", label: "Choosing a preset", frames: 285, minFrames: 155, chapter: "Verify" },
  { id: "s17", label: "When it fails", frames: 315, minFrames: 140, chapter: "Verify" },
  { id: "s18", label: "Go deeper", frames: 270, minFrames: 150 },
];

/**
 * With a voice track the scene has to contain its own line; without one it has
 * to be readable. The animation floor applies either way.
 */
const sceneFrames = (scene: ScenePlan): number => {
  const clip = voiceClip(scene.id);
  if (!clip) {
    return scene.frames;
  }
  const spoken = Math.ceil(clip.seconds * FPS) + VO_LEAD_FRAMES + VO_TAIL_FRAMES;
  return Math.max(scene.minFrames ?? 0, spoken);
};

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

const RESOLVED = PLAN.map((scene) => ({ ...scene, frames: sceneFrames(scene) }));

export const SCENES: Scene[] = RESOLVED.map((scene, index) => {
  const isLast = index === RESOLVED.length - 1;
  const overlapsNext = !isLast && !scene.hardCutAfter;
  return {
    ...scene,
    start: RESOLVED.slice(0, index).reduce((sum, prev) => sum + prev.frames, 0),
    sequenceFrames:
      scene.frames + (overlapsNext ? scene.transitionFrames ?? TRANSITION_FRAMES : 0),
  };
});

export const TOTAL_FRAMES = RESOLVED.reduce((sum, scene) => sum + scene.frames, 0);

/**
 * The caption-paced cut, checked to catch accidental edits. With a voice track
 * the length comes from the read, so the constant no longer applies.
 */
export const EXPECTED_TOTAL_FRAMES = 9420;

if (!HAS_VOICEOVER && TOTAL_FRAMES !== EXPECTED_TOTAL_FRAMES) {
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
