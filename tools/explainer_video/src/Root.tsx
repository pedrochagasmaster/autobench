import { Composition, Folder } from "remotion";
import { AutobenchExplainer } from "./AutobenchExplainer";
import { ScenePreview } from "./ScenePreview";
import { FPS, HEIGHT, SCENES, TOTAL_FRAMES, WIDTH } from "./timeline";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="AutobenchExplainer"
        component={AutobenchExplainer}
        durationInFrames={TOTAL_FRAMES}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{
          showControlReference: true,
          showNarration: true,
          musicGain: 0.34,
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
