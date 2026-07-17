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

/** The compliance verdict: an animated check ring and the real output string. */
export const Verdict: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const ring = interpolate(frame, [6, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: (v) => 1 - Math.pow(1 - v, 3),
  });
  const check = interpolate(frame, [30, 52], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: (v) => 1 - Math.pow(1 - v, 2.4),
  });
  const pop = spring({
    frame: frame - 44,
    fps,
    config: { damping: 15, mass: 0.8 },
    durationInFrames: 40,
  });

  const R = 96;
  const CIRC = 2 * Math.PI * R;

  return (
    <AbsoluteFill>
      <Backdrop glow={0.5} />
      <Centered>
        <svg width={260} height={260} viewBox="0 0 260 260">
          <circle
            cx={130}
            cy={130}
            r={R}
            fill="none"
            stroke={COLORS.green}
            strokeWidth={10}
            strokeLinecap="round"
            strokeDasharray={CIRC}
            strokeDashoffset={CIRC * (1 - ring)}
            transform="rotate(-90 130 130)"
            opacity={0.95}
          />
          <path
            d="M 85 133 L 117 165 L 178 100"
            fill="none"
            stroke={COLORS.green}
            strokeWidth={13}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={140}
            strokeDashoffset={140 * (1 - check)}
          />
        </svg>
        <div
          style={{
            fontFamily: FONTS.mono,
            fontWeight: 700,
            fontSize: 96,
            color: COLORS.green,
            marginTop: 36,
            letterSpacing: "-0.02em",
            opacity: pop,
            transform: `scale(${0.9 + pop * 0.1})`,
            textShadow: "0 0 60px rgba(48, 209, 88, 0.35)",
          }}
        >
          fully_compliant
        </div>
        <RiseIn delay={62} duration={22}>
          <div
            style={{
              fontFamily: FONTS.display,
              fontWeight: 500,
              fontSize: 38,
              color: COLORS.textDim,
              marginTop: 26,
            }}
          >
            Auditable. Publishable. Every single run.
          </div>
        </RiseIn>
      </Centered>
    </AbsoluteFill>
  );
};
