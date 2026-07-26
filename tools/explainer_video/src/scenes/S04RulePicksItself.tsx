import { Easing, interpolate, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import {
  CONTROL_REFERENCE,
  PRIVACY_RULES,
  RULE_CAPTION,
  RULE_SELECTION_STEPS,
  RULE_TABLE_HEADERS,
} from "../data/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";
import { localFrame } from "../timeline";

const COUNTER_PANEL_FROM = 120;
const COUNTER_START = localFrame("s04", 810);
const STEP_FRAMES = 30;
const COUNTER_END = COUNTER_START + RULE_SELECTION_STEPS.length * STEP_FRAMES;
const CONDITIONAL_FROM = COUNTER_END + 8;
const CAPTION_FROM = COUNTER_END + 28;

const COLUMN_WIDTHS = [250, 240, 400, 750];
const ROW_HEIGHT = 74;

const activeStepAt = (local: number): number => {
  if (local < COUNTER_START) {
    return -1;
  }
  const index = Math.floor((local - COUNTER_START) / STEP_FRAMES);
  return Math.min(index, RULE_SELECTION_STEPS.length - 1);
};

const tintFor = (local: number, ruleName: string): number => {
  const step = activeStepAt(local);
  if (step < 0) {
    return 0;
  }
  if (RULE_SELECTION_STEPS[step].rule !== ruleName) {
    return 0;
  }
  if (local >= COUNTER_END) {
    return 0.4;
  }
  const within = (local - COUNTER_START) % STEP_FRAMES;
  return interpolate(within, [0, 5, 25, STEP_FRAMES], [0, 1, 1, 0.15], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};

const Cell: React.FC<{
  width: number;
  children: React.ReactNode;
  font?: string;
  size?: number;
  color?: string;
}> = ({ width, children, font = MONO, size = SIZES.mono, color = COLORS.text }) => (
  <div
    style={{
      width,
      fontFamily: font,
      fontSize: size,
      color,
      whiteSpace: "nowrap",
    }}
  >
    {children}
  </div>
);

export const S04RulePicksItself: React.FC<{ showControlReference: boolean }> = ({
  showControlReference,
}) => {
  const frame = useCurrentFrame();
  const step = activeStepAt(frame);
  const selection = step >= 0 ? RULE_SELECTION_STEPS[step] : null;
  const stepStart = COUNTER_START + Math.max(step, 0) * STEP_FRAMES;

  return (
    <SceneFrame sceneId="s04">
      <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            opacity: interpolate(frame, [COUNTER_PANEL_FROM, COUNTER_PANEL_FROM + 20], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        >
          <div
            style={{
              display: "flex",
              gap: 56,
              padding: "22px 38px",
              borderRadius: 8,
              backgroundColor: COLORS.panel,
              border: `1px solid ${COLORS.edge}`,
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div
                style={{
                  fontFamily: MONO,
                  fontSize: SIZES.micro,
                  letterSpacing: 3,
                  color: COLORS.textFaint,
                  textTransform: "uppercase",
                }}
              >
                peers in group
              </div>
              <div
                style={{
                  fontFamily: MONO,
                  fontSize: 60,
                  fontWeight: 500,
                  color: COLORS.text,
                  lineHeight: 1,
                  scale: interpolate(frame, [stepStart, stepStart + 8], [1.08, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                    easing: Easing.bezier(0.16, 1, 0.3, 1),
                  }),
                }}
              >
                {selection ? selection.peers : "—"}
              </div>
            </div>
            <div style={{ width: 1, backgroundColor: COLORS.edge }} />
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div
                style={{
                  fontFamily: MONO,
                  fontSize: SIZES.micro,
                  letterSpacing: 3,
                  color: COLORS.textFaint,
                  textTransform: "uppercase",
                }}
              >
                rule selected
              </div>
              <div
                style={{
                  fontFamily: MONO,
                  fontSize: 60,
                  fontWeight: 500,
                  color: COLORS.accent,
                  lineHeight: 1,
                }}
              >
                {selection ? selection.rule : "—"}
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              display: "flex",
              paddingBottom: 14,
              borderBottom: `1px solid ${COLORS.edgeBright}`,
              opacity: interpolate(frame, [0, 16], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
            }}
          >
            {RULE_TABLE_HEADERS.map((header, index) => (
              <Cell
                key={header}
                width={COLUMN_WIDTHS[index]}
                font={MONO}
                size={SIZES.micro}
                color={COLORS.textFaint}
              >
                <span style={{ letterSpacing: 3, textTransform: "uppercase" }}>{header}</span>
              </Cell>
            ))}
          </div>

          {PRIVACY_RULES.map((rule, index) => {
            const enterAt = 20 * index;
            const enter = interpolate(frame, [enterAt, enterAt + 22], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            });
            const tint = tintFor(frame, rule.name);
            const conditionalOn = rule.conditional
              ? interpolate(frame, [CONDITIONAL_FROM, CONDITIONAL_FROM + 20], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                })
              : 0;
            const dimmed = rule.conditional ? 0.42 + 0.58 * conditionalOn : 1;

            return (
              <div
                key={rule.name}
                style={{
                  display: "flex",
                  alignItems: "center",
                  height: ROW_HEIGHT,
                  paddingLeft: 10,
                  marginLeft: -10,
                  borderRadius: 6,
                  opacity: enter * dimmed,
                  translate: interpolate(enter, [0, 1], ["0px 14px", "0px 0px"]),
                  backgroundColor: rule.conditional
                    ? `rgba(216, 178, 106, ${0.14 * conditionalOn})`
                    : `rgba(143, 179, 212, ${0.16 * tint})`,
                }}
              >
                <Cell
                  width={COLUMN_WIDTHS[0]}
                  color={
                    rule.conditional
                      ? conditionalOn > 0.5
                        ? COLORS.amber
                        : COLORS.textDim
                      : tint > 0.5
                        ? COLORS.accent
                        : COLORS.text
                  }
                >
                  {rule.name}
                </Cell>
                <Cell width={COLUMN_WIDTHS[1]} color={COLORS.textDim}>
                  {rule.minPeers}
                </Cell>
                <Cell width={COLUMN_WIDTHS[2]} color={COLORS.textDim}>
                  {rule.maxConcentration}
                </Cell>
                <Cell
                  width={COLUMN_WIDTHS[3]}
                  font={SANS}
                  size={SIZES.label}
                  color={COLORS.textDim}
                >
                  {rule.extra}
                </Cell>
              </div>
            );
          })}
        </div>

        <div
          style={{
            fontFamily: MONO,
            fontSize: SIZES.micro,
            letterSpacing: 2,
            color: COLORS.textFaint,
            height: SIZES.micro,
            opacity: showControlReference
              ? interpolate(frame, [100, 130], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                })
              : 0,
          }}
        >
          {CONTROL_REFERENCE}
        </div>

        <div
          style={{
            fontFamily: SANS,
            fontSize: SIZES.lead,
            color: COLORS.text,
            opacity: interpolate(frame, [CAPTION_FROM, CAPTION_FROM + 22], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          {RULE_CAPTION}
        </div>
      </div>
    </SceneFrame>
  );
};
