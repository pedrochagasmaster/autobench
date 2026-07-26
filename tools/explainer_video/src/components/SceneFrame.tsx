import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { MONO } from "../fonts";
import { COLORS, SAFE, SIZES } from "../theme";
import { SCENES, TRANSITION_FRAMES } from "../timeline";

type Props = {
  sceneId: string;
  children: React.ReactNode;
  /** Vertical placement of the scene body inside the safe area. */
  align?: "center" | "start";
};

export const SceneFrame: React.FC<Props> = ({ sceneId, children, align = "center" }) => {
  const frame = useCurrentFrame();
  const index = SCENES.findIndex((candidate) => candidate.id === sceneId);
  const scene = SCENES[index];

  if (!scene) {
    throw new Error(`Unknown scene id: ${sceneId}`);
  }

  // Two kickers dissolving through each other at the same position reads as
  // garbled text, so the outgoing one clears before the crossfade starts.
  const crossfadesOut = index < SCENES.length - 1 && !scene.hardCutAfter;
  const kickerOpacity = crossfadesOut
    ? interpolate(
        frame,
        [
          0,
          18,
          scene.sequenceFrames - TRANSITION_FRAMES - 8,
          scene.sequenceFrames - TRANSITION_FRAMES,
        ],
        [0, 1, 1, 0],
        {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        },
      )
    : interpolate(frame, [0, 18], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: Easing.bezier(0.16, 1, 0.3, 1),
      });

  return (
    <AbsoluteFill
      style={{
        paddingTop: SAFE.top,
        paddingLeft: SAFE.side,
        paddingRight: SAFE.side,
        paddingBottom: SAFE.bottom,
        display: "flex",
        flexDirection: "column",
        gap: 40,
      }}
    >
      <div
        style={{
          fontFamily: MONO,
          fontSize: SIZES.kicker,
          letterSpacing: 6,
          textTransform: "uppercase",
          color: COLORS.textFaint,
          opacity: kickerOpacity,
        }}
      >
        {scene.label}
      </div>
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: align === "center" ? "center" : "flex-start",
        }}
      >
        {children}
      </div>
    </AbsoluteFill>
  );
};
