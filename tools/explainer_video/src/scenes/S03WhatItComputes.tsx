import { Easing, interpolate, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import {
  CSV_COLUMNS,
  CSV_ROWS,
  PEERS,
  SHARE_OUTPUT_LINE,
  WEIGHT_CHIP_PEERS,
} from "../data/facts";
import { MONO, SANS } from "../fonts";
import { formatMultiplier } from "../format";
import { COLORS, SIZES } from "../theme";

const CHIPS_FROM = 60;
const WEIGHTS_FROM = 100;
const WEIGHT_STAGGER = 12;
const WEIGHT_FRAMES = 30;
const OUTPUT_FROM = 200;

const CSV_COLUMN_WIDTHS = [250, 200, 170, 190];

const chipPeers = WEIGHT_CHIP_PEERS.map((name) => {
  const peer = PEERS.find((candidate) => candidate.name === name);
  if (!peer) {
    throw new Error(`Scene 3 references unknown peer ${name}`);
  }
  return peer;
});

/** Frame window over which the given chip animates away from 1.00. */
const chipWindow = (index: number): [number, number] => [
  WEIGHTS_FROM + index * WEIGHT_STAGGER,
  WEIGHTS_FROM + index * WEIGHT_STAGGER + WEIGHT_FRAMES,
];

export const S03WhatItComputes: React.FC = () => {
  const frame = useCurrentFrame();
  const dominantIndex = chipPeers.reduce(
    (best, peer, index) =>
      peer.multiplier < chipPeers[best].multiplier ? index : best,
    0,
  );
  const [dominantStart, dominantEnd] = chipWindow(dominantIndex);
  const dominantName = chipPeers[dominantIndex].name;
  const rowTint = interpolate(
    frame,
    [dominantStart - 10, dominantStart + 6, dominantEnd, dominantEnd + 24],
    [0, 1, 1, 0.35],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <SceneFrame kicker="What it actually computes">
      <div style={{ display: "flex", flexDirection: "column", gap: 46 }}>
        <div style={{ display: "flex", gap: 80 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 20, flex: 1 }}>
            <div
              style={{
                fontFamily: MONO,
                fontSize: SIZES.micro,
                letterSpacing: 3,
                textTransform: "uppercase",
                color: COLORS.textFaint,
              }}
            >
              pre-aggregated input · one row per entity and bucket
            </div>
            <div
              style={{
                padding: "26px 28px",
                borderRadius: 10,
                backgroundColor: COLORS.panelSoft,
                border: `1px solid ${COLORS.edge}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  paddingBottom: 14,
                  borderBottom: `1px solid ${COLORS.edge}`,
                }}
              >
                {CSV_COLUMNS.map((column, index) => (
                  <div
                    key={column}
                    style={{
                      width: CSV_COLUMN_WIDTHS[index],
                      fontFamily: MONO,
                      fontSize: SIZES.micro,
                      color: COLORS.textFaint,
                      textAlign: index === CSV_COLUMNS.length - 1 ? "right" : "left",
                    }}
                  >
                    {column}
                  </div>
                ))}
              </div>
              {CSV_ROWS.map((row, rowIndex) => {
                const enter = interpolate(frame, [rowIndex * 6, rowIndex * 6 + 18], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                });
                const isDominant = row[0] === dominantName;
                return (
                  <div
                    key={row.join("-")}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      height: 62,
                      paddingLeft: 8,
                      marginLeft: -8,
                      borderRadius: 5,
                      opacity: enter,
                      backgroundColor: isDominant
                        ? `rgba(216, 178, 106, ${0.16 * rowTint})`
                        : "transparent",
                    }}
                  >
                    {row.map((cell, cellIndex) => (
                      <div
                        key={`${row[0]}-${cellIndex}`}
                        style={{
                          width: CSV_COLUMN_WIDTHS[cellIndex],
                          fontFamily: MONO,
                          fontSize: SIZES.monoSmall,
                          color:
                            cellIndex === 0
                              ? isDominant && rowTint > 0.5
                                ? COLORS.amber
                                : COLORS.text
                              : COLORS.textDim,
                          textAlign: cellIndex === row.length - 1 ? "right" : "left",
                        }}
                      >
                        {cell}
                      </div>
                    ))}
                  </div>
                );
              })}
              <div
                style={{
                  fontFamily: MONO,
                  fontSize: SIZES.monoSmall,
                  color: COLORS.textFaint,
                  paddingTop: 10,
                }}
              >
                …
              </div>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 20, width: 560 }}>
            <div
              style={{
                fontFamily: MONO,
                fontSize: SIZES.micro,
                letterSpacing: 3,
                textTransform: "uppercase",
                color: COLORS.textFaint,
                opacity: interpolate(frame, [CHIPS_FROM, CHIPS_FROM + 18], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                }),
              }}
            >
              peer weight multipliers
            </div>
            {chipPeers.map((peer, index) => {
              const [start, end] = chipWindow(index);
              const value = interpolate(frame, [start, end], [1, peer.multiplier], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              });
              const changed = Math.abs(peer.multiplier - 1) > 0.001;
              const settled = frame >= end;
              return (
                <div
                  key={peer.name}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "18px 28px",
                    borderRadius: 999,
                    backgroundColor: COLORS.panel,
                    border: `1px solid ${
                      changed && settled ? "rgba(216, 178, 106, 0.55)" : COLORS.edge
                    }`,
                    opacity: interpolate(
                      frame,
                      [CHIPS_FROM + index * 6, CHIPS_FROM + index * 6 + 18],
                      [0, 1],
                      { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                    ),
                  }}
                >
                  <span
                    style={{
                      fontFamily: MONO,
                      fontSize: SIZES.mono,
                      color: COLORS.textDim,
                    }}
                  >
                    {peer.name}
                  </span>
                  <span
                    style={{
                      fontFamily: MONO,
                      fontSize: 44,
                      fontWeight: 500,
                      color: changed ? COLORS.amber : COLORS.text,
                    }}
                  >
                    {formatMultiplier(value)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 22,
            opacity: interpolate(frame, [OUTPUT_FROM, OUTPUT_FROM + 24], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          <div style={{ width: 46, height: 1, backgroundColor: COLORS.accent }} />
          <div
            style={{
              fontFamily: SANS,
              fontSize: SIZES.body,
              color: COLORS.text,
            }}
          >
            {SHARE_OUTPUT_LINE}
          </div>
        </div>
      </div>
    </SceneFrame>
  );
};
