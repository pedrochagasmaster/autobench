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

const RULES = ["5/25", "6/30", "7/35", "10/40"];

/** The Mastercard Control 3.2 privacy rules as huge sequential numerals. */
export const PrivacyRules: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill>
      <Backdrop glow={0.45} />
      <Centered>
        <RiseIn delay={0} duration={20}>
          <div
            style={{
              fontFamily: FONTS.display,
              fontWeight: 500,
              fontSize: 44,
              color: COLORS.textDim,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              marginBottom: 30,
            }}
          >
            Mastercard Control 3.2
          </div>
        </RiseIn>
        <div style={{ display: "flex", gap: 66, alignItems: "baseline" }}>
          {RULES.map((rule, i) => {
            const delay = 16 + i * 13;
            const pop = spring({
              frame: frame - delay,
              fps,
              config: { damping: 13, mass: 0.7 },
              durationInFrames: 40,
            });
            return (
              <div
                key={rule}
                style={{
                  fontFamily: FONTS.display,
                  fontWeight: 700,
                  fontSize: 150,
                  letterSpacing: "-0.04em",
                  ...GRADIENT_TEXT,
                  opacity: pop,
                  transform: `scale(${0.7 + pop * 0.3}) translateY(${
                    (1 - pop) * 40
                  }px)`,
                }}
              >
                {rule}
              </div>
            );
          })}
        </div>
        <RiseIn delay={86} duration={24}>
          <div
            style={{
              fontFamily: FONTS.display,
              fontWeight: 600,
              fontSize: 66,
              color: COLORS.text,
              letterSpacing: "-0.025em",
              marginTop: 44,
            }}
          >
            Every cap. Enforced.{" "}
            <span style={{ color: COLORS.textDim }}>Automatically.</span>
          </div>
        </RiseIn>
        <RiseIn delay={112} duration={24}>
          <div
            style={{
              fontFamily: FONTS.display,
              fontWeight: 500,
              fontSize: 32,
              color: COLORS.textDim,
              marginTop: 20,
              opacity: interpolate(frame, [112, 136], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
            }}
          >
            No peer ever dominates a category. You never configure a thing.
          </div>
        </RiseIn>
      </Centered>
    </AbsoluteFill>
  );
};
