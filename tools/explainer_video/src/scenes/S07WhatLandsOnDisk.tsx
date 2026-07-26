import { Easing, interpolate, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import { Typewriter, typedLength } from "../components/Typewriter";
import { SIDE_ARTIFACTS, SUMMARY_ROWS, WORKBOOK_TABS } from "../data/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

const WINDOW_FROM = 0;
const TABS_FROM = 30;
const TAB_STAGGER = 15;
const TYPE_FROM = 118;
const TYPE_SPEED = 2;
const ZOOM_FROM = 100;

const VERDICT_LENGTH = SUMMARY_ROWS[1].value.length;
const VERDICT_TYPED_AT = TYPE_FROM + 40 + VERDICT_LENGTH * TYPE_SPEED;
const ARTIFACTS_FROM = VERDICT_TYPED_AT + 40;

const ROW_HEIGHT = 46;
const COLUMN_A = 430;
const COLUMN_B = 470;
const SHEET_HEIGHT = 312;

const SHEET_ROWS: { a: string; b: string | null; bold?: boolean }[] = [
  { a: "Benchmark Analysis Summary", b: null, bold: true },
  { a: "Analysis Type:", b: "RATE" },
  { a: "Privacy Rule:", b: "7/35" },
];

const GridCell: React.FC<{
  width: number;
  children?: React.ReactNode;
  color?: string;
  bold?: boolean;
}> = ({ width, children, color = COLORS.textDim, bold }) => (
  <div
    style={{
      boxSizing: "border-box",
      width,
      height: ROW_HEIGHT,
      display: "flex",
      alignItems: "center",
      paddingLeft: 16,
      borderRight: `1px solid ${COLORS.edge}`,
      borderBottom: `1px solid ${COLORS.edge}`,
      fontFamily: MONO,
      fontSize: 30,
      fontWeight: bold ? 600 : 400,
      color,
      whiteSpace: "nowrap",
    }}
  >
    {children}
  </div>
);

export const S07WhatLandsOnDisk: React.FC = () => {
  const frame = useCurrentFrame();
  const open = interpolate(frame, [WINDOW_FROM, WINDOW_FROM + 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const zoom = interpolate(frame, [ZOOM_FROM, ZOOM_FROM + 30], [1, 1.07], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  // The artifact cards arrive late, so the workbook sits lower while it is the
  // only thing on screen and rises as they slide in.
  const reframe = interpolate(frame, [ARTIFACTS_FROM, ARTIFACTS_FROM + 24], [86, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <SceneFrame sceneId="s07">
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 26,
          alignItems: "center",
          translate: `0px ${reframe}px`,
        }}
      >
        <div
          style={{
            width: 1420,
            borderRadius: 12,
            overflow: "hidden",
            backgroundColor: COLORS.panelSoft,
            border: `1px solid ${COLORS.edgeBright}`,
            opacity: open,
            scale: interpolate(open, [0, 1], [0.97, 1]) * zoom,
            transformOrigin: "30% 66%",
          }}
        >
          <div
            style={{
              height: 62,
              display: "flex",
              alignItems: "center",
              paddingLeft: 26,
              gap: 26,
              backgroundColor: COLORS.panel,
              borderBottom: `1px solid ${COLORS.edge}`,
            }}
          >
            <div style={{ display: "flex", gap: 10 }}>
              {[0, 1, 2].map((dot) => (
                <div
                  key={dot}
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: 999,
                    backgroundColor: COLORS.edgeBright,
                  }}
                />
              ))}
            </div>
            <div style={{ fontFamily: MONO, fontSize: SIZES.micro, color: COLORS.textDim }}>
              gate_demo_rate.xlsx
            </div>
          </div>

          <div style={{ height: SHEET_HEIGHT, overflow: "hidden" }}>
            <div>
              <div style={{ display: "flex" }}>
                <div
                  style={{
                    boxSizing: "border-box",
                    width: 56,
                    height: 38,
                    borderRight: `1px solid ${COLORS.edge}`,
                    borderBottom: `1px solid ${COLORS.edge}`,
                    backgroundColor: COLORS.panel,
                  }}
                />
                {[
                  { label: "A", width: COLUMN_A },
                  { label: "B", width: COLUMN_B },
                  { label: "C", width: 430 },
                ].map((column) => (
                  <div
                    key={column.label}
                    style={{
                      boxSizing: "border-box",
                      width: column.width,
                      height: 38,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      borderRight: `1px solid ${COLORS.edge}`,
                      borderBottom: `1px solid ${COLORS.edge}`,
                      backgroundColor: COLORS.panel,
                      fontFamily: MONO,
                      fontSize: 22,
                      color: COLORS.textFaint,
                    }}
                  >
                    {column.label}
                  </div>
                ))}
              </div>

              {SHEET_ROWS.map((row, index) => (
                <div key={row.a} style={{ display: "flex" }}>
                  <div
                    style={{
                      boxSizing: "border-box",
                      width: 56,
                      height: ROW_HEIGHT,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      borderRight: `1px solid ${COLORS.edge}`,
                      borderBottom: `1px solid ${COLORS.edge}`,
                      backgroundColor: COLORS.panel,
                      fontFamily: MONO,
                      fontSize: 22,
                      color: COLORS.textFaint,
                    }}
                  >
                    {index + 1}
                  </div>
                  <GridCell
                    width={COLUMN_A}
                    color={row.bold ? COLORS.text : COLORS.textDim}
                    bold={row.bold}
                  >
                    {row.a}
                  </GridCell>
                  <GridCell width={COLUMN_B}>{row.b ?? ""}</GridCell>
                  <GridCell width={430} />
                </div>
              ))}

              {SUMMARY_ROWS.map((row, index) => {
                const startFrame = TYPE_FROM + index * 40;
                const shown = typedLength(
                  frame,
                  startFrame,
                  TYPE_SPEED,
                  row.value.length,
                );
                return (
                  <div key={row.label} style={{ display: "flex" }}>
                    <div
                      style={{
                        boxSizing: "border-box",
                        width: 56,
                        height: ROW_HEIGHT,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        borderRight: `1px solid ${COLORS.edge}`,
                        borderBottom: `1px solid ${COLORS.edge}`,
                        backgroundColor: COLORS.panel,
                        fontFamily: MONO,
                        fontSize: 22,
                        color: COLORS.textFaint,
                      }}
                    >
                      {SHEET_ROWS.length + index + 1}
                    </div>
                    <GridCell width={COLUMN_A} color={COLORS.text}>
                      {row.label}
                    </GridCell>
                    <div
                      style={{
                        boxSizing: "border-box",
                        width: COLUMN_B,
                        height: ROW_HEIGHT,
                        display: "flex",
                        alignItems: "center",
                        paddingLeft: 16,
                        borderRight: `1px solid ${COLORS.edge}`,
                        borderBottom: `1px solid ${COLORS.edge}`,
                        backgroundColor:
                          shown >= row.value.length
                            ? "rgba(151, 187, 157, 0.12)"
                            : "transparent",
                      }}
                    >
                      <Typewriter
                        text={row.value}
                        startFrame={startFrame}
                        framesPerChar={TYPE_SPEED}
                        cursor="solid"
                        cursorColor={COLORS.good}
                        style={{
                          fontFamily: MONO,
                          fontSize: 30,
                          fontWeight: 600,
                          color: COLORS.good,
                        }}
                      />
                    </div>
                    <GridCell width={430} />
                  </div>
                );
              })}
            </div>
          </div>

          <div
            style={{
              height: 62,
              display: "flex",
              alignItems: "center",
              gap: 8,
              paddingLeft: 20,
              backgroundColor: COLORS.panel,
              borderTop: `1px solid ${COLORS.edge}`,
            }}
          >
            {WORKBOOK_TABS.map((tab, index) => {
              const appear = interpolate(
                frame,
                [TABS_FROM + index * TAB_STAGGER, TABS_FROM + index * TAB_STAGGER + 14],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
              );
              const active = index === 0;
              return (
                <div
                  key={tab}
                  style={{
                    padding: "10px 24px",
                    borderRadius: "6px 6px 0 0",
                    fontFamily: MONO,
                    fontSize: 27,
                    color: active ? COLORS.text : COLORS.textDim,
                    backgroundColor: active ? COLORS.panelSoft : "transparent",
                    borderTop: `2px solid ${active ? COLORS.accent : "transparent"}`,
                    opacity: appear,
                  }}
                >
                  {tab}
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ width: 1420, display: "flex", flexDirection: "column", gap: 14 }}>
          {SIDE_ARTIFACTS.map((artifact, index) => {
            const slideFrom = ARTIFACTS_FROM + index * 20;
            const slide = interpolate(frame, [slideFrom, slideFrom + 24], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            });
            return (
              <div
                key={artifact.file}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                  padding: "16px 28px",
                  borderRadius: 8,
                  backgroundColor: COLORS.panelSoft,
                  border: `1px solid ${COLORS.edge}`,
                  opacity: slide,
                  translate: interpolate(slide, [0, 1], ["120px 0px", "0px 0px"]),
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
                  <div
                    style={{
                      fontFamily: MONO,
                      fontSize: 32,
                      color: COLORS.text,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {artifact.file}
                  </div>
                  <div
                    style={{
                      fontFamily: MONO,
                      fontSize: 25,
                      color: COLORS.accent,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {artifact.flag}
                  </div>
                </div>
                <div
                  style={{
                    fontFamily: SANS,
                    fontSize: 27,
                    color: COLORS.textFaint,
                    whiteSpace: "nowrap",
                  }}
                >
                  {artifact.note}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </SceneFrame>
  );
};
