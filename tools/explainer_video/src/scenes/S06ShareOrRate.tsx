import { Easing, interpolate, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import { MODE_PANELS } from "../data/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

export const S06ShareOrRate: React.FC = () => {
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <SceneFrame kicker="Share or rate">
      <div
        style={{
          display: "flex",
          gap: 60,
          opacity: enter,
          translate: interpolate(enter, [0, 1], ["0px 22px", "0px 0px"]),
        }}
      >
        {MODE_PANELS.map((panel) => (
          <div
            key={panel.mode}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              gap: 34,
              padding: "48px 52px",
              minHeight: 420,
              borderRadius: 12,
              backgroundColor: COLORS.panel,
              border: `1px solid ${COLORS.edge}`,
            }}
          >
            <div
              style={{
                fontFamily: MONO,
                fontSize: 78,
                fontWeight: 500,
                color: COLORS.accent,
              }}
            >
              {panel.mode}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14, flex: 1 }}>
              {panel.flags.map((flag) => (
                <div
                  key={flag}
                  style={{
                    fontFamily: MONO,
                    fontSize: SIZES.mono,
                    color: COLORS.text,
                  }}
                >
                  {flag}
                </div>
              ))}
            </div>
            <div
              style={{
                paddingTop: 26,
                borderTop: `1px solid ${COLORS.edge}`,
                fontFamily: SANS,
                fontSize: SIZES.body,
                color: COLORS.textDim,
              }}
            >
              {panel.result}
            </div>
          </div>
        ))}
      </div>
    </SceneFrame>
  );
};
