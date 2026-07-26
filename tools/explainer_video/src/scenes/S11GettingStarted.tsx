import { interpolate, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import { Typewriter } from "../components/Typewriter";
import { INSTALL_BLOCKS } from "../data/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

// Typing all six commands at the scripted 2 frames per character would run past
// the end of the scene, leaving no room for the closing cursor hold.
const TYPE_SPEED = 1.6;
const BLOCK_GAP = 6;
const COMMAND_GAP = 2;

/** Each command types out after the previous one has finished. */
const commandStarts = (): number[][] => {
  const starts: number[][] = [];
  let cursor = 0;
  INSTALL_BLOCKS.forEach((block, blockIndex) => {
    if (blockIndex > 0) {
      cursor += BLOCK_GAP;
    }
    starts.push(
      block.commands.map((command) => {
        const start = cursor;
        cursor += command.length * TYPE_SPEED + COMMAND_GAP;
        return start;
      }),
    );
  });
  return starts;
};

const STARTS = commandStarts();
const EDGE_BLOCK_FROM = STARTS[1][0];

export const S11GettingStarted: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s11">
      <div style={{ display: "flex", gap: 80, alignItems: "flex-start" }}>
        {INSTALL_BLOCKS.map((block, blockIndex) => {
          const isLocal = blockIndex === 0;
          const fade = isLocal
            ? interpolate(frame, [EDGE_BLOCK_FROM, EDGE_BLOCK_FROM + 24], [1, 0.7], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              })
            : interpolate(frame, [EDGE_BLOCK_FROM - 20, EDGE_BLOCK_FROM], [0.25, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });

          return (
            <div
              key={block.title}
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                gap: 26,
                opacity: fade,
              }}
            >
              <div
                style={{
                  fontFamily: SANS,
                  fontSize: SIZES.lead,
                  color: COLORS.text,
                }}
              >
                {block.title}
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 18,
                  padding: "34px 34px",
                  borderRadius: 10,
                  backgroundColor: COLORS.panel,
                  border: `1px solid ${COLORS.edge}`,
                  minHeight: 320,
                }}
              >
                {block.commands.map((command, commandIndex) => {
                  const startFrame = STARTS[blockIndex][commandIndex];
                  const isFinal =
                    blockIndex === INSTALL_BLOCKS.length - 1 &&
                    commandIndex === block.commands.length - 1;
                  return (
                    <div
                      key={command}
                      style={{
                        display: "flex",
                        gap: 16,
                        opacity: frame >= startFrame ? 1 : 0,
                      }}
                    >
                      <span
                        style={{
                          fontFamily: MONO,
                          fontSize: SIZES.monoSmall,
                          color: COLORS.textFaint,
                        }}
                      >
                        $
                      </span>
                      <Typewriter
                        text={command}
                        startFrame={startFrame}
                        framesPerChar={TYPE_SPEED}
                        cursor={isFinal ? "blink" : "none"}
                        style={{
                          fontFamily: MONO,
                          fontSize: SIZES.monoSmall,
                          color: isFinal ? COLORS.accent : COLORS.text,
                        }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </SceneFrame>
  );
};
