import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { Backdrop, RiseIn } from "../components";
import { COLORS, FONTS } from "../theme";

const COMMAND =
  "py benchmark.py share --csv issuers_q2.csv --entity Target --metric txn_cnt --dimensions card_type channel";

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

/** macOS-style terminal window running a real Autobench CLI analysis. */
export const TerminalScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const typed = Math.round(
    interpolate(frame, [TYPE_START, TYPE_START + TYPE_FRAMES], [0, COMMAND.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const cursorOn = Math.floor(frame / 16) % 2 === 0;
  const visibleLogs = Math.max(0, Math.floor((frame - LOG_START) / LOG_STEP));
  const drift = interpolate(frame, [0, 12 * fps], [0, -14]);

  return (
    <AbsoluteFill>
      <Backdrop glow={0.7} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <RiseIn delay={0} duration={20}>
          <div
            style={{
              fontFamily: FONTS.display,
              fontWeight: 600,
              fontSize: 76,
              color: COLORS.text,
              letterSpacing: "-0.03em",
              marginBottom: 46,
              textAlign: "center",
            }}
          >
            One command.{" "}
            <span style={{ color: COLORS.textDim }}>Fully governed.</span>
          </div>
        </RiseIn>
        <div
          style={{
            width: 1480,
            transform: `translateY(${drift}px)`,
            borderRadius: 22,
            background: "rgba(16, 16, 20, 0.92)",
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
            <div style={{ color: COLORS.text, whiteSpace: "pre-wrap" }}>
              <span style={{ color: COLORS.accentA, fontWeight: 700 }}>❯ </span>
              {COMMAND.slice(0, typed)}
              {typed < COMMAND.length && cursorOn ? (
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
