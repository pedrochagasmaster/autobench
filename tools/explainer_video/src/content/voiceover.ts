import chapterNarration from "./narration.json";
import manifest from "./tuiManifest";

/**
 * Narration, written to teach rather than to sell, and kept short enough to be
 * read on screen at the pace the scene holds for.
 *
 * The chapter lines live in `narration.json` because `scripts/make_voiceover.py`
 * reads the same file to synthesise the voice track; the walkthrough lines come
 * from `scripts/capture_tui.py` via the capture manifest. Neither the caption
 * nor the spoken line can drift from the step it describes.
 */
export const NARRATION: Record<string, string | null> = {
  s01: null,
  ...(chapterNarration as Record<string, string>),
  ...Object.fromEntries(
    manifest.steps.map((step, index) => [
      `t${String(index).padStart(2, "0")}`,
      step.caption,
    ]),
  ),
};
