import { loadFont as loadMonoFont } from "@remotion/google-fonts/IBMPlexMono";
import { loadFont as loadSansFont } from "@remotion/google-fonts/IBMPlexSans";
import { cancelRender, continueRender, delayRender } from "remotion";

const mono = loadMonoFont("normal", {
  weights: ["400", "500", "600"],
  subsets: ["latin"],
});

const sans = loadSansFont("normal", {
  weights: ["400", "500", "600"],
  subsets: ["latin"],
});

// Typing animations measure text every frame, so both families have to be
// resident before the first frame is painted or the layout reflows mid-render.
const fontHandle = delayRender("Loading IBM Plex Mono and IBM Plex Sans");

Promise.all([mono.waitUntilDone(), sans.waitUntilDone()])
  .then(() => continueRender(fontHandle))
  .catch((err) => cancelRender(err));

export const MONO = mono.fontFamily;
export const SANS = sans.fontFamily;
