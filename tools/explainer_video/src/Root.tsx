import { Composition, Folder } from "remotion";
import { AutobenchOnboarding } from "./AutobenchOnboarding";
import { ScenePreview } from "./ScenePreview";
import { FPS, HEIGHT, SCENES, TOTAL_FRAMES, WIDTH } from "./timeline";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="AutobenchOnboarding"
        component={AutobenchOnboarding}
        durationInFrames={TOTAL_FRAMES}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{
          showControlReference: true,
          showNarration: true,
          showProgress: true,
          musicGain: 0.22,
        }}
      />
      <Folder name="Scenes">
        {SCENES.map((scene) => (
          <Composition
            key={scene.id}
            id={`Scene-${scene.id}`}
            component={ScenePreview}
            durationInFrames={scene.frames}
            fps={FPS}
            width={WIDTH}
            height={HEIGHT}
            defaultProps={{ sceneId: scene.id }}
          />
        ))}
      </Folder>
    </>
  );
};
