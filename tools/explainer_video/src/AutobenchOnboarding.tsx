import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import React from "react";
import { AbsoluteFill, Audio, interpolate, Sequence, staticFile } from "remotion";
import { HAS_VOICEOVER, voiceClip } from "./content/voiceoverManifest";
import { Backdrop } from "./components/Backdrop";
import { Narration } from "./components/Narration";
import { ProgressBar } from "./components/ProgressBar";
import {
  S01Title,
  S02Problem,
  S03Balanced,
  S04TargetMode,
  S05RunPath,
} from "./scenes/Intro";
import {
  S06FirstAccess,
  S07DailyWorkflow,
  S08InputContract,
  S09FirstFailures,
  S10PrivacyRules,
} from "./scenes/SetupAndPrepare";
import { TuiWalkthrough } from "./scenes/TuiWalkthrough";
import {
  S11Cli,
  S12Checks,
  S13Workbook,
  S14WeightMethods,
  S15Contracts,
  S16Presets,
  S17Troubleshooting,
  S18GoDeeper,
} from "./scenes/Verify";
import { SCENES, TOTAL_FRAMES, TRANSITION_FRAMES, VO_LEAD_FRAMES } from "./timeline";

export type OnboardingProps = {
  /**
   * Names the internal control under the privacy rule table. Keep it on for
   * internal distribution; turn it off for anything leaving the organisation.
   */
  showControlReference: boolean;
  showNarration: boolean;
  showProgress: boolean;
  /** Bed level with no voice track; the bed ducks when narration is present. */
  musicGain: number;
  voiceGain: number;
};

/** How far the bed drops under the narration. */
const MUSIC_DUCK = 0.42;

const chapterScenes = (showControlReference: boolean): Record<string, React.ReactNode> => ({
  s01: <S01Title />,
  s02: <S02Problem />,
  s03: <S03Balanced />,
  s04: <S04TargetMode />,
  s05: <S05RunPath />,
  s06: <S06FirstAccess />,
  s07: <S07DailyWorkflow />,
  s08: <S08InputContract />,
  s09: <S09FirstFailures />,
  s10: <S10PrivacyRules showControlReference={showControlReference} />,
  s11: <S11Cli />,
  s12: <S12Checks />,
  s13: <S13Workbook />,
  s14: <S14WeightMethods />,
  s15: <S15Contracts />,
  s16: <S16Presets />,
  s17: <S17Troubleshooting />,
  s18: <S18GoDeeper />,
});

/** Music comes up under the title card and tails out over the last frames. */
const MUSIC_IN = SCENES[0].start;
const MUSIC_OUT_START = TOTAL_FRAMES - 60;

export const AutobenchOnboarding: React.FC<OnboardingProps> = ({
  showControlReference,
  showNarration,
  showProgress,
  musicGain,
  voiceGain,
}) => {
  const scenes = chapterScenes(showControlReference);
  const bedGain = HAS_VOICEOVER ? musicGain * MUSIC_DUCK : musicGain;

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
              {scene.tuiStep === undefined ? (
                scenes[scene.id]
              ) : (
                <TuiWalkthrough sceneId={scene.id} />
              )}
            </TransitionSeries.Sequence>
            {index < SCENES.length - 1 && !scene.hardCutAfter ? (
              <TransitionSeries.Transition
                presentation={fade()}
                timing={linearTiming({
                  durationInFrames: scene.transitionFrames ?? TRANSITION_FRAMES,
                })}
              />
            ) : null}
          </React.Fragment>
        ))}
      </TransitionSeries>
      {showNarration ? <Narration /> : null}
      {showProgress ? <ProgressBar /> : null}
      {SCENES.map((scene) => {
        const clip = voiceClip(scene.id);
        if (!clip) {
          return null;
        }
        return (
          <Sequence
            key={`vo-${scene.id}`}
            name={`voice — ${scene.id}`}
            from={scene.start + VO_LEAD_FRAMES}
            durationInFrames={Math.ceil(clip.seconds * 30) + 2}
            layout="none"
          >
            <Audio src={staticFile(clip.file)} volume={voiceGain} />
          </Sequence>
        );
      })}
      <Audio
        src={staticFile("music_bed.wav")}
        volume={(f) =>
          interpolate(
            f,
            [MUSIC_IN, MUSIC_IN + 60, MUSIC_OUT_START, TOTAL_FRAMES],
            [0, bedGain, bedGain, 0],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
          )
        }
      />
    </AbsoluteFill>
  );
};
