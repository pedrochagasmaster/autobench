import { Easing, interpolate, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import { COMPARISON_HEADERS, COMPARISON_ROWS } from "../data/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

const PAIR_STAGGER = 44;
const SIDE_OFFSET = 22;

const Column: React.FC<{
  header: string;
  values: string[];
  offset: number;
  dim: boolean;
  align: "left" | "right";
}> = ({ header, values, offset, dim, align }) => {
  const frame = useCurrentFrame();

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 20 }}>
      <div
        style={{
          fontFamily: MONO,
          fontSize: SIZES.micro,
          letterSpacing: 4,
          textTransform: "uppercase",
          color: dim ? COLORS.textFaint : COLORS.accent,
          textAlign: align,
          paddingBottom: 18,
          borderBottom: `1px solid ${dim ? COLORS.edge : COLORS.edgeBright}`,
          opacity: interpolate(frame, [0, 18], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        {header}
      </div>
      {values.map((value, index) => {
        const appearAt = offset + index * PAIR_STAGGER;
        const appear = interpolate(frame, [appearAt, appearAt + 22], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        });
        return (
          <div
            key={value}
            style={{
              height: 76,
              display: "flex",
              alignItems: "center",
              justifyContent: align === "right" ? "flex-end" : "flex-start",
              fontFamily: SANS,
              fontSize: SIZES.body,
              color: dim ? COLORS.textDim : COLORS.text,
              textAlign: align,
              opacity: appear * (dim ? 0.6 : 1),
              translate: interpolate(appear, [0, 1], ["0px 12px", "0px 0px"]),
            }}
          >
            {value}
          </div>
        );
      })}
    </div>
  );
};

export const S08BeforeAndAfter: React.FC = () => {
  return (
    <SceneFrame sceneId="s08">
      <div style={{ display: "flex", gap: 90 }}>
        <Column
          header={COMPARISON_HEADERS[0]}
          values={COMPARISON_ROWS.map((row) => row[0])}
          offset={0}
          dim
          align="right"
        />
        <div style={{ width: 1, backgroundColor: COLORS.edge }} />
        <Column
          header={COMPARISON_HEADERS[1]}
          values={COMPARISON_ROWS.map((row) => row[1])}
          offset={SIDE_OFFSET}
          dim={false}
          align="left"
        />
      </div>
    </SceneFrame>
  );
};
