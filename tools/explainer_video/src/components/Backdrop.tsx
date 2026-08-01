import { AbsoluteFill } from "remotion";
import { COLORS } from "../theme";
import { HEIGHT, WIDTH } from "../timeline";

const GRID_STEP = 60;

export const Backdrop: React.FC = () => {
  const columns = Math.floor(WIDTH / GRID_STEP);
  const rows = Math.floor(HEIGHT / GRID_STEP);

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
        {Array.from({ length: columns + 1 }).map((_, index) => (
          <line
            key={`column-${index}`}
            x1={index * GRID_STEP}
            y1={0}
            x2={index * GRID_STEP}
            y2={HEIGHT}
            stroke={COLORS.grid}
            strokeWidth={1}
          />
        ))}
        {Array.from({ length: rows + 1 }).map((_, index) => (
          <line
            key={`row-${index}`}
            x1={0}
            y1={index * GRID_STEP}
            x2={WIDTH}
            y2={index * GRID_STEP}
            stroke={COLORS.grid}
            strokeWidth={1}
          />
        ))}
      </svg>
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 50% 38%, rgba(143, 179, 212, 0.07) 0%, rgba(9, 14, 17, 0) 55%), linear-gradient(180deg, rgba(9, 14, 17, 0) 55%, ${COLORS.bgDeep} 100%)`,
        }}
      />
    </AbsoluteFill>
  );
};
