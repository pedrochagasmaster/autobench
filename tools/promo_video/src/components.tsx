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

/** Subtle animated film grain for a cinematic finish. */
export const FilmGrain: React.FC<{ opacity?: number }> = ({
  opacity = 0.05,
}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity, mixBlendMode: "overlay" }}>
      <svg width="100%" height="100%">
        <filter id="promo-grain">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.9"
            numOctaves="2"
            seed={frame % 200}
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#promo-grain)" />
      </svg>
    </AbsoluteFill>
  );
};

/** Darkened corners to focus the eye center-frame. */
export const Vignette: React.FC<{ strength?: number }> = ({
  strength = 0.42,
}) => (
  <AbsoluteFill
    style={{
      pointerEvents: "none",
      background: `radial-gradient(ellipse 78% 68% at 50% 48%, transparent 58%, rgba(0,0,0,${strength}) 100%)`,
    }}
  />
);

/** One word of a headline, rising and un-blurring with a stagger. */
export const WordRise: React.FC<{
  words: string;
  delay?: number;
  stagger?: number;
  duration?: number;
  render?: (word: string, index: number) => React.CSSProperties;
}> = ({ words, delay = 0, stagger = 4, duration = 22, render }) => {
  const frame = useCurrentFrame();
  return (
    <span style={{ display: "inline" }}>
      {words.split(" ").map((word, i) => {
        const start = delay + i * stagger;
        const p = interpolate(frame, [start, start + duration], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: (v) => 1 - Math.pow(1 - v, 3.4),
        });
        return (
          <span
            key={`${word}-${i}`}
            style={{
              display: "inline-block",
              whiteSpace: "pre",
              opacity: p,
              transform: `translateY(${(1 - p) * 42}px)`,
              filter: `blur(${(1 - p) * 12}px)`,
              ...(render ? render(word, i) : undefined),
            }}
          >
            {word}
            {"\u00a0"}
          </span>
        );
      })}
    </span>
  );
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
