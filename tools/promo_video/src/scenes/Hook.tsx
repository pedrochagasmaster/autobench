import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

import { Centered, Headline } from "../components";
import { COLORS } from "../theme";

const LINES: Array<{ text: string; from: number; to: number; dim?: boolean }> = [
  { text: "Your peers hold the answers.", from: 0, to: 78 },
  { text: "Privacy holds the rules.", from: 84, to: 162 },
  { text: "What if you never had to choose?", from: 170, to: 275 },
];

/** Opening beats: short declarative lines, one at a time, on black. */
export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      {LINES.map((line) => {
        const opacity =
          interpolate(frame, [line.from, line.from + 18], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }) *
          interpolate(frame, [line.to - 14, line.to], [1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
        const drift = interpolate(frame, [line.from, line.to], [16, -10], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        if (opacity <= 0) {
          return null;
        }
        return (
          <Centered key={line.text}>
            <div style={{ opacity, transform: `translateY(${drift}px)` }}>
              <Headline size={92} weight={500}>
                {line.text}
              </Headline>
            </div>
          </Centered>
        );
      })}
    </AbsoluteFill>
  );
};
