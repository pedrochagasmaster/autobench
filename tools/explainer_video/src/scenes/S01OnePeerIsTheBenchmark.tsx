import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import {
  DEMO_CATEGORY,
  PEER_COUNT,
  PEERS,
  TOP_PEER,
  TOP_PEER_SHARE_PCT,
  VOLUME_WEIGHTED_AVERAGE,
} from "../data/facts";
import { MONO, SANS } from "../fonts";
import { formatThousands } from "../format";
import { COLORS, SIZES } from "../theme";

const CHART = {
  width: 1640,
  height: 540,
  left: 40,
  right: 1600,
  baseline: 452,
  maxBarHeight: 384,
  barWidth: 138,
};

const DASH_LENGTH = 16;
const DASH_STEP = 28;

const AVERAGE_LINE_FROM = 90;
const PULSE_FROM = 130;
const CAPTION_FROM = 142;

const step = (CHART.right - CHART.left) / PEER_COUNT;
const barX = (index: number) =>
  CHART.left + index * step + (step - CHART.barWidth) / 2;

const maxVolume = Math.max(...PEERS.map((peer) => peer.volume));

export const S01OnePeerIsTheBenchmark: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const averageY =
    CHART.baseline - (VOLUME_WEIGHTED_AVERAGE / maxVolume) * CHART.maxBarHeight;
  const lineLength = CHART.right - CHART.left;
  const lineProgress = interpolate(
    frame,
    [AVERAGE_LINE_FROM, AVERAGE_LINE_FROM + 30],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.33, 0, 0.67, 1),
    },
  );
  const pulse = interpolate(frame, [PULSE_FROM, PULSE_FROM + 12, PULSE_FROM + 30], [0, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <SceneFrame sceneId="s01">
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <div
          style={{
            fontFamily: MONO,
            fontSize: SIZES.micro,
            letterSpacing: 2,
            color: COLORS.textFaint,
          }}
        >
          {`card_type = ${DEMO_CATEGORY.cardType} · channel = ${DEMO_CATEGORY.channel} · metric = ${DEMO_CATEGORY.metric}`}
        </div>

        <svg
          width={CHART.width}
          height={CHART.height}
          viewBox={`0 0 ${CHART.width} ${CHART.height}`}
        >
          <line
            x1={CHART.left}
            y1={CHART.baseline}
            x2={CHART.right}
            y2={CHART.baseline}
            stroke={COLORS.edgeBright}
            strokeWidth={2}
          />

          {PEERS.map((peer, index) => {
            const isTop = peer.name === TOP_PEER.name;
            const delay = isTop ? 24 : index * 4;
            const grow = spring({
              frame: frame - delay,
              fps,
              config: isTop
                ? { damping: 200, mass: 2.4, stiffness: 70 }
                : { damping: 200, mass: 1 },
            });
            const height = (peer.volume / maxVolume) * CHART.maxBarHeight * grow;
            const x = barX(index);
            const y = CHART.baseline - height;

            return (
              <g key={peer.name}>
                <rect
                  x={x}
                  y={y}
                  width={CHART.barWidth}
                  height={Math.max(height, 0)}
                  fill={isTop ? "rgba(143, 179, 212, 0.34)" : "rgba(163, 174, 180, 0.16)"}
                  stroke={isTop ? COLORS.accent : COLORS.edgeBright}
                  strokeWidth={isTop ? 2 : 1}
                />
                {isTop ? (
                  <rect
                    x={x - 8}
                    y={y - 8}
                    width={CHART.barWidth + 16}
                    height={Math.max(height, 0) + 16}
                    fill="none"
                    stroke={COLORS.accent}
                    strokeWidth={3}
                    opacity={pulse * 0.85}
                  />
                ) : null}
                <text
                  x={x + CHART.barWidth / 2}
                  y={y - 18}
                  textAnchor="middle"
                  fill={isTop ? COLORS.text : COLORS.textFaint}
                  fontFamily={MONO}
                  fontSize={26}
                  opacity={grow}
                >
                  {formatThousands(peer.volume)}
                </text>
                <text
                  x={x + CHART.barWidth / 2}
                  y={CHART.baseline + 42}
                  textAnchor="middle"
                  fill={isTop ? COLORS.text : COLORS.textDim}
                  fontFamily={MONO}
                  fontSize={28}
                >
                  {peer.name}
                </text>
              </g>
            );
          })}

          {Array.from({ length: Math.floor(lineLength / DASH_STEP) }).map((_, index) => {
            const dashStart = index * DASH_STEP;
            const reveal = interpolate(
              lineProgress * lineLength,
              [dashStart, dashStart + DASH_STEP],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            );
            return (
              <line
                key={`dash-${index}`}
                x1={CHART.left + dashStart}
                y1={averageY}
                x2={CHART.left + dashStart + DASH_LENGTH}
                y2={averageY}
                stroke={COLORS.warn}
                strokeWidth={3}
                opacity={reveal}
              />
            );
          })}
          <text
            x={CHART.right}
            y={averageY - 20}
            textAnchor="end"
            fill={COLORS.warn}
            fontFamily={MONO}
            fontSize={28}
            opacity={interpolate(
              frame,
              [AVERAGE_LINE_FROM + 24, AVERAGE_LINE_FROM + 42],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            )}
          >
            peer average, volume-weighted
          </text>
        </svg>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            fontFamily: SANS,
            fontSize: SIZES.body,
            color: COLORS.text,
            opacity: interpolate(frame, [CAPTION_FROM, CAPTION_FROM + 20], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          {`1 of ${PEER_COUNT} peers = ${Math.round(TOP_PEER_SHARE_PCT)}% of category volume`}
        </div>
      </div>
    </SceneFrame>
  );
};
