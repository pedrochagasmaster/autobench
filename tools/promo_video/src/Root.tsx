import React from "react";
import {
  AbsoluteFill,
  Audio,
  Composition,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";

import { FilmGrain, Vignette } from "./components";
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
const CROSSFADE = 15;

const TIMELINE = [
  { component: Hook, duration: 280 },
  { component: TitleReveal, duration: 170 },
  { component: TerminalScene, duration: 330 },
  { component: TuiShowcase, duration: 315 },
  { component: PrivacyRules, duration: 200 },
  { component: FeatureTriptych, duration: 168 },
  { component: Verdict, duration: 175 },
  { component: Outro, duration: 230 },
] as const;

// Scenes overlap by CROSSFADE frames, so the total is shorter than the sum.
const TOTAL =
  TIMELINE.reduce((sum, s) => sum + s.duration, 0) -
  CROSSFADE * (TIMELINE.length - 1);

/** Frame at which each scene starts, accounting for crossfade overlap. */
export const sceneStartFrame = (index: number): number =>
  TIMELINE.slice(0, index).reduce((sum, s) => sum + s.duration, 0) -
  CROSSFADE * index;

const Promo: React.FC = () => {
  const frame = useCurrentFrame();
  const masterFade =
    interpolate(frame, [0, 10], [0, 1], {
      extrapolateRight: "clamp",
    }) *
    interpolate(frame, [TOTAL - 28, TOTAL - 4], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      <AbsoluteFill style={{ opacity: masterFade }}>
        <TransitionSeries>
          {TIMELINE.flatMap((scene, i) => {
            const Component = scene.component;
            const parts = [
              <TransitionSeries.Sequence
                key={`scene-${i}`}
                durationInFrames={scene.duration}
              >
                <Component />
              </TransitionSeries.Sequence>,
            ];
            if (i < TIMELINE.length - 1) {
              parts.push(
                <TransitionSeries.Transition
                  key={`transition-${i}`}
                  presentation={fade()}
                  timing={linearTiming({ durationInFrames: CROSSFADE })}
                />
              );
            }
            return parts;
          })}
        </TransitionSeries>
        <Vignette />
        <FilmGrain />
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
