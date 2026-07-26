import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import React from "react";
import { AbsoluteFill, Audio, interpolate, staticFile } from "remotion";
import { Backdrop } from "./components/Backdrop";
import { Narration } from "./components/Narration";
import { S01OnePeerIsTheBenchmark } from "./scenes/S01OnePeerIsTheBenchmark";
import { S02Title } from "./scenes/S02Title";
import { S03WhatItComputes } from "./scenes/S03WhatItComputes";
import { S04RulePicksItself } from "./scenes/S04RulePicksItself";
import { S05WeightsSolved } from "./scenes/S05WeightsSolved";
import { S06ShareOrRate } from "./scenes/S06ShareOrRate";
import { S07WhatLandsOnDisk } from "./scenes/S07WhatLandsOnDisk";
import { S08BeforeAndAfter } from "./scenes/S08BeforeAndAfter";
import { S09PresetsAndLean } from "./scenes/S09PresetsAndLean";
import { S10ThreeWaysIn } from "./scenes/S10ThreeWaysIn";
import { S11GettingStarted } from "./scenes/S11GettingStarted";
import { S12Outro } from "./scenes/S12Outro";
import { SCENES, TOTAL_FRAMES, TRANSITION_FRAMES } from "./timeline";

export type ExplainerProps = {
  /**
   * Names the internal control under the scene 4 rule table. Keep it on for
   * internal distribution; turn it off for anything leaving the organisation.
   */
  showControlReference: boolean;
  showNarration: boolean;
  musicGain: number;
};

/** Music comes up under the title card, not under the opening argument. */
const MUSIC_IN = SCENES[1].start;
const MUSIC_OUT_START = TOTAL_FRAMES - 40;

export const AutobenchExplainer: React.FC<ExplainerProps> = ({
  showControlReference,
  showNarration,
  musicGain,
}) => {
  const scenes: React.ReactNode[] = [
    <S01OnePeerIsTheBenchmark />,
    <S02Title />,
    <S03WhatItComputes />,
    <S04RulePicksItself showControlReference={showControlReference} />,
    <S05WeightsSolved />,
    <S06ShareOrRate />,
    <S07WhatLandsOnDisk />,
    <S08BeforeAndAfter />,
    <S09PresetsAndLean />,
    <S10ThreeWaysIn />,
    <S11GettingStarted />,
    <S12Outro />,
  ];

  return (
    <AbsoluteFill>
      <Backdrop />
      <TransitionSeries>
        {SCENES.map((scene, index) => (
          <React.Fragment key={scene.id}>
            <TransitionSeries.Sequence
              name={`${scene.id} — ${scene.label}`}
              durationInFrames={scene.sequenceFrames}
            >
              {scenes[index]}
            </TransitionSeries.Sequence>
            {index < SCENES.length - 1 && !scene.hardCutAfter ? (
              <TransitionSeries.Transition
                presentation={fade()}
                timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
              />
            ) : null}
          </React.Fragment>
        ))}
      </TransitionSeries>
      {showNarration ? <Narration /> : null}
      <Audio
        src={staticFile("music_bed.wav")}
        volume={(f) =>
          interpolate(
            f,
            [MUSIC_IN, MUSIC_IN + 45, MUSIC_OUT_START, TOTAL_FRAMES],
            [0, musicGain, musicGain, 0],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
          )
        }
      />
    </AbsoluteFill>
  );
};
