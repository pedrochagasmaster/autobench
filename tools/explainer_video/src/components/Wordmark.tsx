import { Easing, interpolate, useCurrentFrame } from "remotion";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";
import { Typewriter } from "./Typewriter";

type Props = {
  framesPerChar?: number;
  subtitle?: string;
  subtitleFrom?: number;
  footnote?: string;
};

export const Wordmark: React.FC<Props> = ({
  framesPerChar = 3,
  subtitle,
  subtitleFrom = 0,
  footnote,
}) => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 34,
      }}
    >
      <Typewriter
        text="autobench"
        startFrame={0}
        framesPerChar={framesPerChar}
        cursor="blink"
        style={{
          fontFamily: MONO,
          fontSize: 168,
          fontWeight: 500,
          letterSpacing: -4,
          color: COLORS.text,
        }}
      />
      {subtitle ? (
        <div
          style={{
            fontFamily: SANS,
            fontSize: SIZES.lead,
            color: COLORS.textDim,
            textAlign: "center",
            opacity: interpolate(frame, [subtitleFrom, subtitleFrom + 24], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          {subtitle}
        </div>
      ) : null}
      {footnote ? (
        <div
          style={{
            fontFamily: MONO,
            fontSize: SIZES.micro,
            letterSpacing: 3,
            color: COLORS.textFaint,
            opacity: interpolate(
              frame,
              [subtitleFrom + 14, subtitleFrom + 38],
              [0, 1],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              },
            ),
          }}
        >
          {footnote}
        </div>
      ) : null}
    </div>
  );
};
