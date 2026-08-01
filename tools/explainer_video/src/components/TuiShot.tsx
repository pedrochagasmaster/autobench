import { useEffect, useState } from "react";
import {
  cancelRender,
  continueRender,
  delayRender,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { COLORS } from "../theme";
import manifest from "../content/tuiManifest";

const svgCache = new Map<string, string>();

export type Rect = { x: number; y: number; width: number; height: number };

type Props = {
  /** Manifest step index. */
  step: number;
  /** Screen area the shot is fitted into. */
  frameWidth: number;
  frameHeight: number;
  /**
   * 1 fits the whole terminal. Larger values push in on the highlighted
   * widget so its text is readable at 1080p.
   */
  zoom?: number;
  /** Extra push-in across the scene, on top of `zoom`. */
  drift?: number;
};

const useSvg = (src: string): string | null => {
  const [svg, setSvg] = useState<string | null>(() => svgCache.get(src) ?? null);
  const [handle] = useState(() =>
    svgCache.has(src) ? null : delayRender(`Loading ${src}`),
  );

  useEffect(() => {
    if (handle === null) {
      return;
    }
    fetch(staticFile(src))
      .then((response) => response.text())
      .then((text) => {
        svgCache.set(src, text);
        setSvg(text);
        continueRender(handle);
      })
      .catch((error) => cancelRender(error));
  }, [src, handle]);

  return svg;
};

export const TuiShot: React.FC<Props> = ({
  step,
  frameWidth,
  frameHeight,
  zoom = 1,
  drift = 0,
}) => {
  const frame = useCurrentFrame();
  const entry = manifest.steps[step];
  const svg = useSvg(entry.file);

  // Contain: the larger ratio is the binding one, so scaling by its inverse
  // puts the whole terminal inside the frame.
  const baseScale = Math.min(frameWidth / manifest.width, frameHeight / manifest.height);
  const pushIn = interpolate(frame, [0, 120], [zoom, zoom + drift], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.33, 0, 0.67, 1),
  });
  const scale = baseScale * pushIn;

  const highlight = entry.highlights[0];
  // Centre on the highlighted widget when pushed in; otherwise centre the
  // whole terminal.
  const anchorX = highlight ? highlight.x + highlight.width / 2 : manifest.width / 2;
  const anchorY = highlight ? highlight.y + highlight.height / 2 : manifest.height / 2;
  const maxOffsetX = Math.max(0, (manifest.width * scale - frameWidth) / 2);
  const maxOffsetY = Math.max(0, (manifest.height * scale - frameHeight) / 2);
  const wantedX = (manifest.width / 2 - anchorX) * scale;
  const wantedY = (manifest.height / 2 - anchorY) * scale;
  const offsetX = Math.max(-maxOffsetX, Math.min(maxOffsetX, wantedX));
  const offsetY = Math.max(-maxOffsetY, Math.min(maxOffsetY, wantedY));

  const highlightIn = interpolate(frame, [10, 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <div
      style={{
        width: frameWidth,
        height: frameHeight,
        overflow: "hidden",
        borderRadius: 12,
        backgroundColor: "#1a1b26",
        border: `1px solid ${COLORS.edge}`,
        position: "relative",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          width: manifest.width,
          height: manifest.height,
          marginLeft: -manifest.width / 2,
          marginTop: -manifest.height / 2,
          translate: `${offsetX}px ${offsetY}px`,
          scale,
        }}
      >
        {svg ? (
          <div
            style={{ width: manifest.width, height: manifest.height }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : null}
        {entry.highlights.map((rect, index) => (
          <div
            key={`${entry.slug}-${index}`}
            style={{
              position: "absolute",
              left: rect.x - 6,
              top: rect.y - 6,
              width: rect.width + 12,
              height: rect.height + 12,
              borderRadius: 6,
              border: `3px solid ${COLORS.amber}`,
              backgroundColor: "rgba(216, 178, 106, 0.10)",
              opacity: highlightIn,
              scale: interpolate(highlightIn, [0, 1], [1.04, 1]),
            }}
          />
        ))}
      </div>
    </div>
  );
};

export const tuiStep = (step: number) => manifest.steps[step];
export const tuiStepCount = manifest.steps.length;
