import raw from "../../public/tui/manifest.json";

/**
 * Screenshots of the real TUI, produced by `scripts/capture_tui.py`.
 *
 * They are generated rather than committed, so run
 * `npm run assets` before the first render.
 */
export type TuiRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type TuiStep = {
  slug: string;
  file: string;
  caption: string;
  highlights: TuiRect[];
};

export type TuiManifest = {
  columns: number;
  rows: number;
  width: number;
  height: number;
  steps: TuiStep[];
};

const manifest = raw as TuiManifest;

export const tuiStepIndex = (slug: string): number => {
  const index = manifest.steps.findIndex((step) => step.slug === slug);
  if (index < 0) {
    throw new Error(
      `No captured TUI step named "${slug}". Re-run scripts/capture_tui.py.`,
    );
  }
  return index;
};

export default manifest;
