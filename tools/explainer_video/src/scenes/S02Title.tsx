import { AbsoluteFill } from "remotion";
import { Wordmark } from "../components/Wordmark";
import { CONFIG_MODEL, TAGLINE } from "../data/facts";
import { localFrame } from "../timeline";

const SUBTITLE_FROM = localFrame("s02", 225);

export const S02Title: React.FC = () => {
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <Wordmark
        framesPerChar={3}
        subtitle={TAGLINE}
        subtitleFrom={SUBTITLE_FROM}
        footnote={CONFIG_MODEL}
      />
    </AbsoluteFill>
  );
};
