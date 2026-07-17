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

/** Closing lockup: wordmark, tagline, and the command to get started. */
export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({
    frame,
    fps,
    config: { damping: 17, mass: 0.9 },
    durationInFrames: 42,
  });
  const chipGlow = interpolate(frame, [70, 100], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      <Backdrop glow={0.8} />
      <Centered>
        <div
          style={{
            fontFamily: FONTS.display,
            fontWeight: 700,
            fontSize: 148,
            letterSpacing: "-0.045em",
            ...GRADIENT_TEXT,
            opacity: pop,
            transform: `scale(${0.9 + pop * 0.1})`,
          }}
        >
          Autobench
        </div>
        <RiseIn delay={22} duration={24}>
          <div
            style={{
              fontFamily: FONTS.display,
              fontWeight: 600,
              fontSize: 56,
              color: COLORS.text,
              letterSpacing: "-0.02em",
              marginTop: 20,
            }}
          >
            Benchmark boldly. <span style={{ color: COLORS.textDim }}>Privately.</span>
          </div>
        </RiseIn>
        <RiseIn delay={58} duration={26}>
          <div
            style={{
              marginTop: 58,
              padding: "20px 44px",
              borderRadius: 100,
              border: "1px solid rgba(255,255,255,0.14)",
              background: "rgba(255,255,255,0.05)",
              fontFamily: FONTS.mono,
              fontSize: 34,
              color: COLORS.text,
              boxShadow: `0 0 ${50 * chipGlow}px rgba(90, 120, 255, ${
                0.25 * chipGlow
              })`,
            }}
          >
            <span style={{ color: COLORS.accentA, fontWeight: 700 }}>❯</span> py
            tui_app.py
          </div>
        </RiseIn>
      </Centered>
    </AbsoluteFill>
  );
};
