import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Callout, Card, CodeBlock, revealAt } from "../components/Blocks";
import { DataTable } from "../components/DataTable";
import { SceneFrame } from "../components/SceneFrame";
import { Wordmark } from "../components/Wordmark";
import {
  ARTIFACT_HYGIENE,
  CLI_COMMAND,
  GO_DEEPER,
  ONBOARDED_WHEN,
  OUTPUT_CONTRACTS,
  PRESET_CHOICES,
  PRESET_HEADERS,
  PRESET_RULE,
  RATE_COMMAND_NOTE,
  SUCCESS_CHECKS,
  SUMMARY_ROWS,
  TROUBLESHOOTING,
  TROUBLESHOOTING_HEADERS,
  WEIGHT_METHODS,
  WEIGHT_METHODS_NOTE,
  WORKBOOK_GUIDE,
  WORKBOOK_HEADERS,
} from "../content/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

export const S11Cli: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s11">
      <div style={{ display: "flex", flexDirection: "column", gap: 30 }}>
        <CodeBlock
          lines={CLI_COMMAND}
          startFrame={8}
          lineStagger={11}
          fontSize={34}
          accentLines={[0]}
        />
        <div
          style={{
            fontFamily: SANS,
            fontSize: SIZES.label,
            color: COLORS.textDim,
            opacity: revealAt(frame, 116),
          }}
        >
          {RATE_COMMAND_NOTE}
        </div>
      </div>
    </SceneFrame>
  );
};

export const S12Checks: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s12">
      <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
        {SUCCESS_CHECKS.map((check, index) => {
          const appear = revealAt(frame, 8 + index * 24);
          return (
            <div
              key={check}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 26,
                opacity: appear,
                translate: interpolate(appear, [0, 1], ["0px 12px", "0px 0px"]),
              }}
            >
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: 34,
                  fontWeight: 600,
                  color: COLORS.good,
                  width: 42,
                  flexShrink: 0,
                }}
              >
                ✓
              </span>
              <span style={{ fontFamily: SANS, fontSize: 42, color: COLORS.text }}>
                {check}
              </span>
            </div>
          );
        })}
      </div>
    </SceneFrame>
  );
};

export const S13Workbook: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s13">
      <div style={{ display: "flex", gap: 56, alignItems: "flex-start" }}>
        <div
          style={{
            width: 762,
            display: "flex",
            flexDirection: "column",
            borderRadius: 10,
            overflow: "hidden",
            border: `1px solid ${COLORS.edgeBright}`,
            opacity: revealAt(frame, 6),
          }}
        >
          <div
            style={{
              padding: "16px 24px",
              backgroundColor: COLORS.panel,
              borderBottom: `1px solid ${COLORS.edge}`,
              fontFamily: MONO,
              fontSize: SIZES.micro,
              color: COLORS.textDim,
            }}
          >
            Summary
          </div>
          {SUMMARY_ROWS.map((row, index) => (
            <div
              key={row.label}
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 20,
                padding: "15px 24px",
                borderBottom: `1px solid ${COLORS.edge}`,
                backgroundColor: row.good ? "rgba(151, 187, 157, 0.10)" : COLORS.panelSoft,
                opacity: revealAt(frame, 16 + index * 12),
              }}
            >
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: 26,
                  color: COLORS.textDim,
                  whiteSpace: "nowrap",
                }}
              >
                {row.label}
              </span>
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: 26,
                  fontWeight: row.good ? 600 : 400,
                  whiteSpace: "nowrap",
                  color: row.good ? COLORS.good : COLORS.text,
                }}
              >
                {row.value}
              </span>
            </div>
          ))}
        </div>
        <div style={{ flex: 1 }}>
          <DataTable
            headers={WORKBOOK_HEADERS}
            rows={WORKBOOK_GUIDE.map((entry) => [
              { text: entry.sheet, mono: true },
              { text: entry.meaning },
            ])}
            widths={[300, 480]}
            startFrame={30}
            rowHeight={88}
            rowStagger={13}
            fontSize={28}
          />
        </div>
      </div>
    </SceneFrame>
  );
};

export const S14WeightMethods: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s14">
      <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>
        <div style={{ display: "flex", alignItems: "stretch", gap: 20 }}>
          {WEIGHT_METHODS.map((method, index) => (
            <div
              key={method.name}
              style={{ display: "flex", alignItems: "center", gap: 20, flex: 1 }}
            >
              <div
                style={{
                  boxSizing: "border-box",
                  flex: 1,
                  height: 210,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  gap: 16,
                  padding: "28px 26px",
                  borderRadius: 10,
                  backgroundColor: COLORS.panel,
                  border: `1px solid ${index === 0 ? COLORS.edgeBright : COLORS.edge}`,
                  opacity: 0.35 + 0.65 * revealAt(frame, 10 + index * 26),
                }}
              >
                <div
                  style={{
                    fontFamily: MONO,
                    fontSize: 30,
                    whiteSpace: "nowrap",
                    color: index === 0 ? COLORS.accent : COLORS.textDim,
                  }}
                >
                  {method.name}
                </div>
                <div
                  style={{
                    fontFamily: SANS,
                    fontSize: 28,
                    lineHeight: 1.35,
                    color: COLORS.textFaint,
                  }}
                >
                  {method.note}
                </div>
              </div>
              {index < WEIGHT_METHODS.length - 1 ? (
                <div
                  style={{
                    fontFamily: MONO,
                    fontSize: 40,
                    color: COLORS.textFaint,
                    opacity: revealAt(frame, 26 + index * 26),
                  }}
                >
                  →
                </div>
              ) : null}
            </div>
          ))}
        </div>
        <Callout startFrame={96}>{WEIGHT_METHODS_NOTE}</Callout>
      </div>
    </SceneFrame>
  );
};

export const S15Contracts: React.FC = () => (
  <SceneFrame sceneId="s15">
    <div style={{ display: "flex", flexDirection: "column", gap: 34 }}>
      <div style={{ display: "flex", gap: 34 }}>
        {OUTPUT_CONTRACTS.map((contract, index) => (
          <Card
            key={contract.name}
            title={contract.name}
            body={contract.body}
            startFrame={10 + index * 20}
            accent={index === 1}
          />
        ))}
      </div>
      <Callout startFrame={92}>{ARTIFACT_HYGIENE}</Callout>
    </div>
  </SceneFrame>
);

export const S16Presets: React.FC = () => (
  <SceneFrame sceneId="s16">
    <div style={{ display: "flex", flexDirection: "column", gap: 30 }}>
      <DataTable
        headers={PRESET_HEADERS}
        rows={PRESET_CHOICES.map((choice) => [
          { text: choice.need },
          { text: choice.preset, mono: true },
          { text: choice.note },
        ])}
        widths={[430, 460, 610]}
        emphasis={PRESET_CHOICES.findIndex((choice) => choice.primary)}
        rowHeight={78}
        rowStagger={15}
        fontSize={30}
      />
      <Callout tone="good" startFrame={108}>
        {PRESET_RULE}
      </Callout>
    </div>
  </SceneFrame>
);

export const S17Troubleshooting: React.FC = () => (
  <SceneFrame sceneId="s17">
    <DataTable
      headers={TROUBLESHOOTING_HEADERS}
      rows={TROUBLESHOOTING.map((entry) => [
        { text: entry.symptom, mono: true, color: COLORS.warn },
        { text: entry.fix },
      ])}
      widths={[620, 880]}
      rowHeight={100}
      rowStagger={20}
      fontSize={31}
    />
  </SceneFrame>
);

export const S18GoDeeper: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill
      style={{ justifyContent: "center", alignItems: "center", gap: 52, padding: 140 }}
    >
      <Wordmark framesPerChar={2} />
      <div
        style={{
          fontFamily: SANS,
          fontSize: SIZES.body,
          color: COLORS.textDim,
          textAlign: "center",
          maxWidth: 1280,
          lineHeight: 1.4,
          opacity: revealAt(frame, 34),
        }}
      >
        {ONBOARDED_WHEN}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {GO_DEEPER.map((entry, index) => (
          <div
            key={entry.path}
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 26,
              opacity: revealAt(frame, 58 + index * 12),
            }}
          >
            <span
              style={{
                fontFamily: MONO,
                fontSize: SIZES.monoSmall,
                color: COLORS.accent,
                width: 520,
              }}
            >
              {entry.path}
            </span>
            <span style={{ fontFamily: SANS, fontSize: SIZES.micro, color: COLORS.textFaint }}>
              {entry.note}
            </span>
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};