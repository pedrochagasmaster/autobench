import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { Backdrop, Centered, RiseIn } from "../components";
import { COLORS, FONTS, GRADIENT_TEXT } from "../theme";

/** Big wordmark reveal with gradient glow. */
export const TitleReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 16, mass: 0.9 }, durationInFrames: 45 });
  const glowPulse = 0.55 + 0.45 * Math.sin(frame / 14);
  const shine = interpolate(frame, [20, 90], [-30, 130], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill>
      <Backdrop glow={1} />
      <Centered>
        <div
          style={{
            transform: `scale(${0.86 + pop * 0.14})`,
            position: "relative",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: -80,
              background: `radial-gradient(closest-side, rgba(120, 92, 255, ${
                0.22 * glowPulse
              }), transparent)`,
              filter: "blur(30px)",
            }}
          />
          <div
            style={{
              fontFamily: FONTS.display,
              fontWeight: 700,
              fontSize: 200,
              letterSpacing: "-0.045em",
              ...GRADIENT_TEXT,
              backgroundImage: `linear-gradient(100deg, ${COLORS.accentA} ${
                shine - 60
              }%, #dfe6ff ${shine}%, ${COLORS.accentC} ${shine + 60}%)`,
            }}
          >
            Autobench
          </div>
        </div>
        <RiseIn delay={26}>
          <div
            style={{
              fontFamily: FONTS.display,
              fontWeight: 500,
              fontSize: 46,
              color: COLORS.textDim,
              letterSpacing: "-0.01em",
              marginTop: 26,
            }}
          >
            Peer benchmarking. Privacy-compliant by design.
          </div>
        </RiseIn>
      </Centered>
    </AbsoluteFill>
  );
};
