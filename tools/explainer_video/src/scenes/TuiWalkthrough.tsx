import { interpolate, useCurrentFrame } from "remotion";
import { TuiShot } from "../components/TuiShot";
import manifest from "../content/tuiManifest";
import { MONO } from "../fonts";
import { COLORS, SIZES } from "../theme";
import { SCENES } from "../timeline";

// Matches the captured terminal's aspect, so a fully zoomed-out shot fills the
// frame exactly instead of floating inside a wider box.
const SHOT_HEIGHT = 790;
const SHOT_WIDTH = Math.round((SHOT_HEIGHT * manifest.width) / manifest.height);

/**
 * How far each captured screen is pushed in. 1 shows the whole terminal, which
 * is what the first shot needs; the rest push in so the widget under discussion
 * is readable at 1080p.
 */
const ZOOM: Record<string, { zoom: number; drift?: number }> = {
  launch: { zoom: 0.97, drift: 0.03 },
  browse: { zoom: 1.1, drift: 0.04 },
  loaded: { zoom: 1.35, drift: 0.05 },
  entity_column: { zoom: 1.7, drift: 0.06 },
  target: { zoom: 1.7, drift: 0.06 },
  time_column: { zoom: 1.7, drift: 0.05 },
  preset: { zoom: 1.6, drift: 0.06 },
  preset_guide: { zoom: 1.12, drift: 0.05 },
  options: { zoom: 1.55, drift: 0.05 },
  metric: { zoom: 1.45, drift: 0.06 },
  dimensions: { zoom: 1.4, drift: 0.06 },
  rate_tab: { zoom: 1.4, drift: 0.05 },
  running: { zoom: 1.3, drift: 0.05 },
  log_tail: { zoom: 1.25, drift: 0.05 },
  done: { zoom: 1.3, drift: 0.05 },
};

const stepCounter = (index: number): string =>
  `${String(index + 1).padStart(2, "0")} / ${String(manifest.steps.length).padStart(2, "0")}`;

export const TuiWalkthrough: React.FC<{ sceneId: string }> = ({ sceneId }) => {
  const frame = useCurrentFrame();
  const scene = SCENES.find((candidate) => candidate.id === sceneId);
  if (!scene || scene.tuiStep === undefined) {
    throw new Error(`Scene ${sceneId} is not a TUI walkthrough scene`);
  }
  const step = manifest.steps[scene.tuiStep];
  const framing = ZOOM[step.slug] ?? { zoom: 1.4, drift: 0.05 };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        paddingTop: 60,
        gap: 22,
      }}
    >
      <div
        style={{
          width: SHOT_WIDTH,
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          fontFamily: MONO,
          fontSize: SIZES.micro,
          letterSpacing: 4,
          textTransform: "uppercase",
          opacity: interpolate(frame, [0, 14], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        <span style={{ color: COLORS.accent }}>Run · the terminal UI</span>
        <span style={{ color: COLORS.textFaint }}>
          {`${step.slug.replace(/_/g, " ")} · ${stepCounter(scene.tuiStep)}`}
        </span>
      </div>
      <TuiShot
        step={scene.tuiStep}
        frameWidth={SHOT_WIDTH}
        frameHeight={SHOT_HEIGHT}
        zoom={framing.zoom}
        drift={framing.drift}
      />
    </div>
  );
};
