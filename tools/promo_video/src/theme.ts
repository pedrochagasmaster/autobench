export const COLORS = {
  bg: "#050506",
  bgSoft: "#0b0b0f",
  text: "#f5f5f7",
  textDim: "#86868b",
  accentA: "#3a7bfd",
  accentB: "#9f5bff",
  accentC: "#ff5bb1",
  green: "#30d158",
} as const;

export const FONTS = {
  display: "InterDisplay",
  mono: "JetBrainsMono",
} as const;

export const GRADIENT_TEXT: React.CSSProperties = {
  backgroundImage: `linear-gradient(100deg, ${COLORS.accentA} 0%, ${COLORS.accentB} 50%, ${COLORS.accentC} 100%)`,
  WebkitBackgroundClip: "text",
  backgroundClip: "text",
  color: "transparent",
};
