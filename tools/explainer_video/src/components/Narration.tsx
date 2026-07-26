import { interpolate, useCurrentFrame } from "remotion";
import { NARRATION } from "../data/voiceover";
import { SANS } from "../fonts";
import { COLORS, NARRATION_BAND } from "../theme";
import { SCENES } from "../timeline";

const FADE = 14;

type Props = {
  /** Set when previewing a single scene, where frame 0 is the scene start. */
  forceSceneId?: string;
};

export const Narration: React.FC<Props> = ({ forceSceneId }) => {
  const frame = useCurrentFrame();

  const scene = forceSceneId
    ? SCENES.find((candidate) => candidate.id === forceSceneId)
    : SCENES.find(
        (candidate) =>
          frame >= candidate.start && frame < candidate.start + candidate.frames,
      );
  const line = scene ? NARRATION[scene.id] : null;

  if (!scene || !line) {
    return null;
  }

  const local = forceSceneId ? frame : frame - scene.start;
  const opacity = interpolate(
    local,
    [0, FADE, scene.frames - FADE, scene.frames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <div
      style={{
        position: "absolute",
        left: 140,
        right: 140,
        top: NARRATION_BAND.top,
        height: NARRATION_BAND.height,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 22,
        opacity,
      }}
    >
      <div
        style={{
          width: 220,
          height: 1,
          backgroundColor: COLORS.edge,
        }}
      />
      <div
        style={{
          fontFamily: SANS,
          fontSize: 30,
          lineHeight: 1.38,
          color: COLORS.textDim,
          textAlign: "center",
          maxWidth: 1480,
        }}
      >
        {line}
      </div>
    </div>
  );
};
