import { AbsoluteFill } from "remotion";
import { Backdrop } from "./components/Backdrop";
import { Narration } from "./components/Narration";
import { S01Title, S02Problem, S03Balanced, S04TargetMode, S05RunPath } from "./scenes/Intro";
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
import { sceneById } from "./timeline";

const CHAPTERS: Record<string, React.ReactNode> = {
  s01: <S01Title />,
  s02: <S02Problem />,
  s03: <S03Balanced />,
  s04: <S04TargetMode />,
  s05: <S05RunPath />,
  s06: <S06FirstAccess />,
  s07: <S07DailyWorkflow />,
  s08: <S08InputContract />,
  s09: <S09FirstFailures />,
  s10: <S10PrivacyRules showControlReference />,
  s11: <S11Cli />,
  s12: <S12Checks />,
  s13: <S13Workbook />,
  s14: <S14WeightMethods />,
  s15: <S15Contracts />,
  s16: <S16Presets />,
  s17: <S17Troubleshooting />,
  s18: <S18GoDeeper />,
};

/**
 * One composition per scene so a single scene can be rendered as a still or a
 * short clip while iterating, without waiting on the whole walkthrough.
 */
export const ScenePreview: React.FC<{ sceneId: string }> = ({ sceneId }) => {
  const scene = sceneById(sceneId);

  return (
    <AbsoluteFill>
      <Backdrop />
      {scene.tuiStep === undefined ? (
        CHAPTERS[sceneId]
      ) : (
        <TuiWalkthrough sceneId={sceneId} />
      )}
      <Narration forceSceneId={sceneId} />
    </AbsoluteFill>
  );
};
