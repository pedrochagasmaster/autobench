import { loadFont as loadTerminalFont } from "@remotion/google-fonts/FiraCode";
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

// Textual exports its screenshots against Fira Code and positions every run of
// text at an absolute x. A substituted font would shear the box drawing apart,
// so the real family has to be resident before the first frame is painted.
const terminal = loadTerminalFont("normal", {
  weights: ["400", "700"],
  subsets: ["latin"],
});

// Typing animations measure text every frame, so the families have to be
// resident before the first frame is painted or the layout reflows mid-render.
const fontHandle = delayRender("Loading IBM Plex and Fira Code");

Promise.all([mono.waitUntilDone(), sans.waitUntilDone(), terminal.waitUntilDone()])
  .then(() => continueRender(fontHandle))
  .catch((err) => cancelRender(err));

export const MONO = mono.fontFamily;
export const SANS = sans.fontFamily;
export const TERMINAL = terminal.fontFamily;
