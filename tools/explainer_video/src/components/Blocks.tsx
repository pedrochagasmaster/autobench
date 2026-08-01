import { Easing, interpolate, useCurrentFrame } from "remotion";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

/** Eased 0→1 ramp starting at `at`. Not a hook, so it is safe inside loops. */
export const revealAt = (frame: number, at: number, over = 20): number =>
  interpolate(frame, [at, at + over], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

export const useReveal = (at: number, over = 20): number =>
  revealAt(useCurrentFrame(), at, over);

export const CodeBlock: React.FC<{
  lines: string[];
  startFrame?: number;
  lineStagger?: number;
  fontSize?: number;
  prompt?: boolean;
  accentLines?: number[];
}> = ({
  lines,
  startFrame = 0,
  lineStagger = 8,
  fontSize = SIZES.monoSmall,
  prompt = false,
  accentLines = [],
}) => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: "32px 36px",
        borderRadius: 10,
        backgroundColor: COLORS.panelSoft,
        border: `1px solid ${COLORS.edge}`,
      }}
    >
      {lines.map((line, index) => {
        const appearAt = startFrame + index * lineStagger;
        return (
          <div
            key={`${index}-${line}`}
            style={{
              display: "flex",
              gap: 14,
              opacity: interpolate(frame, [appearAt, appearAt + 14], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
            }}
          >
            {prompt ? (
              <span
                style={{ fontFamily: MONO, fontSize, color: COLORS.textFaint }}
              >
                $
              </span>
            ) : null}
            <span
              style={{
                fontFamily: MONO,
                fontSize,
                whiteSpace: "pre",
                color: accentLines.includes(index) ? COLORS.accent : COLORS.text,
              }}
            >
              {line}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export const Callout: React.FC<{
  tone?: "neutral" | "warn" | "good";
  children: React.ReactNode;
  startFrame?: number;
}> = ({ tone = "neutral", children, startFrame = 0 }) => {
  const reveal = revealAt(useCurrentFrame(), startFrame);
  const accent =
    tone === "warn" ? COLORS.warn : tone === "good" ? COLORS.good : COLORS.accent;

  return (
    <div
      style={{
        display: "flex",
        gap: 22,
        padding: "22px 28px",
        borderRadius: 8,
        backgroundColor: COLORS.panelSoft,
        borderLeft: `4px solid ${accent}`,
        opacity: reveal,
        translate: interpolate(reveal, [0, 1], ["0px 10px", "0px 0px"]),
      }}
    >
      <div
        style={{
          fontFamily: SANS,
          fontSize: SIZES.label,
          lineHeight: 1.4,
          color: COLORS.textDim,
        }}
      >
        {children}
      </div>
    </div>
  );
};

export const StepList: React.FC<{
  items: string[];
  startFrame?: number;
  stagger?: number;
  numbered?: boolean;
  marker?: string;
  markerColor?: string;
  fontSize?: number;
}> = ({
  items,
  startFrame = 0,
  stagger = 22,
  numbered = true,
  marker = "·",
  markerColor = COLORS.accent,
  fontSize = SIZES.body,
}) => {
  const frame = useCurrentFrame();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
      {items.map((item, index) => {
        const appearAt = startFrame + index * stagger;
        const appear = interpolate(frame, [appearAt, appearAt + 20], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        });
        return (
          <div
            key={item}
            style={{
              display: "flex",
              gap: 26,
              alignItems: "baseline",
              opacity: appear,
              translate: interpolate(appear, [0, 1], ["0px 12px", "0px 0px"]),
            }}
          >
            <span
              style={{
                fontFamily: MONO,
                fontSize: fontSize - 4,
                color: markerColor,
                width: 44,
                flexShrink: 0,
              }}
            >
              {numbered ? String(index + 1).padStart(2, "0") : marker}
            </span>
            <span
              style={{
                fontFamily: SANS,
                fontSize,
                lineHeight: 1.35,
                color: COLORS.text,
              }}
            >
              {item}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export const Card: React.FC<{
  title: string;
  body: string;
  hint?: string;
  startFrame?: number;
  accent?: boolean;
}> = ({ title, body, hint, startFrame = 0, accent = false }) => {
  const reveal = revealAt(useCurrentFrame(), startFrame);

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        gap: 18,
        padding: "36px 34px",
        borderRadius: 12,
        backgroundColor: COLORS.panel,
        border: `1px solid ${accent ? COLORS.edgeBright : COLORS.edge}`,
        opacity: reveal,
        translate: interpolate(reveal, [0, 1], ["0px 16px", "0px 0px"]),
      }}
    >
      <div
        style={{
          fontFamily: MONO,
          fontSize: 40,
          fontWeight: 500,
          color: accent ? COLORS.accent : COLORS.text,
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontFamily: SANS,
          fontSize: SIZES.label,
          lineHeight: 1.4,
          color: COLORS.textDim,
          flex: 1,
        }}
      >
        {body}
      </div>
      {hint ? (
        <div
          style={{
            fontFamily: MONO,
            fontSize: SIZES.micro,
            letterSpacing: 2,
            color: COLORS.textFaint,
          }}
        >
          {hint}
        </div>
      ) : null}
    </div>
  );
};
