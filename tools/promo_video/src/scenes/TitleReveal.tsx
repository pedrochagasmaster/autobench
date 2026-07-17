import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { Backdrop, Centered, RiseIn } from "../components";
import { COLORS, FONTS } from "../theme";

/** Big wordmark reveal: flash, gradient shine sweep, and a slow settle. */
export const TitleReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({
    frame,
    fps,
    config: { damping: 15, mass: 0.9 },
    durationInFrames: 45,
  });
  // Impact flash synced to the soundtrack boom at the scene start.
  const flash = interpolate(frame, [2, 16], [0.55, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const glowPulse = 0.55 + 0.45 * Math.sin(frame / 14);
  const shine = interpolate(frame, [14, 96], [-40, 140], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const settle = interpolate(frame, [0, 170], [1.045, 1.0]);

  return (
    <AbsoluteFill>
      <Backdrop glow={1} />
      <AbsoluteFill style={{ transform: `scale(${settle})` }}>
        <Centered>
          <div
            style={{
              transform: `scale(${0.84 + pop * 0.16})`,
              position: "relative",
            }}
          >
            <div
              style={{
                position: "absolute",
                inset: -90,
                background: `radial-gradient(closest-side, rgba(120, 92, 255, ${
                  0.26 * glowPulse
                }), transparent)`,
                filter: "blur(34px)",
              }}
            />
            <div
              style={{
                fontFamily: FONTS.display,
                fontWeight: 700,
                fontSize: 204,
                letterSpacing: "-0.045em",
                backgroundImage: `linear-gradient(100deg, ${COLORS.accentA} ${
                  shine - 55
                }%, #eef2ff ${shine}%, ${COLORS.accentC} ${shine + 55}%)`,
                WebkitBackgroundClip: "text",
                backgroundClip: "text",
                color: "transparent",
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
      <AbsoluteFill
        style={{
          pointerEvents: "none",
          opacity: flash,
          background:
            "radial-gradient(ellipse 60% 45% at 50% 46%, rgba(210, 220, 255, 0.9), transparent 70%)",
        }}
      />
    </AbsoluteFill>
  );
};
