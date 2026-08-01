import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { DEMO_CAP_PCT, Peer } from "../content/facts";
import { MONO } from "../fonts";
import { COLORS } from "../theme";

const CHART = {
  width: 1640,
  height: 470,
  left: 40,
  right: 1600,
  baseline: 392,
  maxHeight: 320,
  barWidth: 150,
};

type Props = {
  peers: Peer[];
  /** Which share each bar shows. */
  mode: "base" | "adjusted";
  /** Frame the bars start growing. */
  startFrame?: number;
  /** Frame the cap line is drawn. */
  capFrame?: number;
};

const DASH_LENGTH = 16;
const DASH_STEP = 28;

export const ShareChart: React.FC<Props> = ({
  peers,
  mode,
  startFrame = 0,
  capFrame = 40,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const shareOf = (peer: Peer) =>
    mode === "base" ? peer.baseSharePct : peer.adjustedSharePct;
  const scaleMax = Math.max(...peers.map(shareOf), DEMO_CAP_PCT * 1.35);
  const step = (CHART.right - CHART.left) / peers.length;
  const capY = CHART.baseline - (DEMO_CAP_PCT / scaleMax) * CHART.maxHeight;
  const lineLength = CHART.right - CHART.left;
  const lineProgress = interpolate(frame, [capFrame, capFrame + 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.33, 0, 0.67, 1),
  });

  return (
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

      {peers.map((peer, index) => {
        const share = shareOf(peer);
        const breaches = share > DEMO_CAP_PCT;
        const grow = spring({
          frame: frame - startFrame - index * 4,
          fps,
          config: { damping: 200, mass: breaches ? 1.8 : 1 },
        });
        const height = (share / scaleMax) * CHART.maxHeight * grow;
        const x = CHART.left + index * step + (step - CHART.barWidth) / 2;
        const y = CHART.baseline - height;

        return (
          <g key={peer.name}>
            <rect
              x={x}
              y={y}
              width={CHART.barWidth}
              height={Math.max(height, 0)}
              fill={
                breaches ? "rgba(230, 148, 136, 0.28)" : "rgba(151, 187, 157, 0.22)"
              }
              stroke={breaches ? COLORS.warn : COLORS.good}
              strokeWidth={breaches ? 2 : 1}
            />
            <text
              x={x + CHART.barWidth / 2}
              y={y - 16}
              textAnchor="middle"
              fill={breaches ? COLORS.warn : COLORS.text}
              fontFamily={MONO}
              fontSize={30}
              opacity={grow}
            >
              {`${share.toFixed(1)}%`}
            </text>
            <text
              x={x + CHART.barWidth / 2}
              y={CHART.baseline + 42}
              textAnchor="middle"
              fill={COLORS.textDim}
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
            y1={capY}
            x2={CHART.left + dashStart + DASH_LENGTH}
            y2={capY}
            stroke={COLORS.amber}
            strokeWidth={3}
            opacity={reveal}
          />
        );
      })}
      <text
        x={CHART.right}
        y={capY - 18}
        textAnchor="end"
        fill={COLORS.amber}
        fontFamily={MONO}
        fontSize={28}
        opacity={interpolate(frame, [capFrame + 20, capFrame + 38], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })}
      >
        {`6/30 concentration cap · ${DEMO_CAP_PCT}%`}
      </text>
    </svg>
  );
};
