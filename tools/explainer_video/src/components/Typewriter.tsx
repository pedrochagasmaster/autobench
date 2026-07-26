import { useCurrentFrame } from "remotion";
import { COLORS } from "../theme";

export const typedLength = (
  frame: number,
  startFrame: number,
  framesPerChar: number,
  length: number,
): number => {
  if (frame < startFrame) {
    return 0;
  }
  return Math.min(length, Math.floor((frame - startFrame) / framesPerChar));
};

type Props = {
  text: string;
  startFrame: number;
  framesPerChar: number;
  cursor?: "none" | "solid" | "blink";
  cursorColor?: string;
  style?: React.CSSProperties;
};

export const Typewriter: React.FC<Props> = ({
  text,
  startFrame,
  framesPerChar,
  cursor = "solid",
  cursorColor = COLORS.accent,
  style,
}) => {
  const frame = useCurrentFrame();
  const shown = typedLength(frame, startFrame, framesPerChar, text.length);
  const done = shown >= text.length;
  const blinkOn = Math.floor(frame / 15) % 2 === 0;
  const cursorVisible =
    cursor === "none"
      ? false
      : cursor === "blink" && done
        ? blinkOn
        : frame >= startFrame;

  return (
    <span style={{ whiteSpace: "pre", ...style }}>
      {text.slice(0, shown)}
      <span
        style={{
          display: "inline-block",
          width: "0.58em",
          height: "0.66em",
          marginLeft: 1,
          verticalAlign: "0",
          backgroundColor: cursorColor,
          opacity: cursorVisible ? 0.85 : 0,
        }}
      />
    </span>
  );
};
