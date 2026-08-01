import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Card, revealAt } from "../components/Blocks";
import { SceneFrame } from "../components/SceneFrame";
import { Wordmark } from "../components/Wordmark";
import {
  CONFIG_MODEL,
  DEMO_FILE,
  HEADLINE,
  PEERS,
  RUN_PATH,
  SUBHEAD,
  TARGET_MODES,
  TOP_PEER,
} from "../content/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";
import { ShareChart } from "./ShareChart";

export const S01Title: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <Wordmark
        framesPerChar={3}
        subtitle={HEADLINE}
        subtitleFrom={36}
        footnote={CONFIG_MODEL}
      />
      <div
        style={{
          marginTop: 30,
          fontFamily: SANS,
          fontSize: SIZES.body,
          color: COLORS.textFaint,
          opacity: revealAt(frame, 60),
        }}
      >
        {SUBHEAD}
      </div>
    </AbsoluteFill>
  );
};

const ChartCaption: React.FC<{
  frame: number;
  at: number;
  left: string;
  right: string;
  rightColor: string;
}> = ({ frame, at, left, right, rightColor }) => (
  <div
    style={{
      display: "flex",
      justifyContent: "space-between",
      alignItems: "baseline",
      gap: 40,
      opacity: revealAt(frame, at),
    }}
  >
    <div style={{ flex: 1, fontFamily: SANS, fontSize: SIZES.body, color: COLORS.text }}>
      {left}
    </div>
    <div
      style={{
        fontFamily: MONO,
        fontSize: SIZES.label,
        color: rightColor,
        whiteSpace: "nowrap",
      }}
    >
      {right}
    </div>
  </div>
);

const ChartLead: React.FC<{ text: string }> = ({ text }) => (
  <div
    style={{
      fontFamily: MONO,
      fontSize: SIZES.micro,
      letterSpacing: 2,
      color: COLORS.textFaint,
    }}
  >
    {text}
  </div>
);

export const S02Problem: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s02">
      <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
        <ChartLead text={`share of one category · the six peers in ${DEMO_FILE}`} />
        <ShareChart peers={PEERS} mode="base" capFrame={40} />
        <ChartCaption
          frame={frame}
          at={70}
          left={`${TOP_PEER.name} alone is ${TOP_PEER.baseSharePct.toFixed(0)}% of the category.`}
          right="over the cap · not publishable"
          rightColor={COLORS.warn}
        />
      </div>
    </SceneFrame>
  );
};

export const S03Balanced: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s03">
      <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
        <ChartLead text="the same category after privacy-constrained weighting" />
        <ShareChart peers={PEERS} mode="adjusted" capFrame={34} />
        <ChartCaption
          frame={frame}
          at={62}
          left="Dominant peers scaled down, smaller peers up, only where needed."
          right="every cut under the cap"
          rightColor={COLORS.good}
        />
      </div>
    </SceneFrame>
  );
};

export const S04TargetMode: React.FC = () => (
  <SceneFrame sceneId="s04">
    <div style={{ display: "flex", flexDirection: "column", gap: 36 }}>
      <div style={{ fontFamily: MONO, fontSize: SIZES.mono, color: COLORS.textDim }}>
        Target entity (blank = peer-only)
      </div>
      <div style={{ display: "flex", gap: 48 }}>
        {TARGET_MODES.map((mode, index) => (
          <Card
            key={mode.title}
            title={mode.title}
            body={mode.body}
            hint={mode.hint}
            startFrame={12 + index * 22}
            accent={index === 0}
          />
        ))}
      </div>
    </div>
  </SceneFrame>
);

export const S05RunPath: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s05">
      <div style={{ display: "flex", gap: 26 }}>
        {RUN_PATH.map((step, index) => {
          const appear = revealAt(frame, index * 18, 22);
          return (
            <div
              key={step.index}
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                gap: 16,
                padding: "34px 30px",
                borderRadius: 12,
                backgroundColor: COLORS.panel,
                border: `1px solid ${COLORS.edge}`,
                borderTop: `3px solid ${COLORS.accent}`,
                opacity: appear,
                translate: interpolate(appear, [0, 1], ["0px 16px", "0px 0px"]),
              }}
            >
              <div style={{ fontFamily: MONO, fontSize: 32, color: COLORS.accent }}>
                {step.index}
              </div>
              <div style={{ fontFamily: SANS, fontSize: 48, color: COLORS.text }}>
                {step.title}
              </div>
              <div style={{ fontFamily: SANS, fontSize: SIZES.label, color: COLORS.textDim }}>
                {step.body}
              </div>
            </div>
          );
        })}
      </div>
    </SceneFrame>
  );
};
