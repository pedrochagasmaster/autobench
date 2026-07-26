import { Easing, interpolate, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import { Typewriter } from "../components/Typewriter";
import { CODE_SNIPPET, ENGINE_LABEL, ENTRY_POINTS } from "../data/facts";
import { MONO, SANS } from "../fonts";
import { COLORS } from "../theme";

const PATH_STAGGER = 20;
const PATH_FROM = 20;
const PATH_DRAW = 26;
const CONNECTED_AT = PATH_FROM + PATH_STAGGER * 2 + PATH_DRAW;
const SNIPPET_FROM = 100;
const SNIPPET_SPEED = 1;
const BLANK_LINE_PAUSE = 6;

const DOOR_HEIGHT = 104;
const DOOR_GAP = 26;
const CONNECTOR_WIDTH = 260;
const PATH_LENGTH = 340;

const snippetStart = (index: number): number => {
  let offset = SNIPPET_FROM;
  for (let line = 0; line < index; line += 1) {
    offset +=
      CODE_SNIPPET[line].length === 0
        ? BLANK_LINE_PAUSE
        : CODE_SNIPPET[line].length * SNIPPET_SPEED + 4;
  }
  return offset;
};

export const S10ThreeWaysIn: React.FC = () => {
  const frame = useCurrentFrame();
  const doorsHeight = ENTRY_POINTS.length * DOOR_HEIGHT + (ENTRY_POINTS.length - 1) * DOOR_GAP;
  const doorCenter = (index: number) => index * (DOOR_HEIGHT + DOOR_GAP) + DOOR_HEIGHT / 2;
  const pulse = interpolate(
    frame,
    [CONNECTED_AT, CONNECTED_AT + 10, CONNECTED_AT + 28],
    [0, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <SceneFrame kicker="Three ways in, one engine">
      <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "center" }}>
          <div style={{ width: 620, display: "flex", flexDirection: "column", gap: DOOR_GAP }}>
            {ENTRY_POINTS.map((entry, index) => (
              <div
                key={entry.name}
                style={{
                  boxSizing: "border-box",
                  height: DOOR_HEIGHT,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  gap: 8,
                  padding: "0 30px",
                  borderRadius: 10,
                  backgroundColor: COLORS.panel,
                  border: `1px solid ${COLORS.edge}`,
                  opacity: interpolate(frame, [index * 10, index * 10 + 20], [0, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                    easing: Easing.bezier(0.16, 1, 0.3, 1),
                  }),
                }}
              >
                <div style={{ fontFamily: MONO, fontSize: 36, color: COLORS.text }}>
                  {entry.name}
                </div>
                <div style={{ fontFamily: SANS, fontSize: 27, color: COLORS.textFaint }}>
                  {entry.note}
                </div>
              </div>
            ))}
          </div>

          <svg
            width={CONNECTOR_WIDTH}
            height={doorsHeight}
            viewBox={`0 0 ${CONNECTOR_WIDTH} ${doorsHeight}`}
          >
            {ENTRY_POINTS.map((entry, index) => {
              const drawFrom = PATH_FROM + index * PATH_STAGGER;
              const progress = interpolate(frame, [drawFrom, drawFrom + PATH_DRAW], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.bezier(0.33, 0, 0.67, 1),
              });
              return (
                <path
                  key={entry.name}
                  d={`M 0,${doorCenter(index)} C ${CONNECTOR_WIDTH / 2},${doorCenter(
                    index,
                  )} ${CONNECTOR_WIDTH / 2},${doorsHeight / 2} ${CONNECTOR_WIDTH},${
                    doorsHeight / 2
                  }`}
                  fill="none"
                  stroke={COLORS.accent}
                  strokeWidth={2}
                  opacity={0.7}
                  strokeDasharray={PATH_LENGTH}
                  strokeDashoffset={PATH_LENGTH * (1 - progress)}
                />
              );
            })}
          </svg>

          <div
            style={{
              width: 300,
              height: doorsHeight,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: 12,
              backgroundColor: COLORS.panel,
              border: `2px solid ${pulse > 0.4 ? COLORS.accent : COLORS.edgeBright}`,
              boxShadow: `0 0 ${34 * pulse}px rgba(143, 179, 212, ${0.5 * pulse})`,
            }}
          >
            <div
              style={{
                fontFamily: MONO,
                fontSize: 64,
                fontWeight: 500,
                color: COLORS.text,
              }}
            >
              {ENGINE_LABEL}
            </div>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            padding: "30px 36px",
            borderRadius: 10,
            backgroundColor: COLORS.panelSoft,
            border: `1px solid ${COLORS.edge}`,
          }}
        >
          {CODE_SNIPPET.map((line, index) => (
            <div key={`${index}-${line}`} style={{ height: 46, display: "flex" }}>
              <Typewriter
                text={line}
                startFrame={snippetStart(index)}
                framesPerChar={SNIPPET_SPEED}
                cursor={index === CODE_SNIPPET.length - 1 ? "blink" : "none"}
                style={{
                  fontFamily: MONO,
                  fontSize: 34,
                  color: index < 2 ? COLORS.textDim : COLORS.text,
                }}
              />
            </div>
          ))}
        </div>
      </div>
    </SceneFrame>
  );
};
