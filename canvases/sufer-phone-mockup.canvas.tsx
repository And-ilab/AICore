import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Divider,
  H1,
  IconButton,
  Pill,
  Row,
  Spacer,
  Stack,
  Text,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";
import type { CanvasHostTheme } from "cursor/canvas";
import { useEffect, useState } from "react";
import type { CSSProperties, JSX } from "react";

// sufer-phone-mockup v1.4.23 — 2026-08-02
// Changelog: RU по умолчанию — 1 подсказка (замечание ID=76, слайд 4).
const CANVAS_MOCKUP_VERSION = "v1.4.23";

const RADIUS = 8;
const WINDOW_CONTROLS_WIDTH = 108;
const DRAWER_WIDTH = 300;
type ColorScheme =
  | "default"
  | "belarusbank_classic"
  | "belarusbank_soft"
  | "belarusbank_emerald"
  | "belarusbank_night";

type SchemePalette = {
  label: string;
  accent: string;
  accentWeak: string;
  headerBg: string;
  panelBg: string;
};

type SuflerFeedbackChoice = "used" | "not_used" | "partial";

const SUFLER_FEEDBACK_OPTIONS: { id: SuflerFeedbackChoice; label: string }[] = [
  { id: "used", label: "Воспользовался" },
  { id: "not_used", label: "Не воспользовался" },
  { id: "partial", label: "Неполный ответ" },
];

type FeedbackChipPalette = {
  idleBg: string;
  idleBorder: string;
  activeBg: string;
  activeBorder: string;
  activeColor: string;
};

/** Subtle per-label tints (§4.3.2.5): green / muted blue-grey / amber. */
function feedbackChipPalette(t: CanvasHostTheme, choice: SuflerFeedbackChoice): FeedbackChipPalette {
  const isLight = t.kind === "light";
  if (choice === "used") {
    return {
      idleBg: t.diff.insertedLine,
      idleBorder: isLight ? "#1F8A6533" : "#3FA26640",
      activeBg: isLight ? "#1F8A6533" : "#3FA2664D",
      activeBorder: t.diff.stripAdded,
      activeColor: isLight ? "#1F8A65" : "#52B896",
    };
  }
  if (choice === "not_used") {
    return {
      idleBg: isLight ? "#3685BF12" : "#599CE71A",
      idleBorder: isLight ? "#3685BF2E" : "#599CE738",
      activeBg: isLight ? "#3685BF24" : "#599CE730",
      activeBorder: isLight ? "#3685BF70" : "#599CE788",
      activeColor: t.text.primary,
    };
  }
  return {
    idleBg: isLight ? "#E8C03014" : "#E8C0301F",
    idleBorder: isLight ? "#E8C03040" : "#E8C03050",
    activeBg: isLight ? "#E8C0302E" : "#E8C03042",
    activeBorder: isLight ? "#C06028A8" : "#F0A040B3",
    activeColor: isLight ? "#8A6D00" : "#E8C030",
  };
}

type HintCardData = {
  id: string;
  title: string;
  preview: string;
  fullText: string;
  relevance: string;
  relevanceTone: "success" | "neutral" | "warning";
  suzTitle: string;
  highlighted?: boolean;
};

function feedbackChipStyle(
  t: CanvasHostTheme,
  choice: SuflerFeedbackChoice,
  selected: boolean,
  disabled: boolean,
): CSSProperties {
  const palette = feedbackChipPalette(t, choice);
  return {
    display: "inline-flex",
    alignItems: "center",
    fontSize: 10,
    fontWeight: selected ? 600 : 500,
    padding: "2px 6px",
    borderRadius: 4,
    border: `1px solid ${selected ? palette.activeBorder : palette.idleBorder}`,
    background: selected ? palette.activeBg : palette.idleBg,
    color: selected ? palette.activeColor : t.text.secondary,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.55 : 1,
    lineHeight: 1.2,
    whiteSpace: "nowrap",
    flexShrink: 0,
    appearance: "none",
    fontFamily: "inherit",
    outline: "none",
  };
}

function SuflerFeedbackRow({
  t,
  scheme,
  cardId,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  cardId: string;
}): JSX.Element {
  const [selected, setSelected] = useCanvasState<SuflerFeedbackChoice | null>(`suflerFeedback_${cardId}`, null);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row",
        flexWrap: "wrap",
        gap: 4,
        marginTop: 6,
        alignItems: "center",
      }}
    >
      {SUFLER_FEEDBACK_OPTIONS.map((option) => (
        <button
          key={option.id}
          type="button"
          title={option.label}
          style={feedbackChipStyle(t, option.id, selected === option.id, false)}
          onClick={() => setSelected(selected === option.id ? null : option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function PreviewResizeHandle({
  t,
  onMouseDown,
}: {
  t: CanvasHostTheme;
  onMouseDown: (event: { clientX: number; clientY: number; preventDefault: () => void }) => void;
}): JSX.Element {
  return (
    <div
      role="separator"
      aria-label="Изменить размер окна превью"
      title="Потяните за угол для изменения размера"
      onMouseDown={onMouseDown}
      style={{
        position: "absolute",
        right: 0,
        bottom: 0,
        width: 22,
        height: 22,
        zIndex: 30,
        touchAction: "none",
        cursor: "nwse-resize",
        background: t.stroke.secondary,
        borderTop: `1px solid ${t.stroke.tertiary}`,
        borderLeft: `1px solid ${t.stroke.tertiary}`,
      }}
    />
  );
}

function windowControlBtn(theme: CanvasHostTheme): CSSProperties {
  return {
    width: 36,
    height: 32,
    border: "none",
    background: "transparent",
    color: theme.text.secondary,
    fontSize: 12,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
  };
}

function WindowTitleBarControls({
  theme,
  onMinimize,
  onMaximize,
  onClose,
  maximized,
}: {
  theme: CanvasHostTheme;
  onMinimize?: () => void;
  onMaximize?: () => void;
  onClose?: () => void;
  maximized?: boolean;
}): JSX.Element {
  const btn = windowControlBtn(theme);
  return (
    <div style={{ position: "absolute", top: 0, right: 0, display: "flex", zIndex: 10 }}>
      <button type="button" title="Свернуть" style={btn} onClick={onMinimize}>
        ─
      </button>
      <button type="button" title={maximized ? "Восстановить" : "Развернуть"} style={btn} onClick={onMaximize}>
        {maximized ? "❐" : "□"}
      </button>
      <button type="button" title="Закрыть" style={btn} onClick={onClose}>
        ×
      </button>
    </div>
  );
}

function PinIcon({ pinned }: { pinned: boolean }): JSX.Element {
  return (
    <svg width={12} height={12} viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <circle
        cx={6}
        cy={2.75}
        r={1.75}
        fill={pinned ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth={pinned ? 0 : 1.1}
      />
      <path
        d="M4.75 4.75h2.5l.6 2.4H4.15l.6-2.4z"
        fill={pinned ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth={pinned ? 0 : 1.1}
        strokeLinejoin="round"
      />
      <path d="M6 7.2v2.8" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" />
    </svg>
  );
}

function getSchemePalette(theme: CanvasHostTheme, scheme: ColorScheme): SchemePalette {
  if (scheme === "belarusbank_classic") {
    return {
      label: "Classic",
      accent: "#0C4DA2",
      accentWeak: "#BFD3F3",
      headerBg: "linear-gradient(135deg, #EAF2FF 0%, #DCEAFF 55%, #F4F8FF 100%)",
      panelBg: "linear-gradient(180deg, #F7FAFF 0%, #EDF4FF 100%)",
    };
  }
  if (scheme === "belarusbank_soft") {
    return {
      label: "Soft",
      accent: "#2E5AAC",
      accentWeak: "#C8D6EF",
      headerBg: "linear-gradient(135deg, #F3F7FF 0%, #EAF1FF 58%, #FDFEFF 100%)",
      panelBg: "linear-gradient(180deg, #FAFCFF 0%, #F1F6FF 100%)",
    };
  }
  if (scheme === "belarusbank_emerald") {
    return {
      label: "Emerald",
      accent: "#007A43",
      accentWeak: "#BEE8D5",
      headerBg: "linear-gradient(135deg, #EAF8F1 0%, #DCF3E8 58%, #F2FBF6 100%)",
      panelBg: "linear-gradient(180deg, #F5FCF8 0%, #EAF7F1 100%)",
    };
  }
  if (scheme === "belarusbank_night") {
    return {
      label: "Night",
      accent: "#0D5C86",
      accentWeak: "#C5D9E6",
      headerBg: "linear-gradient(135deg, #E8F1F8 0%, #D8E8F4 60%, #EFF6FB 100%)",
      panelBg: "linear-gradient(180deg, #F3F8FC 0%, #E6F1F8 100%)",
    };
  }
  return {
    label: "Текущая",
    accent: theme.accent.primary,
    accentWeak: theme.stroke.secondary,
    headerBg: "linear-gradient(135deg, #F1F3F6 0%, #E9EDF3 100%)",
    panelBg: theme.bg.elevated,
  };
}

function panel(t: CanvasHostTheme, scheme: SchemePalette, extra?: CSSProperties): CSSProperties {
  return {
    background: scheme.panelBg,
    border: `1px solid ${scheme.accentWeak}`,
    borderRadius: RADIUS,
    ...extra,
  };
}

type RelevanceTier = "high" | "mediumStrong" | "mediumLight" | "low";

function parseRelevancePercent(relevance: number | string): number {
  if (typeof relevance === "number") return relevance;
  const match = relevance.match(/(\d+(?:\.\d+)?)/);
  return match ? Number(match[1]) : 0;
}

function relevanceTierFromPercent(pct: number): RelevanceTier {
  if (pct >= 90) return "high";
  if (pct >= 85) return "mediumStrong";
  if (pct >= 80) return "mediumLight";
  return "low";
}

type RelevanceShadeStyle = {
  tier: RelevanceTier;
  tone: "success" | "warning" | "neutral";
  background: string;
  border: string;
  borderLeft: string;
};

/** Shared relevance palette: ≥90% green, 85–89% amber-strong, 80–84% amber-light, <80% neutral. */
const RELEVANCE_SHADE_COLORS = {
  high: {
    borderLight: "#2E7D3270",
    borderDark: "#3FA26688",
  },
  mediumStrong: {
    bgLight: "#E8A02030",
    bgDark: "#E8A03042",
    borderLight: "#C0602880",
    borderDark: "#F0904080",
    borderLeftLight: "#C06028CC",
    borderLeftDark: "#F0A040D9",
  },
  mediumLight: {
    bgLight: "#F0D88018",
    bgDark: "#E8C03024",
    borderLight: "#B8883850",
    borderDark: "#C8984860",
    borderLeftLight: "#B88860A0",
    borderLeftDark: "#C8A060B0",
  },
  low: {
    bgLight: "#ECEFF120",
    bgDark: "#546E7A28",
    borderLight: "#78909C66",
    borderDark: "#90A4AE77",
    borderLeftLight: "#78909C",
    borderLeftDark: "#90A4AE",
  },
} as const;

function relevanceShade(t: CanvasHostTheme, relevance: number | string): RelevanceShadeStyle {
  const tier = relevanceTierFromPercent(parseRelevancePercent(relevance));
  const isLight = t.kind === "light";

  if (tier === "high") {
    const c = RELEVANCE_SHADE_COLORS.high;
    return {
      tier,
      tone: "success",
      background: t.diff.insertedLine,
      border: isLight ? c.borderLight : c.borderDark,
      borderLeft: t.palette.diffStripAdded,
    };
  }
  if (tier === "mediumStrong") {
    const c = RELEVANCE_SHADE_COLORS.mediumStrong;
    return {
      tier,
      tone: "warning",
      background: isLight ? c.bgLight : c.bgDark,
      border: isLight ? c.borderLight : c.borderDark,
      borderLeft: isLight ? c.borderLeftLight : c.borderLeftDark,
    };
  }
  if (tier === "mediumLight") {
    const c = RELEVANCE_SHADE_COLORS.mediumLight;
    return {
      tier,
      tone: "warning",
      background: isLight ? c.bgLight : c.bgDark,
      border: isLight ? c.borderLight : c.borderDark,
      borderLeft: isLight ? c.borderLeftLight : c.borderLeftDark,
    };
  }
  const c = RELEVANCE_SHADE_COLORS.low;
  return {
    tier,
    tone: "neutral",
    background: isLight ? c.bgLight : c.bgDark,
    border: isLight ? c.borderLight : c.borderDark,
    borderLeft: isLight ? c.borderLeftLight : c.borderLeftDark,
  };
}

function SuflerHintCard({
  t,
  scheme,
  hint,
  hoveredHintId,
  onHover,
  onHoverEnd,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  hint: HintCardData;
  hoveredHintId: string | null;
  onHover: (id: string) => void;
  onHoverEnd: () => void;
}): JSX.Element {
  const isExpanded = hoveredHintId === hint.id;
  const shade = relevanceShade(t, hint.relevance);

  const handleBlur = (event: { currentTarget: EventTarget & HTMLElement; relatedTarget: EventTarget | null }) => {
    const next = event.relatedTarget as Node | null;
    if (!next || !event.currentTarget.contains(next)) {
      onHoverEnd();
    }
  };

  return (
    <div
      tabIndex={0}
      role="group"
      aria-label={`Подсказка: ${hint.title}`}
      aria-expanded={isExpanded}
      style={{ marginTop: 8, marginLeft: 12, outline: "none" }}
      onMouseEnter={() => onHover(hint.id)}
      onMouseLeave={onHoverEnd}
      onFocus={() => onHover(hint.id)}
      onBlur={handleBlur}
    >
      <Card
        style={{
          background: shade.background,
          border: `1px solid ${shade.border}`,
          borderLeft: `3px solid ${shade.borderLeft}`,
        }}
      >
        <CardHeader trailing={<Pill tone={shade.tone}>{hint.relevance}</Pill>}>{hint.title}</CardHeader>
        <CardBody>
          {isExpanded ? (
            <Text style={{ fontSize: 13, lineHeight: 1.45, color: t.text.primary }}>{hint.fullText}</Text>
          ) : (
            <Text
              style={{
                fontSize: 13,
                lineHeight: 1.4,
                overflow: "hidden",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
              }}
            >
              {hint.preview}
            </Text>
          )}
          {isExpanded ? (
            <>
              <Row gap={6} wrap style={{ marginTop: 10 }}>
                <Button variant="ghost" size="sm">
                  {hint.suzTitle} ↗
                </Button>
              </Row>
              <SuflerFeedbackRow t={t} scheme={scheme} cardId={hint.id} />
            </>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

/** Client message bubble — mirrors online-chat MessageBubble side="client". */
function clientBubbleStyle(t: CanvasHostTheme): CSSProperties {
  return {
    maxWidth: "88%",
    padding: "10px 14px",
    borderRadius: 12,
    borderBottomLeftRadius: 4,
    background: t.fill.tertiary,
    border: `1px solid ${t.stroke.secondary}`,
  };
}

/** Operator draft bubble — elevated surface, accentWeak border, italic text. */
function operatorDraftBubbleStyle(t: CanvasHostTheme, scheme: SchemePalette): CSSProperties {
  return {
    padding: "10px 14px",
    borderRadius: 6,
    background: t.bg.elevated,
    border: `1px solid ${scheme.accentWeak}`,
  };
}

/** Operator sent reply — mirrors online-chat MessageBubble side="operator". */
function operatorReplyBubbleStyle(_t: CanvasHostTheme, scheme: SchemePalette): CSSProperties {
  return {
    maxWidth: "88%",
    marginLeft: "auto",
    padding: "10px 14px",
    borderRadius: 12,
    borderBottomRightRadius: 4,
    borderBottomLeftRadius: 12,
    background: scheme.headerBg,
    border: `1px solid ${scheme.accent}`,
  };
}

function DialogueBlock({
  t,
  scheme,
  client,
  clientTime,
  operator,
  operatorTime,
  operatorReply,
  operatorReplyTime,
  hints,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  client: string;
  clientTime: string;
  operator?: string;
  operatorTime?: string;
  operatorReply?: string;
  operatorReplyTime?: string;
  hints: HintCardData[];
}): JSX.Element {
  const [hoveredHintId, setHoveredHintId] = useState<string | null>(null);

  return (
    <div style={{ ...panel(t, scheme, { padding: 12, marginBottom: 12 }), borderLeft: `3px solid ${scheme.accentWeak}` }}>
      <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 4 }}>Клиент · {clientTime}</Text>
      <div style={{ ...clientBubbleStyle(t), marginBottom: operator ? 8 : 0 }}>
        <Text style={{ fontSize: 13, lineHeight: 1.45, color: t.text.primary }}>{client}</Text>
      </div>
      {operator ? (
        <>
          <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 4, marginTop: 8 }}>
            Оператор · {operatorTime} · черновик
          </Text>
          <div style={{ ...operatorDraftBubbleStyle(t, scheme), marginBottom: 4 }}>
            <Text style={{ fontSize: 13, fontStyle: "italic", color: t.text.secondary }}>{operator}</Text>
          </div>
        </>
      ) : null}
      <Divider style={{ margin: "10px 0" }} />
      <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 6 }}>
        Подсказки суфлёра
      </Text>
      {hints.map((hint) => (
        <SuflerHintCard
          key={hint.id}
          t={t}
          scheme={scheme}
          hint={hint}
          hoveredHintId={hoveredHintId}
          onHover={setHoveredHintId}
          onHoverEnd={() => setHoveredHintId(null)}
        />
      ))}
      {operatorReply ? (
        <>
          <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 4, marginTop: 12 }}>
            Оператор · {operatorReplyTime} · ответ клиенту
          </Text>
          <div style={operatorReplyBubbleStyle(t, scheme)}>
            <Text style={{ fontSize: 13, lineHeight: 1.45, color: t.text.primary }}>{operatorReply}</Text>
          </div>
        </>
      ) : null}
    </div>
  );
}

/** Neutral right-panel cards: border is a more saturated tone of the field background. */
function neutralCardSurface(t: CanvasHostTheme, isExpanded: boolean): { background: string; border: string } {
  const background = isExpanded ? t.bg.elevated : t.fill.tertiary;
  return {
    background,
    border: t.stroke.secondary,
  };
}

type SummaryHistoryData = {
  summary: string;
  detailedSummary: string;
  preview: string;
};

const ACTIVE_SUMMARY_HISTORY: SummaryHistoryData = {
  summary:
    "3 обращения за 90 дней: лимиты ATM (чат), перевод РФ (тел.), карта NFC (Telegram). Повторная тема: переводы.",
  detailedSummary:
    "За 90 дней — 3 обращения по теме лимитов и переводов.\n\n12.05.2026 · онлайн-чат · лимит ATM — оператор Сидорова М.В. Разъяснены суточные лимиты карты Visa.\n\n03.04.2026 · Telegram · NFC — оператор Козлов Д.А. Проверены настройки бесконтактной оплаты.\n\n15.03.2026 · телефония (Oktell) · перевод в РФ — оператор Петрова А.С., длит. 4:12. Рекомендован раздел «Платежи → За рубеж».\n\nПовторная тема: переводы. Рекомендация: проверить актуальный лимит в мобильном банке перед ответом.",
  preview:
    "3 обращения за 90 дней: лимиты ATM (чат), перевод РФ (тел.), карта NFC (Telegram). Повторная тема: переводы.",
};

function ClientSummaryCard({
  t,
  data,
  isExpanded,
  onHover,
  onHoverEnd,
}: {
  t: CanvasHostTheme;
  data: SummaryHistoryData;
  isExpanded: boolean;
  onHover: () => void;
  onHoverEnd: () => void;
}): JSX.Element {
  const handleBlur = (event: { currentTarget: EventTarget & HTMLElement; relatedTarget: EventTarget | null }) => {
    const next = event.relatedTarget as Node | null;
    if (!next || !event.currentTarget.contains(next)) {
      onHoverEnd();
    }
  };

  const surface = neutralCardSurface(t, isExpanded);

  return (
    <div
      tabIndex={0}
      role="group"
      aria-label="Summary клиента"
      aria-expanded={isExpanded}
      style={{ outline: "none" }}
      onMouseEnter={onHover}
      onMouseLeave={onHoverEnd}
      onFocus={onHover}
      onBlur={handleBlur}
    >
      <Card
        style={{
          background: surface.background,
          border: `1px solid ${surface.border}`,
        }}
      >
        <CardHeader>Summary клиента</CardHeader>
        <CardBody>
          {isExpanded ? (
            <Stack style={{ gap: 8 }}>
              <Text style={{ fontSize: 12, lineHeight: 1.5, color: t.text.primary }}>{data.summary}</Text>
              <div style={{ height: 1, background: t.stroke.tertiary }} />
              <Text weight="semibold" style={{ fontSize: 11, color: t.text.secondary }}>
                Детальный summary
              </Text>
              <Text style={{ fontSize: 12, lineHeight: 1.55, color: t.text.primary, whiteSpace: "pre-line" }}>
                {data.detailedSummary}
              </Text>
            </Stack>
          ) : (
            <Text
              style={{
                fontSize: 12,
                lineHeight: 1.4,
                overflow: "hidden",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
              }}
            >
              {data.preview}
            </Text>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function SidePanelContent({ t }: { t: CanvasHostTheme }): JSX.Element {
  const [hoveredSummaryCard, setHoveredSummaryCard] = useState(false);

  return (
    <Stack style={{ gap: 10, padding: 10, flex: 1 }}>
      <ClientSummaryCard
        t={t}
        data={ACTIVE_SUMMARY_HISTORY}
        isExpanded={hoveredSummaryCard}
        onHover={() => setHoveredSummaryCard(true)}
        onHoverEnd={() => setHoveredSummaryCard(false)}
      />
    </Stack>
  );
}

function SidePanelHeader({
  t,
  scheme,
  pinned,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  pinned: boolean;
}): JSX.Element {
  return (
    <div style={{ padding: "8px 12px", borderBottom: `1px solid ${t.stroke.secondary}`, background: scheme.headerBg }}>
      <Text weight="semibold" style={{ fontSize: 12 }}>
        {pinned ? "Контекст" : "Выдвижная панель"}
      </Text>
    </div>
  );
}

function SideContextDrawer({
  t,
  scheme,
  open,
  pinned,
  onToggle,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  open: boolean;
  pinned: boolean;
  onToggle: () => void;
}): JSX.Element {
  if (pinned) {
    return null;
  }

  const handleStyle: CSSProperties = {
    position: "absolute",
    right: open ? DRAWER_WIDTH : 0,
    top: "42%",
    zIndex: 20,
    transform: "translateX(100%)",
    transition: "right 0.28s ease",
    writingMode: "vertical-rl",
    textOrientation: "mixed",
    padding: "10px 6px",
    border: `1px solid ${scheme.accentWeak}`,
    borderRight: "none",
    borderRadius: `${RADIUS}px 0 0 ${RADIUS}px`,
    background: scheme.headerBg,
    color: t.text.primary,
    fontSize: 11,
    fontWeight: 600,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: 6,
    letterSpacing: 0.3,
  };

  return (
    <>
      <button type="button" title={open ? "Скрыть панель контекста" : "Показать панель контекста"} style={handleStyle} onClick={onToggle}>
        {open ? "◀ скрыть" : "контекст ▶"}
      </button>

      <div
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          bottom: 0,
          width: DRAWER_WIDTH,
          zIndex: 15,
          display: "flex",
          flexDirection: "column",
          background: t.bg.elevated,
          borderLeft: `2px solid ${scheme.accent}`,
          transform: open ? "translateX(0)" : `translateX(${DRAWER_WIDTH}px)`,
          transition: "transform 0.28s ease",
          overflow: "auto",
        }}
      >
        <SidePanelHeader t={t} scheme={scheme} pinned={pinned} />
        <SidePanelContent t={t} />
      </div>

      {open ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: "rgba(0, 0, 0, 0.06)",
            zIndex: 12,
            transition: "opacity 0.28s ease",
          }}
          onClick={onToggle}
          aria-hidden
        />
      ) : null}
    </>
  );
}

function SideContextDock({
  t,
  scheme,
  open,
  pinned,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  open: boolean;
  pinned: boolean;
}): JSX.Element {
  if (!open) {
    return null;
  }

  return (
    <div
      style={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        borderLeft: `2px solid ${scheme.accent}`,
        background: t.bg.elevated,
        overflow: "auto",
      }}
    >
      <SidePanelHeader t={t} scheme={scheme} pinned={pinned} />
      <SidePanelContent t={t} />
    </div>
  );
}

function ClosedWindowCallout({
  t,
  scheme,
  onReopen,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  onReopen: () => void;
}): JSX.Element {
  return (
    <Stack style={{ padding: 20, maxWidth: 1100, margin: "0 auto", gap: 16 }}>
      <H1>Суфлёр · телефония — окно закрыто</H1>
      <div style={{ ...panel(t, scheme, { padding: 16 }), borderLeft: `3px solid ${scheme.accent}` }}>
        <Text weight="semibold" style={{ fontSize: 13, marginBottom: 10 }}>
          Закрыли окно → как вызвать снова
        </Text>
        <Stack style={{ gap: 8 }}>
          <Row style={{ gap: 8, alignItems: "flex-start" }}>
            <Pill size="sm">1</Pill>
            <Text style={{ fontSize: 13, lineHeight: 1.45 }}>
              <strong>Портальный лаунчер</strong> — кнопка AI Hub в правом нижнем углу портала → «Суфлёр»
            </Text>
          </Row>
          <Row style={{ gap: 8, alignItems: "flex-start" }}>
            <Pill size="sm">2</Pill>
            <Text style={{ fontSize: 13, lineHeight: 1.45 }}>
              <strong>Иконка в системном трее</strong> — контекстное меню «Открыть суфлёр»
            </Text>
          </Row>
          <Row style={{ gap: 8, alignItems: "flex-start" }}>
            <Pill size="sm">3</Pill>
            <Text style={{ fontSize: 13, lineHeight: 1.45 }}>
              <strong>Автоматически при звонке Oktell</strong>
            </Text>
          </Row>
        </Stack>
        <Button variant="primary" onClick={onReopen} style={{ marginTop: 16 }}>
          Демо: открыть окно суфлёра
        </Button>
      </div>
      <div style={{ position: "relative", height: 48 }}>
        <div
          style={{
            position: "absolute",
            right: 24,
            bottom: 0,
            width: 56,
            height: 56,
            borderRadius: 28,
            background: scheme.accent,
            color: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 11,
            fontWeight: 700,
            cursor: "pointer",
          }}
          onClick={onReopen}
          title="Лаунчер AI Hub"
        >
          Hub
        </div>
      </div>
    </Stack>
  );
}

export default function SuferPhoneMockup(): JSX.Element {
  const t = useHostTheme();
  const [colorScheme, setColorScheme] = useCanvasState<ColorScheme>("suflerPhoneColorScheme", "belarusbank_emerald");
  const [windowOpen, setWindowOpen] = useCanvasState("suflerWindowOpen", true);
  const [maximized, setMaximized] = useCanvasState("suflerWindowMaximized", false);
  const [drawerOpen, setDrawerOpen] = useCanvasState("suflerContextDrawerOpen", true);
  const [drawerPinned, setDrawerPinned] = useCanvasState("suflerContextDrawerPinned", true);
  const [previewWidth, setPreviewWidth] = useCanvasState("suflerPhonePreviewWidth", 1100);
  const [previewHeight, setPreviewHeight] = useCanvasState("suflerPhonePreviewHeight", 780);
  const [demoLang, setDemoLang] = useCanvasState<"ru" | "en">("suflerPhoneDemoLang", "ru");
  const [canvasBuild, setCanvasBuild] = useCanvasState("_canvasBuild", "");
  const scheme = getSchemePalette(t, "belarusbank_emerald");

  useEffect(() => {
    if (canvasBuild !== CANVAS_MOCKUP_VERSION) {
      setCanvasBuild(CANVAS_MOCKUP_VERSION);
      setColorScheme("belarusbank_emerald");
      setDemoLang("ru");
      setDrawerOpen(true);
      setDrawerPinned(true);
      setPreviewWidth(1100);
      setPreviewHeight(780);
    }
  }, [
    canvasBuild,
    setCanvasBuild,
    setColorScheme,
    setDemoLang,
    setDrawerOpen,
    setDrawerPinned,
    setPreviewWidth,
    setPreviewHeight,
  ]);
  const boundedWidth = Math.max(680, Math.min(1200, previewWidth));
  const boundedHeight = Math.max(maximized ? 820 : 480, Math.min(900, previewHeight));

  const setPreviewSize = (nextWidth: number, nextHeight: number) => {
    setPreviewWidth(Math.max(680, Math.min(1200, Math.round(nextWidth))));
    setPreviewHeight(Math.max(maximized ? 820 : 480, Math.min(900, Math.round(nextHeight))));
  };

  const startResize = (event: { clientX: number; clientY: number; preventDefault: () => void }) => {
    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const initialWidth = boundedWidth;
    const initialHeight = boundedHeight;

    const handleMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      setPreviewSize(initialWidth + deltaX, initialHeight + deltaY);
    };

    const handleUp = () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "nwse-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
  };

  if (!windowOpen) {
    return <ClosedWindowCallout t={t} scheme={scheme} onReopen={() => setWindowOpen(true)} />;
  }

  return (
    <Stack style={{ padding: 8, maxWidth: 1140, margin: "0 auto", background: "transparent" }}>
      <div
        style={{
          position: "relative",
          width: boundedWidth,
          maxWidth: "100%",
          height: boundedHeight,
          minHeight: 0,
          transition: "width 160ms ease, height 160ms ease",
          ...panel(t, scheme, { display: "flex", flexDirection: "column", overflow: "hidden", padding: 0 }),
        }}
      >
        <div
          style={{
            position: "relative",
            padding: "12px 16px",
            paddingRight: WINDOW_CONTROLS_WIDTH,
            borderBottom: `1px solid ${t.stroke.secondary}`,
            background: scheme.headerBg,
            zIndex: 5,
          }}
        >
          <Row style={{ justifyContent: "space-between", alignItems: "center" }}>
            <Text weight="semibold">Суфлёр · активный звонок</Text>
            <Row style={{ gap: 8, alignItems: "center" }}>
              <Pill active={demoLang === "ru"} onClick={() => setDemoLang("ru")} size="sm">
                RU
              </Pill>
              <Pill active={demoLang === "en"} onClick={() => setDemoLang("en")} size="sm">
                EN
              </Pill>
              <IconButton
                title={drawerPinned ? "Открепить панель контекста" : "Закрепить панель контекста"}
                variant={drawerPinned ? "circle" : "default"}
                size="sm"
                onClick={() => {
                  const nextPinned = !drawerPinned;
                  setDrawerPinned(nextPinned);
                  if (nextPinned) {
                    setDrawerOpen(true);
                  }
                }}
                style={drawerPinned ? { color: scheme.accent } : undefined}
              >
                <PinIcon pinned={drawerPinned} />
              </IconButton>
              <Pill tone="success" size="sm">
                Консультация
              </Pill>
              <Text style={{ fontSize: 12, color: t.text.secondary }}>Иванова М.П.</Text>
            </Row>
          </Row>
          <WindowTitleBarControls
            theme={t}
            onMinimize={() => setWindowOpen(false)}
            onMaximize={() => setMaximized(!maximized)}
            onClose={() => setWindowOpen(false)}
            maximized={maximized}
          />
        </div>

        <div style={{ flex: 1, display: "flex", minHeight: 0, overflow: "hidden", position: "relative" }}>
          <div style={{ flex: 1, padding: 16, overflow: "auto", minWidth: 0, position: "relative", zIndex: 5 }}>
            {demoLang === "en" ? (
              <>
                <div
                  style={{
                    display: "flex",
                    gap: 6,
                    flexWrap: "wrap",
                    marginBottom: 10,
                    alignItems: "center",
                  }}
                >
                  <Pill tone="info" size="sm" active>
                    Язык клиента: EN
                  </Pill>
                  <Pill size="sm">Определено ≥99%</Pill>
                </div>
                <DialogueBlock
                  t={t}
                  scheme={scheme}
                  client="How can I transfer money to Russia via the mobile bank?"
                  clientTime="10:14"
                  operator="One moment — I'll check the cross-border transfer conditions."
                  operatorTime="10:15"
                  operatorReply="You can transfer to Russia via Payments → Abroad if a limit is available. What amount do you need?"
                  operatorReplyTime="10:16"
                  hints={[
                    {
                      id: "phone-en-q-translate",
                      title: "① Вопрос + перевод",
                      preview: "EN: How can I transfer… → RU: Как оформить перевод…",
                      fullText:
                        "EN: How can I transfer money to Russia via the mobile bank?\nRU: Как оформить перевод денег в Россию через мобильный банк?",
                      relevance: "96%",
                      relevanceTone: "success",
                      suzTitle: "Переводы в РФ — лимиты",
                      highlighted: true,
                    },
                    {
                      id: "phone-en-answer-en",
                      title: "② Ответ EN (для клиента)",
                      preview: "You can transfer to Russia via Payments → Abroad…",
                      fullText:
                        "You can transfer to Russia via «Payments» → «Abroad» if an international transfer limit is available. Please specify the amount and currency.",
                      relevance: "93%",
                      relevanceTone: "success",
                      suzTitle: "Переводы в РФ — лимиты",
                      highlighted: true,
                    },
                    {
                      id: "phone-en-answer-ru",
                      title: "③ Ответ RU (для проверки)",
                      preview: "Перевод в РФ доступен через «Платежи» → «За рубеж»…",
                      fullText:
                        "Перевод в РФ доступен через «Платежи» → «За рубеж» при наличии лимита. Уточните сумму и валюту.",
                      relevance: "93%",
                      relevanceTone: "success",
                      suzTitle: "Переводы в РФ — лимиты",
                      highlighted: true,
                    },
                  ]}
                />
              </>
            ) : (
              <DialogueBlock
                t={t}
                scheme={scheme}
                client="Подскажите, как оформить перевод в Россию через мобильный банк?"
                clientTime="10:14"
                operator="Хорошо, сейчас посмотрю условия перевода за рубеж."
                operatorTime="10:15"
                operatorReply="Перевод в РФ доступен через «Платежи» → «За рубеж» при наличии лимита. Уточните, пожалуйста, сумму перевода."
                operatorReplyTime="10:16"
                hints={[
                  {
                    id: "phone-hint-transfer-rf",
                    title: "Переводы в РФ — лимиты",
                    preview: "Перевод в РФ доступен через «Платежи» → «За рубеж»…",
                    fullText:
                      "Перевод в РФ доступен через «Платежи» → «За рубеж» при наличии лимита. Уточните сумму и валюту.",
                    relevance: "92%",
                    relevanceTone: "success",
                    suzTitle: "Переводы в РФ — лимиты",
                    highlighted: true,
                  },
                ]}
              />
            )}
          </div>
          <SideContextDock
            t={t}
            scheme={scheme}
            open={drawerOpen && drawerPinned}
            pinned={drawerPinned}
          />
        </div>

        <div style={{ padding: 12, borderTop: `1px solid ${t.stroke.secondary}`, fontSize: 11, color: t.text.tertiary, zIndex: 5 }}>
          ASR активен · p95 подсказки 1.4 с
        </div>

        <SideContextDrawer
          t={t}
          scheme={scheme}
          open={drawerOpen && !drawerPinned}
          pinned={drawerPinned}
          onToggle={() => setDrawerOpen(!drawerOpen)}
        />
        <PreviewResizeHandle t={t} onMouseDown={startResize} />
      </div>
    </Stack>
  );
}
