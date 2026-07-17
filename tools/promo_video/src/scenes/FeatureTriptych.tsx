import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

import { Backdrop, Centered, Headline } from "../components";
import { COLORS } from "../theme";

const BEATS: Array<{ title: string; accent: string; from: number; to: number }> = [
  { title: "Share analysis.", accent: COLORS.accentA, from: 0, to: 52 },
  { title: "Rate analysis.", accent: COLORS.accentB, from: 52, to: 104 },
  { title: "Excel-ready reports.", accent: COLORS.accentC, from: 104, to: 168 },
];

/** Rapid Apple-style feature beats: one bold phrase per cut. */
export const FeatureTriptych: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Backdrop glow={0.4} />
      {BEATS.map((beat) => {
        if (frame < beat.from || frame >= beat.to + 10) {
          return null;
        }
        const local = frame - beat.from;
        const span = beat.to - beat.from;
        const opacity =
          interpolate(local, [0, 10], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }) *
          interpolate(local, [span - 8, span], [1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
        const scale = interpolate(local, [0, span], [0.98, 1.04]);
        return (
          <Centered key={beat.title}>
            <div style={{ opacity, transform: `scale(${scale})` }}>
              <Headline size={128} weight={700}>
                <span style={{ color: beat.accent }}>●</span>&nbsp;&nbsp;
                {beat.title}
              </Headline>
            </div>
          </Centered>
        );
      })}
    </AbsoluteFill>
  );
};
