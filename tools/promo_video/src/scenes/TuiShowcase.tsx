import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";

import { Backdrop } from "../components";
import { COLORS, FONTS } from "../theme";

const BEAT = 105;

const SHOTS: Array<{ src: string; caption: string; sub: string }> = [
  {
    src: "footage/01_fresh.png",
    caption: "Meet the terminal, reimagined.",
    sub: "A guided TUI. No manuals, no guesswork.",
  },
  {
    src: "footage/03_entity.png",
    caption: "Point it at your data.",
    sub: "Columns, entities and presets — detected for you.",
  },
  {
    src: "footage/06_done.png",
    caption: "Press run. That's it.",
    sub: "Weighted, validated, and written to Excel in seconds.",
  },
];

/** Real TUI footage floating with slow zoom, Apple product-shot style. */
export const TuiShowcase: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Backdrop glow={0.6} />
      {SHOTS.map((shot, i) => {
        const start = i * BEAT;
        const end = start + BEAT;
        const local = frame - start;
        if (frame < start - 14 || frame > end + 14) {
          return null;
        }
        const opacity =
          interpolate(local, [0, 9], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }) *
          interpolate(local, [BEAT - 8, BEAT], [1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
        const zoom = interpolate(local, [0, BEAT], [1.0, 1.055]);
        const pan = interpolate(local, [0, BEAT], [10, -10]);
        return (
          <AbsoluteFill key={shot.src} style={{ opacity }}>
            <AbsoluteFill
              style={{ justifyContent: "flex-start", alignItems: "center" }}
            >
              <div style={{ textAlign: "center", marginTop: 74 }}>
                <div
                  style={{
                    fontFamily: FONTS.display,
                    fontWeight: 600,
                    fontSize: 72,
                    color: COLORS.text,
                    letterSpacing: "-0.03em",
                  }}
                >
                  {shot.caption}
                </div>
                <div
                  style={{
                    fontFamily: FONTS.display,
                    fontWeight: 500,
                    fontSize: 33,
                    color: COLORS.textDim,
                    marginTop: 14,
                  }}
                >
                  {shot.sub}
                </div>
              </div>
            </AbsoluteFill>
            <AbsoluteFill
              style={{
                justifyContent: "flex-end",
                alignItems: "center",
                paddingBottom: 0,
              }}
            >
              <div
                style={{
                  width: 1290,
                  transform: `translateY(${64 + pan}px) scale(${zoom})`,
                  transformOrigin: "center 20%",
                  filter: "drop-shadow(0 50px 90px rgba(0,0,0,0.6))",
                }}
              >
                <Img
                  src={staticFile(shot.src)}
                  style={{ width: "100%", display: "block" }}
                />
              </div>
            </AbsoluteFill>
          </AbsoluteFill>
        );
      })}
    </AbsoluteFill>
  );
};
