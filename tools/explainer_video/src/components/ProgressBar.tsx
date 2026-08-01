import { useCurrentFrame } from "remotion";
import { COLORS } from "../theme";
import { SCENES, TOTAL_FRAMES, WIDTH } from "../timeline";

/**
 * A four-and-a-half minute walkthrough needs to tell the viewer where they are.
 * Chapter ticks sit under a plain progress line at the top of the frame.
 */
export const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();
  const chapterStarts = SCENES.filter(
    (scene, index) => index > 0 && scene.chapter !== SCENES[index - 1].chapter,
  );

  return (
    <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 5 }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundColor: "rgba(163, 174, 180, 0.10)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: (frame / TOTAL_FRAMES) * WIDTH,
          backgroundColor: COLORS.accent,
          opacity: 0.75,
        }}
      />
      {chapterStarts.map((scene) => (
        <div
          key={scene.id}
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: (scene.start / TOTAL_FRAMES) * WIDTH,
            width: 2,
            backgroundColor: COLORS.bg,
          }}
        />
      ))}
    </div>
  );
};
