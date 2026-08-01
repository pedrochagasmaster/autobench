import { useCurrentFrame } from "remotion";
import { Callout, CodeBlock, revealAt, StepList } from "../components/Blocks";
import { DataTable } from "../components/DataTable";
import { SceneFrame } from "../components/SceneFrame";
import {
  CONTROL_REFERENCE,
  DAILY_WORKFLOW,
  DEMO_RULE,
  FIRST_ACCESS_COMMANDS,
  FIRST_ACCESS_WARNING,
  FIRST_FAILURES,
  INPUT_CONTRACT,
  INPUT_CONTRACT_HEADERS,
  LAUNCHERS,
  PREPARE_SQL,
  PRIVACY_RULES,
  PRIVACY_RULE_HEADERS,
  RULE_SELECTION_NOTE,
  SESSION_MEMORY,
  SHORTCUTS,
  VALIDATION_WARNING,
} from "../content/facts";
import { MONO, SANS } from "../fonts";
import { COLORS, SIZES } from "../theme";

export const S06FirstAccess: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s06">
      <div style={{ display: "flex", flexDirection: "column", gap: 30 }}>
        <CodeBlock lines={FIRST_ACCESS_COMMANDS} prompt startFrame={6} lineStagger={10} />
        <div style={{ display: "flex", gap: 26 }}>
          {LAUNCHERS.map((launcher, index) => (
            <div
              key={launcher.name}
              style={{
                flex: 1,
                display: "flex",
                alignItems: "baseline",
                gap: 20,
                padding: "22px 28px",
                borderRadius: 8,
                backgroundColor: COLORS.panel,
                border: `1px solid ${COLORS.edge}`,
                opacity: revealAt(frame, 62 + index * 14),
              }}
            >
              <span style={{ fontFamily: MONO, fontSize: SIZES.mono, color: COLORS.accent }}>
                {launcher.name}
              </span>
              <span style={{ fontFamily: SANS, fontSize: SIZES.label, color: COLORS.textDim }}>
                {launcher.note}
              </span>
            </div>
          ))}
        </div>
        <Callout tone="warn" startFrame={104}>
          {FIRST_ACCESS_WARNING}
        </Callout>
      </div>
    </SceneFrame>
  );
};

const MemoryCard: React.FC<{
  title: string;
  body: string;
  color: string;
  opacity: number;
}> = ({ title, body, color, opacity }) => (
  <div
    style={{
      flex: 1,
      padding: "24px 28px",
      borderRadius: 8,
      backgroundColor: COLORS.panelSoft,
      border: `1px solid ${COLORS.edge}`,
      opacity,
    }}
  >
    <div style={{ fontFamily: MONO, fontSize: SIZES.micro, letterSpacing: 3, color }}>
      {title}
    </div>
    <div
      style={{
        fontFamily: SANS,
        fontSize: SIZES.label,
        color: COLORS.textDim,
        marginTop: 12,
        lineHeight: 1.35,
      }}
    >
      {body}
    </div>
  </div>
);

export const S07DailyWorkflow: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s07">
      <div style={{ display: "flex", flexDirection: "column", gap: 38 }}>
        <StepList items={DAILY_WORKFLOW} startFrame={6} stagger={24} fontSize={40} />
        <div style={{ display: "flex", gap: 26 }}>
          <MemoryCard
            title="REMEMBERS BETWEEN SESSIONS"
            body={SESSION_MEMORY.remembers}
            color={COLORS.good}
            opacity={revealAt(frame, 98)}
          />
          <MemoryCard
            title="NEVER RESTORES"
            body={SESSION_MEMORY.forgets}
            color={COLORS.warn}
            opacity={revealAt(frame, 112)}
          />
        </div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", opacity: revealAt(frame, 134) }}>
          {SHORTCUTS.map((shortcut) => (
            <div
              key={shortcut.key}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 12,
                padding: "10px 22px",
                borderRadius: 999,
                border: `1px solid ${COLORS.edge}`,
              }}
            >
              <span style={{ fontFamily: MONO, fontSize: SIZES.micro, color: COLORS.accent }}>
                {shortcut.key}
              </span>
              <span style={{ fontFamily: SANS, fontSize: SIZES.micro, color: COLORS.textFaint }}>
                {shortcut.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </SceneFrame>
  );
};

export const S08InputContract: React.FC = () => (
  <SceneFrame sceneId="s08">
    <div style={{ display: "flex", gap: 56, alignItems: "flex-start" }}>
      <div style={{ width: 840 }}>
        <DataTable
          headers={INPUT_CONTRACT_HEADERS}
          rows={INPUT_CONTRACT.map((entry) => [
            { text: entry.role },
            { text: entry.meaning },
            { text: entry.column, mono: true, color: COLORS.accent },
          ])}
          widths={[200, 340, 300]}
          rowHeight={96}
          fontSize={29}
        />
      </div>
      <div style={{ flex: 1 }}>
        <CodeBlock lines={PREPARE_SQL} startFrame={34} lineStagger={7} fontSize={26} />
      </div>
    </div>
  </SceneFrame>
);

export const S09FirstFailures: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <SceneFrame sceneId="s09">
      <div style={{ display: "flex", flexDirection: "column", gap: 34 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          {FIRST_FAILURES.map((item, index) => {
            const appear = revealAt(frame, 8 + index * 20);
            return (
              <div
                key={item.rule}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: 26,
                  opacity: appear,
                }}
              >
                <span
                  style={{
                    fontFamily: MONO,
                    fontSize: 34,
                    fontWeight: 600,
                    color: COLORS.warn,
                    width: 38,
                    flexShrink: 0,
                  }}
                >
                  ×
                </span>
                <span
                  style={{
                    fontFamily: SANS,
                    fontSize: 40,
                    color: COLORS.text,
                    width: 620,
                    flexShrink: 0,
                  }}
                >
                  {item.rule}
                </span>
                <span style={{ fontFamily: SANS, fontSize: 34, color: COLORS.textDim }}>
                  {item.detail}
                </span>
              </div>
            );
          })}
        </div>
        <Callout tone="warn" startFrame={132}>
          {VALIDATION_WARNING}
        </Callout>
      </div>
    </SceneFrame>
  );
};

export const S10PrivacyRules: React.FC<{ showControlReference: boolean }> = ({
  showControlReference,
}) => {
  const frame = useCurrentFrame();
  const demoRow = PRIVACY_RULES.findIndex((rule) => rule.name === DEMO_RULE);

  return (
    <SceneFrame sceneId="s10">
      <div style={{ display: "flex", flexDirection: "column", gap: 30 }}>
        <DataTable
          headers={PRIVACY_RULE_HEADERS}
          rows={PRIVACY_RULES.map((rule) => [
            { text: rule.name, mono: true },
            { text: String(rule.minPeers), mono: true },
            { text: rule.maxShare, mono: true },
            { text: rule.extra },
          ])}
          widths={[220, 220, 300, 760]}
          emphasis={demoRow}
          muted={PRIVACY_RULES.findIndex((rule) => rule.conditional)}
          rowHeight={80}
          rowStagger={16}
        />
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            gap: 40,
            opacity: revealAt(frame, 120),
          }}
        >
          <div style={{ flex: 1, fontFamily: SANS, fontSize: SIZES.body, color: COLORS.text }}>
            {RULE_SELECTION_NOTE}
          </div>
          <div
            style={{
              fontFamily: MONO,
              fontSize: SIZES.label,
              color: COLORS.accent,
              whiteSpace: "nowrap",
            }}
          >
            {`demo file · 6 peers · ${DEMO_RULE}`}
          </div>
        </div>
        <div
          style={{
            fontFamily: MONO,
            fontSize: SIZES.micro,
            letterSpacing: 2,
            color: COLORS.textFaint,
            height: SIZES.micro,
            opacity: showControlReference ? revealAt(frame, 140) : 0,
          }}
        >
          {CONTROL_REFERENCE}
        </div>
      </div>
    </SceneFrame>
  );
};
