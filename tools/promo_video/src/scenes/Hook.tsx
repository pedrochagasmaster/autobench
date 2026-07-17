import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

import { Centered, WordRise } from "../components";
import { COLORS, FONTS } from "../theme";

const LINES: Array<{ text: string; from: number; to: number; accent?: string }> = [
  { text: "Your peers hold the answers.", from: 0, to: 80 },
  { text: "Privacy holds the rules.", from: 86, to: 164 },
  // Ends just before the crossfade into the title so it doesn't ghost
  // behind the wordmark.
  { text: "What if you never had to choose?", from: 172, to: 271 },
];

/** Opening beats: short declarative lines, word by word, on black. */
export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      {LINES.map((line, li) => {
        const local = frame - line.from;
        if (frame < line.from || frame > line.to + 4) {
          return null;
        }
        const fadeOut = interpolate(
          frame,
          [line.to - 12, line.to],
          [1, 0],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
        const drift = interpolate(local, [0, line.to - line.from], [6, -14]);
        const isQuestion = li === LINES.length - 1;
        return (
          <Centered key={line.text}>
            <div
              style={{
                opacity: fadeOut,
                transform: `translateY(${drift}px) scale(${
                  1 + local * 0.00045
                })`,
                fontFamily: FONTS.display,
                fontWeight: 500,
                fontSize: isQuestion ? 96 : 92,
                color: COLORS.text,
                letterSpacing: "-0.03em",
                textAlign: "center",
                maxWidth: 1560,
              }}
            >
              <WordRise
                words={line.text}
                delay={2}
                stagger={4}
                render={
                  isQuestion
                    ? (word) =>
                        word === "never"
                          ? { fontWeight: 700 }
                          : {}
                    : undefined
                }
              />
            </div>
          </Centered>
        );
      })}
    </AbsoluteFill>
  );
};
