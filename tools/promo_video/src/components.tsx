import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { COLORS, FONTS } from "./theme";

/** Full-screen dark backdrop with a slowly drifting color glow, Apple keynote style. */
export const Backdrop: React.FC<{ glow?: number }> = ({ glow = 0.5 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const x = 50 + Math.sin(t * 0.21) * 22;
  const y = 58 + Math.cos(t * 0.17) * 16;
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(1100px 800px at ${x}% ${y}%, rgba(90, 90, 255, ${
            0.16 * glow
          }), transparent 70%), radial-gradient(900px 700px at ${100 - x}% ${
            100 - y
          }%, rgba(255, 91, 177, ${0.09 * glow}), transparent 70%)`,
        }}
      />
    </AbsoluteFill>
  );
};

/** Fades the scene in and out at its edges. */
export const SceneFade: React.FC<{
  children: React.ReactNode;
  fadeIn?: number;
  fadeOut?: number;
  durationInFrames: number;
}> = ({ children, fadeIn = 12, fadeOut = 12, durationInFrames }) => {
  const frame = useCurrentFrame();
  const opacity =
    interpolate(frame, [0, fadeIn], [0, 1], {
      extrapolateRight: "clamp",
    }) *
    interpolate(frame, [durationInFrames - fadeOut, durationInFrames], [1, 0], {
      extrapolateLeft: "clamp",
    });
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

/** Apple-style headline: rises a few px while fading in, with a soft blur settle. */
export const RiseIn: React.FC<{
  children: React.ReactNode;
  delay?: number;
  duration?: number;
  distance?: number;
  style?: React.CSSProperties;
}> = ({ children, delay = 0, duration = 24, distance = 46, style }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [delay, delay + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: (v) => 1 - Math.pow(1 - v, 3.2),
  });
  return (
    <div
      style={{
        opacity: p,
        transform: `translateY(${(1 - p) * distance}px)`,
        filter: `blur(${(1 - p) * 10}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export const Headline: React.FC<{
  children: React.ReactNode;
  size?: number;
  weight?: number;
  color?: string;
  style?: React.CSSProperties;
}> = ({ children, size = 108, weight = 600, color = COLORS.text, style }) => (
  <div
    style={{
      fontFamily: FONTS.display,
      fontWeight: weight,
      fontSize: size,
      color,
      letterSpacing: "-0.03em",
      lineHeight: 1.08,
      textAlign: "center",
      ...style,
    }}
  >
    {children}
  </div>
);

export const Centered: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => (
  <AbsoluteFill
    style={{
      justifyContent: "center",
      alignItems: "center",
      flexDirection: "column",
    }}
  >
    {children}
  </AbsoluteFill>
);
