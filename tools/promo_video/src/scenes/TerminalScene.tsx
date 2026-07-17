import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { Backdrop, RiseIn } from "../components";
import { COLORS, FONTS } from "../theme";

type Token = { text: string; color: string; weight?: number };

// The command, tokenized for prompt-style syntax colors.
const TOKENS: Token[] = [
  { text: "py ", color: "#7ee787" },
  { text: "benchmark.py ", color: COLORS.text },
  { text: "share ", color: "#ffa657", weight: 700 },
  { text: "--csv ", color: "#79c0ff" },
  { text: "issuers_q2.csv ", color: COLORS.text },
  { text: "--entity ", color: "#79c0ff" },
  { text: "Target ", color: COLORS.text },
  { text: "--metric ", color: "#79c0ff" },
  { text: "txn_cnt ", color: COLORS.text },
  { text: "--dimensions ", color: "#79c0ff" },
  { text: "card_type channel", color: COLORS.text },
];

const COMMAND_LENGTH = TOKENS.reduce((sum, t) => sum + t.text.length, 0);

// Real output lines from a gate_demo run, lightly trimmed to fit the frame.
const LOG_LINES: Array<{ text: string; color?: string; bold?: boolean }> = [
  { text: "INFO  Loaded 42 records with 5 columns" },
  { text: "INFO  Input validation passed with no issues." },
  { text: "INFO  Privacy rule: 6/30 · max concentration 30.0%" },
  { text: "INFO  Found 60 dimension/category combinations" },
  { text: "INFO  P1: multiplier=0.6517, max_adjusted_share=30.0000% [OK]" },
  { text: "INFO  P2: multiplier=1.0697, max_adjusted_share=19.8408% [OK]" },
  { text: "INFO  Global privacy weight optimization completed in 0.028s" },
  { text: "INFO  Report saved to: issuers_q2_share.xlsx" },
  { text: "" },
  { text: "SHARE ANALYSIS COMPLETE", bold: true },
  { text: "Compliance Verdict: fully_compliant", color: COLORS.green, bold: true },
];

const TYPE_START = 18;
const TYPE_FRAMES = 92;
const LOG_START = TYPE_START + TYPE_FRAMES + 16;
const LOG_STEP = 9;
const CAPTION_SWAP = LOG_START + LOG_STEP * LOG_LINES.length + 18;

/** Renders the typed portion of the command with syntax colors. */
const TypedCommand: React.FC<{ typed: number }> = ({ typed }) => {
  let consumed = 0;
  return (
    <>
      {TOKENS.map((token, i) => {
        const start = consumed;
        consumed += token.text.length;
        if (typed <= start) {
          return null;
        }
        const visible = token.text.slice(0, Math.max(0, typed - start));
        return (
          <span
            key={i}
            style={{ color: token.color, fontWeight: token.weight ?? 400 }}
          >
            {visible}
          </span>
        );
      })}
    </>
  );
};

/** macOS-style terminal window running a real Autobench CLI analysis. */
export const TerminalScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const typed = Math.round(
    interpolate(frame, [TYPE_START, TYPE_START + TYPE_FRAMES], [0, COMMAND_LENGTH], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const cursorOn = Math.floor(frame / 16) % 2 === 0;
  const visibleLogs = Math.max(0, Math.floor((frame - LOG_START) / LOG_STEP));
  const drift = interpolate(frame, [0, 12 * fps], [8, -16]);
  const settle = interpolate(frame, [0, 20], [0.985, 1], {
    extrapolateRight: "clamp",
    easing: (v) => 1 - Math.pow(1 - v, 3),
  });

  const captionA =
    interpolate(frame, [0, 14], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }) *
    interpolate(frame, [CAPTION_SWAP - 10, CAPTION_SWAP], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  const captionB = interpolate(
    frame,
    [CAPTION_SWAP + 2, CAPTION_SWAP + 16],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill>
      <Backdrop glow={0.7} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <div style={{ position: "relative", height: 110, marginBottom: 42 }}>
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              justifyContent: "center",
              opacity: captionA,
            }}
          >
            <RiseIn delay={0} duration={20}>
              <div
                style={{
                  fontFamily: FONTS.display,
                  fontWeight: 600,
                  fontSize: 76,
                  color: COLORS.text,
                  letterSpacing: "-0.03em",
                  whiteSpace: "nowrap",
                }}
              >
                One command.{" "}
                <span style={{ color: COLORS.textDim }}>Fully governed.</span>
              </div>
            </RiseIn>
          </div>
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              justifyContent: "center",
              opacity: captionB,
              transform: `translateY(${(1 - captionB) * 26}px)`,
            }}
          >
            <div
              style={{
                fontFamily: FONTS.display,
                fontWeight: 600,
                fontSize: 76,
                letterSpacing: "-0.03em",
                whiteSpace: "nowrap",
                color: COLORS.green,
              }}
            >
              Compliant{" "}
              <span style={{ color: COLORS.textDim }}>in 0.028 seconds.</span>
            </div>
          </div>
        </div>
        <div
          style={{
            width: 1480,
            transform: `translateY(${drift}px) scale(${settle})`,
            borderRadius: 22,
            background: "rgba(14, 14, 18, 0.94)",
            border: "1px solid rgba(255,255,255,0.09)",
            boxShadow:
              "0 60px 140px rgba(0,0,0,0.65), 0 0 120px rgba(90,90,255,0.10)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
              padding: "16px 20px",
              background: "rgba(255,255,255,0.045)",
              borderBottom: "1px solid rgba(255,255,255,0.06)",
            }}
          >
            {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
              <div
                key={c}
                style={{ width: 14, height: 14, borderRadius: 7, background: c }}
              />
            ))}
            <div
              style={{
                flex: 1,
                textAlign: "center",
                fontFamily: FONTS.display,
                fontWeight: 500,
                fontSize: 19,
                color: COLORS.textDim,
                marginRight: 60,
              }}
            >
              autobench — zsh
            </div>
          </div>
          <div
            style={{
              padding: "30px 38px 38px",
              fontFamily: FONTS.mono,
              fontSize: 24.5,
              lineHeight: 1.62,
              minHeight: 560,
            }}
          >
            <div style={{ whiteSpace: "pre-wrap" }}>
              <span style={{ color: COLORS.accentA, fontWeight: 700 }}>❯ </span>
              <TypedCommand typed={typed} />
              {typed < COMMAND_LENGTH && cursorOn ? (
                <span style={{ color: COLORS.text }}>▍</span>
              ) : null}
            </div>
            <div style={{ height: 12 }} />
            {LOG_LINES.slice(0, visibleLogs).map((line, i) => (
              <div
                key={i}
                style={{
                  color: line.color ?? "rgba(245,245,247,0.62)",
                  fontWeight: line.bold ? 700 : 400,
                }}
              >
                {line.text === "" ? "\u00a0" : line.text}
              </div>
            ))}
            {visibleLogs >= LOG_LINES.length && cursorOn ? (
              <span style={{ color: COLORS.text }}>▍</span>
            ) : null}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
