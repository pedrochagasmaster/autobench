import React from "react";
import {
  AbsoluteFill,
  Audio,
  Composition,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";

import { SceneFade } from "./components";
import { fontsReady } from "./fonts";
import { COLORS } from "./theme";
import { FeatureTriptych } from "./scenes/FeatureTriptych";
import { Hook } from "./scenes/Hook";
import { Outro } from "./scenes/Outro";
import { PrivacyRules } from "./scenes/PrivacyRules";
import { TerminalScene } from "./scenes/TerminalScene";
import { TitleReveal } from "./scenes/TitleReveal";
import { TuiShowcase } from "./scenes/TuiShowcase";
import { Verdict } from "./scenes/Verdict";

void fontsReady;

const FPS = 30;

const TIMELINE = [
  { component: Hook, duration: 280 },
  { component: TitleReveal, duration: 170 },
  { component: TerminalScene, duration: 330 },
  { component: TuiShowcase, duration: 315 },
  { component: PrivacyRules, duration: 200 },
  { component: FeatureTriptych, duration: 168 },
  { component: Verdict, duration: 175 },
  { component: Outro, duration: 220 },
] as const;

const TOTAL = TIMELINE.reduce((sum, s) => sum + s.duration, 0);

const Promo: React.FC = () => {
  const frame = useCurrentFrame();
  const masterFade = interpolate(frame, [TOTAL - 30, TOTAL - 4], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  let offset = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      <AbsoluteFill style={{ opacity: masterFade }}>
        {TIMELINE.map((scene, i) => {
          const from = offset;
          offset += scene.duration;
          const Component = scene.component;
          return (
            <Sequence key={i} from={from} durationInFrames={scene.duration}>
              <SceneFade durationInFrames={scene.duration}>
                <Component />
              </SceneFade>
            </Sequence>
          );
        })}
      </AbsoluteFill>
      <Audio src={staticFile("audio/soundtrack.wav")} volume={0.85} />
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="AutobenchPromo"
    component={Promo}
    durationInFrames={TOTAL}
    fps={FPS}
    width={1920}
    height={1080}
  />
);
