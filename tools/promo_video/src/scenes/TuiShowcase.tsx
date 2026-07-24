import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";

import { Backdrop, WordRise } from "../components";
import { COLORS, FONTS } from "../theme";

const BEAT = 105;
// Adjacent beats overlap by this many frames and crossfade, so the scene
// never dips to black between shots.
const OVERLAP = 12;

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

/** Real TUI footage as a floating 3D product shot with a sheen sweep. */
export const TuiShowcase: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Backdrop glow={0.6} />
      {SHOTS.map((shot, i) => {
        const start = i * BEAT;
        const local = frame - start;
        if (local < 0 || local > BEAT + OVERLAP) {
          return null;
        }
        const opacity =
          interpolate(local, [0, OVERLAP], [i === 0 ? 1 : 0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }) *
          interpolate(local, [BEAT, BEAT + OVERLAP], [1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
        const zoom = interpolate(local, [0, BEAT + OVERLAP], [1.0, 1.05]);
        const pan = interpolate(local, [0, BEAT + OVERLAP], [12, -12]);
        const tilt = interpolate(local, [0, BEAT + OVERLAP], [7, 2.5], {
          easing: (v) => 1 - Math.pow(1 - v, 2),
        });
        const sheen = interpolate(local, [8, BEAT - 14], [-35, 135], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
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
                  <WordRise words={shot.caption} delay={3} stagger={3} />
                </div>
                <div
                  style={{
                    fontFamily: FONTS.display,
                    fontWeight: 500,
                    fontSize: 33,
                    color: COLORS.textDim,
                    marginTop: 14,
                    opacity: interpolate(local, [14, 30], [0, 1], {
                      extrapolateLeft: "clamp",
                      extrapolateRight: "clamp",
                    }),
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
                perspective: 1500,
              }}
            >
              <div
                style={{
                  width: 1290,
                  position: "relative",
                  transform: `translateY(${64 + pan}px) rotateX(${tilt}deg) scale(${zoom})`,
                  transformOrigin: "center 18%",
                  filter: "drop-shadow(0 50px 90px rgba(0,0,0,0.62))",
                }}
              >
                <Img
                  src={staticFile(shot.src)}
                  style={{ width: "100%", display: "block" }}
                />
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    borderRadius: 18,
                    background: `linear-gradient(115deg, transparent ${
                      sheen - 14
                    }%, rgba(255,255,255,0.09) ${sheen}%, transparent ${
                      sheen + 14
                    }%)`,
                    mixBlendMode: "screen",
                  }}
                />
              </div>
            </AbsoluteFill>
          </AbsoluteFill>
        );
      })}
    </AbsoluteFill>
  );
};
