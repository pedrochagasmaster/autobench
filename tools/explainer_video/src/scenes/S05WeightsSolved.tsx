import { Easing, interpolate, Sequence, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import { PEERS, WEIGHT_METHODS } from "../data/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

const CARD_LIT = [20, 110, 200];
const CARD_FAIL = [84, 172];
const LADDER_CUT = 260;

const ROW_HEIGHT = 74;
const CONNECTOR_WIDTH = 260;

const MethodCards: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 56 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 22 }}>
        {WEIGHT_METHODS.map((method, index) => {
          const litAt = CARD_LIT[index];
          const supersededAt = CARD_LIT[index + 1];
          const lit = interpolate(frame, [litAt, litAt + 18], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          });
          const superseded =
            supersededAt === undefined
              ? 0
              : interpolate(frame, [supersededAt, supersededAt + 18], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                });
          const emphasis = lit * (1 - 0.55 * superseded);
          const failAt = CARD_FAIL[index];

          return (
            <div
              key={method.name}
              style={{ display: "flex", alignItems: "flex-start", gap: 22 }}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 20, width: 466 }}>
                <div
                  style={{
                    boxSizing: "border-box",
                    display: "flex",
                    flexDirection: "column",
                    gap: 18,
                    padding: "34px 30px",
                    height: 196,
                    borderRadius: 10,
                    backgroundColor: COLORS.panel,
                    border: `1px solid ${
                      emphasis > 0.5 ? COLORS.edgeBright : COLORS.edge
                    }`,
                    opacity: 0.3 + 0.7 * emphasis,
                  }}
                >
                  <div
                    style={{
                      fontFamily: MONO,
                      fontSize: 31,
                      fontWeight: 500,
                      whiteSpace: "nowrap",
                      color: emphasis > 0.5 ? COLORS.accent : COLORS.textDim,
                    }}
                  >
                    {method.name}
                  </div>
                  <div
                    style={{
                      fontFamily: SANS,
                      fontSize: SIZES.label,
                      lineHeight: 1.35,
                      color: COLORS.textDim,
                    }}
                  >
                    {method.note}
                  </div>
                </div>
                <div
                  style={{
                    fontFamily: MONO,
                    fontSize: SIZES.monoSmall,
                    color: COLORS.warn,
                    height: SIZES.monoSmall + 6,
                    opacity:
                      method.failure && failAt !== undefined
                        ? interpolate(frame, [failAt, failAt + 16], [0, 1], {
                            extrapolateLeft: "clamp",
                            extrapolateRight: "clamp",
                          })
                        : 0,
                  }}
                >
                  {method.failure ?? ""}
                </div>
              </div>
              {index < WEIGHT_METHODS.length - 1 ? (
                <div
                  style={{
                    fontFamily: MONO,
                    fontSize: 44,
                    color: COLORS.textFaint,
                    paddingTop: 76,
                    opacity: interpolate(
                      frame,
                      [CARD_LIT[index + 1] - 14, CARD_LIT[index + 1] + 6],
                      [0.2, 1],
                      { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                    ),
                  }}
                >
                  →
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const LadderHeader: React.FC<{ children: React.ReactNode; align: "left" | "right" }> = ({
  children,
  align,
}) => (
  <div
    style={{
      boxSizing: "border-box",
      height: 46,
      fontFamily: MONO,
      fontSize: 23,
      letterSpacing: 1,
      whiteSpace: "nowrap",
      color: COLORS.textFaint,
      textAlign: align,
      borderBottom: `1px solid ${COLORS.edge}`,
    }}
  >
    {children}
  </div>
);

const RankRow: React.FC<{
  rank: number;
  peer: string;
  share: number;
  delta: number;
  side: "base" | "adjusted";
  opacity: number;
}> = ({ rank, peer, share, delta, side, opacity }) => {
  const moved = delta !== 0;
  const rankCell = (
    <div
      style={{
        fontFamily: MONO,
        fontSize: 34,
        color: moved ? COLORS.amber : COLORS.textFaint,
        width: 40,
        textAlign: side === "base" ? "right" : "left",
      }}
    >
      {rank}
    </div>
  );

  return (
    <div
      style={{
        height: ROW_HEIGHT,
        display: "flex",
        alignItems: "center",
        justifyContent: side === "base" ? "flex-end" : "flex-start",
        gap: 26,
        opacity,
      }}
    >
      {side === "adjusted" ? rankCell : null}
      <div
        style={{
          fontFamily: MONO,
          fontSize: 34,
          color: moved ? COLORS.text : COLORS.textDim,
          width: 190,
          textAlign: side === "base" ? "right" : "left",
        }}
      >
        {peer}
      </div>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 28,
          color: COLORS.textFaint,
          width: 130,
          textAlign: "right",
        }}
      >
        {share.toFixed(2)}%
      </div>
      {side === "base" ? rankCell : null}
      {side === "adjusted" ? (
        <div
          style={{
            fontFamily: MONO,
            fontSize: 26,
            color: COLORS.amber,
            width: 70,
            opacity: moved ? 1 : 0,
          }}
        >
          {delta > 0 ? `+${delta}` : delta}
        </div>
      ) : null}
    </div>
  );
};

const RankLadder: React.FC = () => {
  const frame = useCurrentFrame();
  const byBase = [...PEERS].sort((a, b) => a.baseRank - b.baseRank);
  const byAdjusted = [...PEERS].sort((a, b) => a.adjustedRank - b.adjustedRank);
  const height = ROW_HEIGHT * PEERS.length;
  const rowCenter = (index: number) => index * ROW_HEIGHT + ROW_HEIGHT / 2;

  const swapPairs = byBase
    .filter((peer) => peer.rankDelta !== 0)
    .map((peer) => ({
      peer: peer.name,
      from: rowCenter(peer.baseRank - 1),
      to: rowCenter(peer.adjustedRank - 1),
    }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 30 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 26 }}>
        <div style={{ fontFamily: MONO, fontSize: 46, color: COLORS.text }}>
          Rank Changes
        </div>
        <div
          style={{
            fontFamily: MONO,
            fontSize: SIZES.micro,
            letterSpacing: 3,
            textTransform: "uppercase",
            color: COLORS.textFaint,
          }}
        >
          workbook sheet · one row per peer
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "flex-start" }}>
        <div style={{ width: 600, display: "flex", flexDirection: "column" }}>
          <LadderHeader align="right">Peer · Base_Share_% · Base_Rank</LadderHeader>
          {byBase.map((peer, index) => (
            <RankRow
              key={peer.name}
              rank={peer.baseRank}
              peer={peer.name}
              share={peer.baseSharePct}
              delta={peer.rankDelta}
              side="base"
              opacity={interpolate(frame, [index * 5, index * 5 + 16], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              })}
            />
          ))}
        </div>

        <svg
          width={CONNECTOR_WIDTH}
          height={height}
          viewBox={`0 0 ${CONNECTOR_WIDTH} ${height}`}
          style={{ marginTop: 46 }}
        >
          {byBase
            .filter((peer) => peer.rankDelta === 0)
            .map((peer) => (
              <line
                key={peer.name}
                x1={0}
                y1={rowCenter(peer.baseRank - 1)}
                x2={CONNECTOR_WIDTH}
                y2={rowCenter(peer.adjustedRank - 1)}
                stroke={COLORS.edge}
                strokeWidth={2}
                opacity={interpolate(frame, [20, 44], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                })}
              />
            ))}
          {swapPairs.map((swap, index) => {
            const pathLength = 320;
            const drawAt = 40 + Math.floor(index / 2) * 30;
            const progress = interpolate(frame, [drawAt, drawAt + 24], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.33, 0, 0.67, 1),
            });
            return (
              <path
                key={swap.peer}
                d={`M 0,${swap.from} C ${CONNECTOR_WIDTH / 2},${swap.from} ${
                  CONNECTOR_WIDTH / 2
                },${swap.to} ${CONNECTOR_WIDTH},${swap.to}`}
                fill="none"
                stroke={COLORS.amber}
                strokeWidth={3}
                strokeDasharray={pathLength}
                strokeDashoffset={pathLength * (1 - progress)}
              />
            );
          })}
        </svg>

        <div style={{ width: 600, display: "flex", flexDirection: "column" }}>
          <LadderHeader align="left">Adjusted_Rank · Adjusted_Share_% · Delta</LadderHeader>
          {byAdjusted.map((peer, index) => (
            <RankRow
              key={peer.name}
              rank={peer.adjustedRank}
              peer={peer.name}
              share={peer.adjustedSharePct}
              delta={peer.rankDelta}
              side="adjusted"
              opacity={interpolate(frame, [index * 5, index * 5 + 16], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              })}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export const S05WeightsSolved: React.FC = () => {
  return (
    <SceneFrame kicker="How the weights are solved">
      <Sequence name="Fallback chain" durationInFrames={LADDER_CUT} layout="none">
        <MethodCards />
      </Sequence>
      <Sequence name="Rank Changes" from={LADDER_CUT} layout="none">
        <RankLadder />
      </Sequence>
    </SceneFrame>
  );
};
