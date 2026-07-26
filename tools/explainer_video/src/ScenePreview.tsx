import { AbsoluteFill } from "remotion";
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

/**
 * One composition per scene so a single scene can be rendered as a still or a
 * short clip while iterating, without waiting on the full 113 seconds.
 */
export const SCENE_COMPONENTS: Record<string, React.ReactNode> = {
  s01: <S01OnePeerIsTheBenchmark />,
  s02: <S02Title />,
  s03: <S03WhatItComputes />,
  s04: <S04RulePicksItself showControlReference />,
  s05: <S05WeightsSolved />,
  s06: <S06ShareOrRate />,
  s07: <S07WhatLandsOnDisk />,
  s08: <S08BeforeAndAfter />,
  s09: <S09PresetsAndLean />,
  s10: <S10ThreeWaysIn />,
  s11: <S11GettingStarted />,
  s12: <S12Outro />,
};

export const ScenePreview: React.FC<{ sceneId: string }> = ({ sceneId }) => {
  return (
    <AbsoluteFill>
      <Backdrop />
      {SCENE_COMPONENTS[sceneId]}
      <Narration forceSceneId={sceneId} />
    </AbsoluteFill>
  );
};
