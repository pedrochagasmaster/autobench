import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

import { FONTS } from "./theme";

export const fontsReady = Promise.all([
  loadFont({
    family: FONTS.display,
    url: staticFile("fonts/InterDisplay-Light.ttf"),
    weight: "300",
  }),
  loadFont({
    family: FONTS.display,
    url: staticFile("fonts/InterDisplay-Medium.ttf"),
    weight: "500",
  }),
  loadFont({
    family: FONTS.display,
    url: staticFile("fonts/InterDisplay-SemiBold.ttf"),
    weight: "600",
  }),
  loadFont({
    family: FONTS.display,
    url: staticFile("fonts/InterDisplay-Bold.ttf"),
    weight: "700",
  }),
  loadFont({
    family: FONTS.mono,
    url: staticFile("fonts/JetBrainsMono-Regular.ttf"),
    weight: "400",
  }),
  loadFont({
    family: FONTS.mono,
    url: staticFile("fonts/JetBrainsMono-Bold.ttf"),
    weight: "700",
  }),
]);
