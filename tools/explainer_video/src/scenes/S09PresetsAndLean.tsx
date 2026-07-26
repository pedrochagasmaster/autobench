import { Easing, interpolate, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import { LEAN_CAPTION, LEAN_COMMAND, PRESETS } from "../data/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

const CYCLE_FRAMES = 30;
const CYCLE_END = CYCLE_FRAMES * PRESETS.length;
const GLOW_FROM = 60;
const GLOW_FRAMES = 96;

const highlightIndex = (frame: number): number =>
  frame >= CYCLE_END ? 0 : Math.floor(frame / CYCLE_FRAMES);

export const S09PresetsAndLean: React.FC = () => {
  const frame = useCurrentFrame();
  const active = highlightIndex(frame);
  const glow = interpolate(
    frame,
    [GLOW_FROM, GLOW_FROM + GLOW_FRAMES / 2, GLOW_FROM + GLOW_FRAMES],
    [0, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.4, 0, 0.6, 1),
    },
  );

  return (
    <SceneFrame sceneId="s09">
      <div style={{ display: "flex", gap: 90, alignItems: "flex-start" }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
          {PRESETS.map((preset, index) => {
            const isActive = index === active;
            return (
              <div
                key={preset.name}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: 30,
                  height: 88,
                  paddingLeft: 22,
                  marginLeft: -22,
                  borderRadius: 6,
                  backgroundColor: isActive ? "rgba(143, 179, 212, 0.14)" : "transparent",
                  borderLeft: `3px solid ${isActive ? COLORS.accent : "transparent"}`,
                  opacity: interpolate(frame, [index * 6, index * 6 + 18], [0, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  }),
                }}
              >
                <div
                  style={{
                    fontFamily: MONO,
                    fontSize: SIZES.mono,
                    color: isActive ? COLORS.accent : COLORS.textDim,
                    width: 460,
                  }}
                >
                  {preset.name}
                </div>
                <div
                  style={{
                    fontFamily: SANS,
                    fontSize: 28,
                    color: COLORS.textFaint,
                    whiteSpace: "nowrap",
                  }}
                >
                  {preset.note}
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ width: 640, display: "flex", flexDirection: "column", gap: 26 }}>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 10,
              padding: "38px 40px",
              borderRadius: 10,
              backgroundColor: COLORS.panel,
              border: `1px solid ${COLORS.edge}`,
            }}
          >
            {LEAN_COMMAND.map((line) => {
              const isLean = line.trim() === "--lean";
              return (
                <div
                  key={line}
                  style={{
                    fontFamily: MONO,
                    fontSize: SIZES.mono,
                    whiteSpace: "pre",
                    color: isLean ? COLORS.accent : COLORS.text,
                    textShadow: isLean
                      ? `0 0 ${18 * glow}px rgba(143, 179, 212, ${0.85 * glow})`
                      : "none",
                  }}
                >
                  {line}
                </div>
              );
            })}
          </div>
          <div
            style={{
              fontFamily: SANS,
              fontSize: SIZES.body,
              color: COLORS.good,
              paddingLeft: 4,
            }}
          >
            {LEAN_CAPTION}
          </div>
        </div>
      </div>
    </SceneFrame>
  );
};
