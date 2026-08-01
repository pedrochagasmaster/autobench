import { Easing, interpolate, useCurrentFrame } from "remotion";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

export type Cell = {
  text: string;
  mono?: boolean;
  color?: string;
};

type Props = {
  headers: string[];
  rows: Cell[][];
  widths: number[];
  /** Row index rendered as the one that matters. */
  emphasis?: number;
  /** Row index rendered as conditional or secondary. */
  muted?: number;
  startFrame?: number;
  rowStagger?: number;
  rowHeight?: number;
  fontSize?: number;
};

export const DataTable: React.FC<Props> = ({
  headers,
  rows,
  widths,
  emphasis,
  muted,
  startFrame = 0,
  rowStagger = 14,
  rowHeight = 78,
  fontSize = SIZES.label,
}) => {
  const frame = useCurrentFrame();

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div
        style={{
          display: "flex",
          paddingBottom: 14,
          borderBottom: `1px solid ${COLORS.edgeBright}`,
          opacity: interpolate(frame, [startFrame, startFrame + 16], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        {headers.map((header, index) => (
          <div
            key={header}
            style={{
              width: widths[index],
              fontFamily: MONO,
              fontSize: SIZES.micro,
              letterSpacing: 3,
              textTransform: "uppercase",
              color: COLORS.textFaint,
            }}
          >
            {header}
          </div>
        ))}
      </div>

      {rows.map((row, rowIndex) => {
        const appearAt = startFrame + 10 + rowIndex * rowStagger;
        const appear = interpolate(frame, [appearAt, appearAt + 20], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        });
        const isEmphasis = rowIndex === emphasis;
        const isMuted = rowIndex === muted;
        return (
          <div
            key={row.map((cell) => cell.text).join("|")}
            style={{
              display: "flex",
              alignItems: "center",
              minHeight: rowHeight,
              paddingLeft: 14,
              marginLeft: -14,
              borderRadius: 6,
              opacity: appear * (isMuted ? 0.55 : 1),
              translate: interpolate(appear, [0, 1], ["0px 12px", "0px 0px"]),
              backgroundColor: isEmphasis ? "rgba(143, 179, 212, 0.14)" : "transparent",
            }}
          >
            {row.map((cell, cellIndex) => (
              <div
                key={`${rowIndex}-${cellIndex}`}
                style={{
                  width: widths[cellIndex],
                  paddingRight: 24,
                  fontFamily: cell.mono ? MONO : SANS,
                  fontSize: cell.mono ? fontSize - 2 : fontSize,
                  lineHeight: 1.32,
                  color:
                    cell.color ??
                    (cellIndex === 0
                      ? isEmphasis
                        ? COLORS.accent
                        : COLORS.text
                      : COLORS.textDim),
                }}
              >
                {cell.text}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};
