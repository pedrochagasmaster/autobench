import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { Backdrop, Centered } from "../components";
import { COLORS, FONTS } from "../theme";

const BEATS: Array<{ title: string; accent: string; from: number; to: number }> = [
  { title: "Share analysis.", accent: COLORS.accentA, from: 0, to: 52 },
  { title: "Rate analysis.", accent: COLORS.accentB, from: 52, to: 104 },
  { title: "Excel-ready reports.", accent: COLORS.accentC, from: 104, to: 168 },
];

/** Rapid feature beats: hard cuts, sprung type, and a colored glow per beat. */
export const FeatureTriptych: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Backdrop glow={0.4} />
      {BEATS.map((beat) => {
        if (frame < beat.from || frame >= beat.to) {
          return null;
        }
        const local = frame - beat.from;
        const span = beat.to - beat.from;
        const enter = spring({
          frame: local,
          fps,
          config: { damping: 14, mass: 0.6 },
          durationInFrames: 26,
        });
        const exit = interpolate(local, [span - 7, span], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const glow = interpolate(local, [0, 14], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <AbsoluteFill key={beat.title}>
            <AbsoluteFill
              style={{
                background: `radial-gradient(ellipse 55% 42% at 50% 52%, ${beat.accent}26, transparent 72%)`,
                opacity: glow * (1 - exit),
              }}
            />
            <Centered>
              <div
                style={{
                  opacity: enter * (1 - exit),
                  transform: `translateY(${(1 - enter) * 90 - exit * 46}px)`,
                  fontFamily: FONTS.display,
                  fontWeight: 700,
                  fontSize: 132,
                  color: COLORS.text,
                  letterSpacing: "-0.035em",
                  display: "flex",
                  alignItems: "center",
                  gap: 40,
                }}
              >
                <span
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 22,
                    background: beat.accent,
                    boxShadow: `0 0 ${46 * glow}px ${beat.accent}`,
                    flexShrink: 0,
                  }}
                />
                {beat.title}
              </div>
            </Centered>
          </AbsoluteFill>
        );
      })}
    </AbsoluteFill>
  );
};
