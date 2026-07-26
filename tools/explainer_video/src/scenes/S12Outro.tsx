import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Wordmark } from "../components/Wordmark";
import { OUTRO_LINKS } from "../data/facts";
import { MONO } from "../fonts";
import { COLORS, SIZES } from "../theme";

const LINKS_FROM = 46;

export const S12Outro: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        gap: 66,
      }}
    >
      <Wordmark framesPerChar={2} />
      <div style={{ display: "flex", flexDirection: "column", gap: 20, alignItems: "center" }}>
        {OUTRO_LINKS.map((link, index) => (
          <div
            key={link}
            style={{
              fontFamily: MONO,
              fontSize: SIZES.mono,
              color: COLORS.textDim,
              opacity: interpolate(
                frame,
                [LINKS_FROM + index * 16, LINKS_FROM + index * 16 + 22],
                [0, 1],
                {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                  easing: Easing.bezier(0.16, 1, 0.3, 1),
                },
              ),
            }}
          >
            {link}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
