import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { MONO } from "../fonts";
import { COLORS, SAFE, SIZES } from "../theme";

type Props = {
  kicker?: string;
  children: React.ReactNode;
  /** Vertical placement of the scene body inside the safe area. */
  align?: "center" | "start";
};

export const SceneFrame: React.FC<Props> = ({ kicker, children, align = "center" }) => {
  const frame = useCurrentFrame();

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
      {kicker ? (
        <div
          style={{
            fontFamily: MONO,
            fontSize: SIZES.kicker,
            letterSpacing: 6,
            textTransform: "uppercase",
            color: COLORS.textFaint,
            opacity: interpolate(frame, [0, 18], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          {kicker}
        </div>
      ) : null}
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
