import {
  Button,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  IconButton,
  Pill,
  Row,
  Select,
  Stack,
  Text,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";
import type { CanvasHostTheme } from "cursor/canvas";
import { useEffect, useState } from "react";
import type { CSSProperties, JSX, MouseEvent as ReactMouseEvent } from "react";

// tray-launcher-mockup v1.0.4 — 2026-07-10 12:10 UTC+3
// Changelog: вариант C «compact» — минимальная кнопка AI + выезжающие иконки Суфлёр/Ассистент с улучшенным дизайном.
const CANVAS_MOCKUP_VERSION = "v1.0.4";

const SUFLER_SIDE_WIDTH = 260;

type WindowKey = "sufler" | "assistant";
type LauncherMode = "unified" | "dual" | "compact";
type PresetId = "both_closed" | "sufler_only" | "assistant_only" | "both_open" | "menu_open";
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
  accentControl: string;
  headerBg: string;
  panelBg: string;
  badge: string;
};

const PRESETS: { id: PresetId; label: string; sufler: boolean; assistant: boolean; menu: boolean }[] = [
  { id: "both_closed", label: "Оба свёрнуты", sufler: false, assistant: false, menu: false },
  { id: "sufler_only", label: "Только суфлёр", sufler: true, assistant: false, menu: false },
  { id: "assistant_only", label: "Только ассистент", sufler: false, assistant: true, menu: false },
  { id: "both_open", label: "Оба открыты", sufler: true, assistant: true, menu: false },
  { id: "menu_open", label: "Меню выбора", sufler: false, assistant: false, menu: true },
];

const COLOR_SCHEME_ORDER: ColorScheme[] = [
  "default",
  "belarusbank_classic",
  "belarusbank_soft",
  "belarusbank_emerald",
  "belarusbank_night",
];

const WINDOW_CONTROLS_WIDTH = 108;
const DEFAULT_PORTAL_HEIGHT = 560;
const PORTAL_HEADER_HEIGHT = 46;
const WORK_BOTTOM_INSET = 56;

function getSchemePalette(theme: CanvasHostTheme, scheme: ColorScheme): SchemePalette {
  if (scheme === "belarusbank_classic") {
    return {
      label: "Беларусбанк Classic",
      accent: "#0C4DA2",
      accentWeak: "#BFD3F3",
      accentControl: "#0A3F87",
      headerBg: "linear-gradient(135deg, #EAF2FF 0%, #DCEAFF 55%, #F4F8FF 100%)",
      panelBg: "linear-gradient(180deg, #F7FAFF 0%, #EDF4FF 100%)",
      badge: "#C62828",
    };
  }
  if (scheme === "belarusbank_soft") {
    return {
      label: "Беларусбанк Soft",
      accent: "#2E5AAC",
      accentWeak: "#C8D6EF",
      accentControl: "#2A4F93",
      headerBg: "linear-gradient(135deg, #F3F7FF 0%, #EAF1FF 58%, #FDFEFF 100%)",
      panelBg: "linear-gradient(180deg, #FAFCFF 0%, #F1F6FF 100%)",
      badge: "#D46A6A",
    };
  }
  if (scheme === "belarusbank_emerald") {
    return {
      label: "Беларусбанк Emerald",
      accent: "#007A43",
      accentWeak: "#BEE8D5",
      accentControl: "#00663A",
      headerBg: "linear-gradient(135deg, #EAF8F1 0%, #DCF3E8 58%, #F2FBF6 100%)",
      panelBg: "linear-gradient(180deg, #F5FCF8 0%, #EAF7F1 100%)",
      badge: "#0B9E5E",
    };
  }
  if (scheme === "belarusbank_night") {
    return {
      label: "Беларусбанк Night",
      accent: "#0D5C86",
      accentWeak: "#C5D9E6",
      accentControl: "#0A4D70",
      headerBg: "linear-gradient(135deg, #E8F1F8 0%, #D8E8F4 60%, #EFF6FB 100%)",
      panelBg: "linear-gradient(180deg, #F3F8FC 0%, #E6F1F8 100%)",
      badge: "#2D7FB8",
    };
  }
  return {
    label: "Текущая",
    accent: theme.accent.primary,
    accentWeak: theme.stroke.secondary,
    accentControl: theme.accent.control,
    headerBg: theme.fill.tertiary,
    panelBg: theme.bg.elevated,
    badge: theme.palette.diffStripRemoved,
  };
}

function PaletteDebug({ theme, scheme }: { theme: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
  const entries: { key: string; value: string }[] = [
    { key: "accent", value: scheme.accent },
    { key: "accentWeak", value: scheme.accentWeak },
    { key: "accentControl", value: scheme.accentControl },
    { key: "headerBg", value: scheme.headerBg },
    { key: "panelBg", value: scheme.panelBg },
    { key: "badge", value: scheme.badge },
  ];
  return (
    <Row style={{ gap: 8, flexWrap: "wrap", marginTop: 8 }}>
      {entries.map((entry) => (
        <Row key={entry.key} style={{ gap: 6, alignItems: "center" }}>
          <div
            style={{
              width: 14,
              height: 14,
              borderRadius: 3,
              background: entry.value,
              border: `1px solid ${theme.stroke.tertiary}`,
            }}
          />
          <Text style={{ fontSize: 10, color: theme.text.tertiary }}>{entry.key}</Text>
        </Row>
      ))}
    </Row>
  );
}

function applyPreset(
  preset: PresetId,
  setSufler: (v: boolean) => void,
  setAssistant: (v: boolean) => void,
  setMenu: (v: boolean) => void,
): void {
  const p = PRESETS.find((x) => x.id === preset);
  if (!p) return;
  setSufler(p.sufler);
  setAssistant(p.assistant);
  setMenu(p.menu);
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

function clampPortalPreviewHeight(height: number): number {
  return Math.max(400, Math.min(820, Math.round(height)));
}

function PortalPreviewFrame({
  theme,
  scheme,
  height,
  setHeight,
  children,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  height: number;
  setHeight: (h: number) => void;
  children: JSX.Element;
}): JSX.Element {
  const boundedHeight = clampPortalPreviewHeight(height);

  return (
    <div
      style={{
        width: "100%",
        height: boundedHeight,
        minHeight: 0,
        position: "relative",
        borderRadius: 10,
        border: `1px solid ${scheme.accentWeak}`,
        overflow: "hidden",
        background: scheme.panelBg,
        transition: "height 160ms ease",
      }}
    >
      {children}
      <ResizeHandle
        theme={theme}
        onMouseDown={createHeightResizeHandler(boundedHeight, setHeight)}
      />
    </div>
  );
}

function clampSuflerSize(width: number, height: number, portalHeight: number): { w: number; h: number } {
  const maxH = portalHeight - PORTAL_HEADER_HEIGHT - WORK_BOTTOM_INSET;
  return {
    w: Math.max(420, Math.min(920, Math.round(width))),
    h: Math.max(280, Math.min(maxH, Math.round(height))),
  };
}

function clampAssistantSize(width: number, height: number, portalHeight: number): { w: number; h: number } {
  const maxH = portalHeight - PORTAL_HEADER_HEIGHT - WORK_BOTTOM_INSET;
  return {
    w: Math.max(360, Math.min(720, Math.round(width))),
    h: Math.max(380, Math.min(maxH, Math.round(height))),
  };
}

function ResizeHandle({
  theme,
  onMouseDown,
}: {
  theme: CanvasHostTheme;
  onMouseDown: (event: ReactMouseEvent<HTMLDivElement>) => void;
}): JSX.Element {
  return (
    <div
      role="separator"
      aria-label="Resize panel"
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
        background: theme.stroke.secondary,
        borderTop: `1px solid ${theme.stroke.tertiary}`,
        borderLeft: `1px solid ${theme.stroke.tertiary}`,
        boxShadow: "inset -2px -2px 0 rgba(0,0,0,0.08)",
      }}
    />
  );
}

function createHeightResizeHandler(
  initialHeight: number,
  setHeight: (h: number) => void,
): (event: ReactMouseEvent<HTMLDivElement>) => void {
  return (event) => {
    event.preventDefault();
    event.stopPropagation();
    const startY = event.clientY;

    const handleMove = (moveEvent: MouseEvent) => {
      setHeight(initialHeight + moveEvent.clientY - startY);
    };

    const handleUp = () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
  };
}

function createResizeHandler(
  initialWidth: number,
  initialHeight: number,
  setSize: (w: number, h: number) => void,
): (event: ReactMouseEvent<HTMLDivElement>) => void {
  return (event) => {
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startY = event.clientY;

    const handleMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      setSize(initialWidth + deltaX, initialHeight + deltaY);
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
}

type SuflerFeedbackChoice = "used" | "not_used" | "partial";

const SUFLER_FEEDBACK_OPTIONS: { id: SuflerFeedbackChoice; label: string }[] = [
  { id: "used", label: "Воспользовался" },
  { id: "not_used", label: "Не воспользовался" },
  { id: "partial", label: "Неполный ответ" },
];

const ASSISTANT_FEEDBACK_OPTIONS: { id: SuflerFeedbackChoice; label: string }[] = [
  { id: "used", label: "Полезно" },
  { id: "partial", label: "Неполный ответ" },
  { id: "not_used", label: "Неверно" },
];

type FeedbackChipPalette = {
  idleBg: string;
  idleBorder: string;
  activeBg: string;
  activeBorder: string;
  activeColor: string;
};

function feedbackChipPalette(_t: CanvasHostTheme, choice: SuflerFeedbackChoice): FeedbackChipPalette {
  if (choice === "used") {
    return {
      idleBg: "#E6F4EA",
      idleBorder: "#B7DFC5",
      activeBg: "#C8EBD4",
      activeBorder: "#1F8A65",
      activeColor: "#1F8A65",
    };
  }
  if (choice === "not_used") {
    return {
      idleBg: "#E8F0FA",
      idleBorder: "#B8D4EF",
      activeBg: "#D4E6F7",
      activeBorder: "#3685BF",
      activeColor: "#1565C0",
    };
  }
  return {
    idleBg: "#FFF6D6",
    idleBorder: "#E8D090",
    activeBg: "#FFEFB8",
    activeBorder: "#C06028",
    activeColor: "#8A6D00",
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
    fontSize: 11,
    fontWeight: selected ? 600 : 500,
    padding: "4px 10px",
    borderRadius: 4,
    border: `1px solid ${selected ? palette.activeBorder : palette.idleBorder}`,
    background: selected ? palette.activeBg : palette.idleBg,
    color: selected ? palette.activeColor : "#4D443C",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.55 : 1,
    lineHeight: 1.3,
    whiteSpace: "nowrap",
    flexShrink: 0,
    boxSizing: "border-box",
    userSelect: "none",
  };
}

function SuflerFeedbackRow({
  t,
  scheme,
  cardId,
  options = SUFLER_FEEDBACK_OPTIONS,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  cardId: string;
  options?: { id: SuflerFeedbackChoice; label: string }[];
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
      {options.map((option) => (
        <span
          key={option.id}
          role="button"
          tabIndex={0}
          title={option.label}
          style={feedbackChipStyle(t, option.id, selected === option.id, false)}
          onClick={() => setSelected(selected === option.id ? null : option.id)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setSelected(selected === option.id ? null : option.id);
            }
          }}
        >
          {option.label}
        </span>
      ))}
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

function suflerPanel(t: CanvasHostTheme, scheme: SchemePalette, extra?: CSSProperties): CSSProperties {
  return {
    background: scheme.panelBg,
    border: `1px solid ${scheme.accentWeak}`,
    borderRadius: 8,
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

function operatorDraftBubbleStyle(t: CanvasHostTheme, scheme: SchemePalette): CSSProperties {
  return {
    padding: "10px 14px",
    borderRadius: 6,
    background: t.bg.elevated,
    border: `1px solid ${scheme.accentWeak}`,
  };
}

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
    <div style={{ ...suflerPanel(t, scheme, { padding: 12, marginBottom: 12 }), borderLeft: `3px solid ${scheme.accentWeak}` }}>
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

const EMBEDDED_SUMMARY_HISTORY: SummaryHistoryData = {
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

function EmbeddedSidePanel({ t, scheme }: { t: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
  const [hoveredSummaryCard, setHoveredSummaryCard] = useState(false);

  return (
    <div
      style={{
        width: SUFLER_SIDE_WIDTH,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        borderLeft: `2px solid ${scheme.accent}`,
        background: t.bg.elevated,
        overflow: "auto",
      }}
    >
      <div style={{ padding: "8px 12px", borderBottom: `1px solid ${t.stroke.secondary}`, background: scheme.headerBg }}>
        <Text weight="semibold" style={{ fontSize: 12 }}>
          Контекст
        </Text>
      </div>
      <Stack style={{ gap: 10, padding: 10, flex: 1 }}>
        <ClientSummaryCard
          t={t}
          data={EMBEDDED_SUMMARY_HISTORY}
          isExpanded={hoveredSummaryCard}
          onHover={() => setHoveredSummaryCard(true)}
          onHoverEnd={() => setHoveredSummaryCard(false)}
        />
      </Stack>
    </div>
  );
}

function SuflerStartWindow({
  theme,
  scheme,
  open,
  expanded,
  portalHeight,
  panelWidth,
  panelHeight,
  setPanelSize,
  onMinimize,
  onToggleExpand,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  open: boolean;
  expanded: boolean;
  portalHeight: number;
  panelWidth: number;
  panelHeight: number;
  setPanelSize: (w: number, h: number) => void;
  onMinimize: () => void;
  onToggleExpand: () => void;
}): JSX.Element | null {
  if (!open) return null;

  const bounded = clampSuflerSize(panelWidth, panelHeight, portalHeight);
  const shell: CSSProperties = expanded
    ? {
        position: "absolute",
        top: PORTAL_HEADER_HEIGHT,
        left: 0,
        right: 0,
        bottom: 0,
        borderRadius: 0,
      }
    : {
        position: "absolute",
        top: 58,
        left: 18,
        width: bounded.w,
        height: bounded.h,
        borderRadius: 8,
      };

  return (
    <div
      style={{
        ...shell,
        border: `1px solid ${scheme.accentWeak}`,
        background: scheme.panelBg,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        zIndex: 5,
        transition: expanded ? "none" : "width 160ms ease, height 160ms ease",
      }}
    >
      <div
        style={{
          position: "relative",
          padding: "8px 12px",
          paddingRight: WINDOW_CONTROLS_WIDTH,
          borderBottom: `1px solid ${theme.stroke.tertiary}`,
          background: scheme.headerBg,
        }}
      >
        <Row style={{ justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <Text weight="semibold" style={{ fontSize: 13 }}>
            Суфлёр · активный звонок
          </Text>
          <Row style={{ gap: 8, alignItems: "center" }}>
            <IconButton title="Панель контекста закреплена" variant="circle" size="sm" style={{ color: scheme.accent }}>
              <PinIcon pinned />
            </IconButton>
            <Pill tone="success" size="sm">
              Консультация
            </Pill>
            <Text style={{ fontSize: 12, color: theme.text.secondary }}>Иванова М.П.</Text>
          </Row>
        </Row>
        <WindowTitleBarControls
          theme={theme}
          onMinimize={onMinimize}
          onMaximize={onToggleExpand}
          onClose={onMinimize}
          maximized={expanded}
        />
      </div>

      <div style={{ display: "flex", minHeight: 0, flex: 1 }}>
        <div style={{ flex: 1, padding: 10, overflow: "auto", minWidth: 0 }}>
          <DialogueBlock
            t={theme}
            scheme={scheme}
            client="Подскажите, как оформить перевод в Россию через мобильный банк?"
            clientTime="10:14"
            operator="Хорошо, сейчас посмотрю условия перевода за рубеж."
            operatorTime="10:15"
            operatorReply="Перевод в РФ доступен через «Платежи» → «За рубеж» при наличии лимита. Уточните, пожалуйста, сумму перевода."
            operatorReplyTime="10:16"
            hints={[
              {
                id: "tray-hint-transfer-rf",
                title: "Переводы в РФ — лимиты",
                preview: "Перевод в РФ доступен через «Платежи» → «За рубеж»…",
                fullText:
                  "Перевод в РФ доступен через «Платежи» → «За рубеж» при наличии лимита. Уточните сумму и валюту.",
                relevance: "92%",
                relevanceTone: "success",
                suzTitle: "Переводы в РФ — лимиты",
                highlighted: true,
              },
              {
                id: "tray-hint-intl-limits",
                title: "Лимиты международных переводов",
                preview: "Для перевода нужен действующий лимит на международные операции…",
                fullText:
                  "Для перевода нужен действующий лимит на международные операции; проверьте в «Настройки» → «Лимиты».",
                relevance: "87%",
                relevanceTone: "warning",
                suzTitle: "Лимиты международных переводов",
              },
              {
                id: "tray-hint-transfer-fees",
                title: "Комиссии за переводы за рубеж",
                preview: "Комиссия зависит от суммы и валюты; актуальные тарифы…",
                fullText:
                  "Комиссия зависит от суммы и валюты; актуальные тарифы — в разделе «Тарифы» мобильного банка.",
                relevance: "81%",
                relevanceTone: "warning",
                suzTitle: "Комиссии за переводы за рубеж",
              },
            ]}
          />
          <DialogueBlock
            t={theme}
            scheme={scheme}
            client="А если лимит превышен?"
            clientTime="10:16"
            operator="Понял, уточню варианты при превышении лимита."
            operatorTime="10:17"
            operatorReply="При превышении лимита можно обратиться в отделение с паспортом — оформим постоянное или временное повышение лимита на международные переводы."
            operatorReplyTime="10:18"
            hints={[
              {
                id: "tray-hint-limit-exceeded",
                title: "Повышение лимита перевода",
                preview: "При превышении лимита — обращение в отделение с документом…",
                fullText:
                  "При превышении лимита — обращение в отделение с документом или повышение лимита через отделение.",
                relevance: "88%",
                relevanceTone: "warning",
                suzTitle: "Повышение лимита перевода",
              },
              {
                id: "tray-hint-temp-limit",
                title: "Временное повышение лимита",
                preview: "Временное повышение лимита возможно через отделение…",
                fullText:
                  "Временное повышение лимита возможно через отделение при предъявлении документа, удостоверяющего личность.",
                relevance: "79%",
                relevanceTone: "neutral",
                suzTitle: "Временное повышение лимита",
              },
            ]}
          />
        </div>

        <EmbeddedSidePanel t={theme} scheme={scheme} />
      </div>

      <div style={{ padding: "8px 12px", borderTop: `1px solid ${theme.stroke.tertiary}`, background: scheme.headerBg }}>
        <Text style={{ fontSize: 11, color: theme.text.tertiary }}>ASR активен · p95 подсказки 1.4 с</Text>
      </div>

      {!expanded ? (
        <ResizeHandle
          theme={theme}
          onMouseDown={createResizeHandler(bounded.w, bounded.h, setPanelSize)}
        />
      ) : null}
    </div>
  );
}

function AssistantWindow({
  theme,
  scheme,
  open,
  expanded,
  portalHeight,
  panelWidth,
  panelHeight,
  setPanelSize,
  onMinimize,
  onToggleExpand,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  open: boolean;
  expanded: boolean;
  portalHeight: number;
  panelWidth: number;
  panelHeight: number;
  setPanelSize: (w: number, h: number) => void;
  onMinimize: () => void;
  onToggleExpand: () => void;
}): JSX.Element | null {
  if (!open) return null;

  const bounded = clampAssistantSize(panelWidth, panelHeight, portalHeight);
  const shell: CSSProperties = expanded
    ? {
        position: "absolute",
        top: PORTAL_HEADER_HEIGHT,
        left: 0,
        right: 0,
        bottom: 0,
        borderRadius: 0,
      }
    : {
        position: "absolute",
        top: 58,
        right: 18,
        width: bounded.w,
        height: bounded.h,
        borderRadius: 12,
      };

  return (
    <div
      style={{
        ...shell,
        border: `1px solid ${scheme.accentWeak}`,
        background: scheme.panelBg,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        zIndex: 6,
        transition: expanded ? "none" : "width 160ms ease, height 160ms ease",
      }}
    >
      <div
        style={{
          position: "relative",
          padding: "10px 12px",
          paddingRight: WINDOW_CONTROLS_WIDTH,
          borderBottom: `1px solid ${theme.stroke.tertiary}`,
          background: scheme.headerBg,
        }}
      >
        <Stack style={{ gap: 2 }}>
          <Text weight="semibold">Беларусбанк AI</Text>
          <Text style={{ fontSize: 11, color: theme.text.tertiary }}>Сидоров П.К. · Пользователь ИИ-ассистента</Text>
        </Stack>
        <WindowTitleBarControls
          theme={theme}
          onMinimize={onMinimize}
          onMaximize={onToggleExpand}
          onClose={onMinimize}
          maximized={expanded}
        />
      </div>

      <div style={{ display: "flex", borderBottom: `1px solid ${theme.stroke.tertiary}` }}>
        {["Ассистент", "Документы"].map((label, i) => (
          <div
            key={label}
            style={{
              flex: 1,
              padding: "10px 8px",
              textAlign: "center",
              fontSize: 12,
              fontWeight: i === 0 ? 600 : 400,
              color: i === 0 ? theme.text.primary : theme.text.tertiary,
              borderBottom: i === 0 ? `2px solid ${scheme.accentWeak}` : "2px solid transparent",
              background: i === 0 ? scheme.headerBg : "transparent",
              opacity: i === 0 ? 1 : 0.45,
            }}
          >
            {label}
          </div>
        ))}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 10, minHeight: 0 }}>
        <Stack style={{ gap: 10 }}>
          <div>
            <Text style={{ fontSize: 11, color: theme.text.tertiary }}>Вы</Text>
            <Text style={{ fontSize: 12 }}>Как оформить отпуск?</Text>
          </div>
          <div>
            <Text style={{ fontSize: 11, color: theme.text.tertiary }}>Ассистент</Text>
            <Text style={{ fontSize: 12, lineHeight: 1.45 }}>
              Для оформления отпуска подайте заявление в HR-портале не позднее чем за 5 рабочих дней. При необходимости
              приложите согласование руководителя.
            </Text>
            <Stack style={{ gap: 4, marginTop: 8 }}>
              <Text weight="semibold" style={{ fontSize: 11 }}>
                Источники (2)
              </Text>
              <Row style={{ gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                <Pill size="sm" tone="success">
                  Регламент HR-12 · 94%
                </Pill>
                <Button variant="ghost" size="sm">
                  Открыть
                </Button>
              </Row>
            </Stack>
            <SuflerFeedbackRow
              t={theme}
              scheme={scheme}
              cardId="assistant_demo"
              options={ASSISTANT_FEEDBACK_OPTIONS}
            />
          </div>
        </Stack>
      </div>

      <div
        style={{
          flexShrink: 0,
          padding: 10,
          borderTop: `1px solid ${theme.stroke.secondary}`,
          background: scheme.panelBg,
        }}
      >
        <Row style={{ gap: 6, marginBottom: 6 }}>
          <Button variant="ghost" size="sm">
            Прикрепить
          </Button>
          <Button variant="ghost" size="sm">
            Инструменты
          </Button>
        </Row>
        <Row style={{ gap: 6, alignItems: "flex-end" }}>
          <div
            style={{
              flex: 1,
              minHeight: 52,
              padding: "8px 10px",
              borderRadius: 8,
              border: `1px solid ${scheme.accentWeak}`,
              background: theme.bg.elevated,
              fontSize: 12,
              color: theme.text.tertiary,
            }}
          >
            Задайте вопрос…
          </div>
          <Button variant="primary" size="sm" style={{ background: scheme.accentControl, borderColor: scheme.accentControl }}>
            Отправить
          </Button>
        </Row>
      </div>

      <div style={{ padding: "8px 12px", borderTop: `1px solid ${theme.stroke.tertiary}`, background: scheme.headerBg }}>
        <Row style={{ gap: 8, alignItems: "center" }}>
          <Pill size="sm" tone="success" active>
            Подключено
          </Pill>
          <Text style={{ fontSize: 11, color: theme.text.tertiary }}>БЗ обновлена · 12:34</Text>
        </Row>
      </div>

      {!expanded ? (
        <ResizeHandle
          theme={theme}
          onMouseDown={createResizeHandler(bounded.w, bounded.h, setPanelSize)}
        />
      ) : null}
    </div>
  );
}

function CompactModuleIcon({
  theme,
  scheme,
  target,
  label,
  glyph,
  active,
  expanded,
  onPick,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  target: WindowKey;
  label: string;
  glyph: string;
  active: boolean;
  expanded: boolean;
  onPick: (target: WindowKey) => void;
}): JSX.Element {
  return (
    <button
      type="button"
      title={label}
      onClick={() => onPick(target)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: 0,
        border: "none",
        background: "transparent",
        cursor: "pointer",
        opacity: expanded ? 1 : 0,
        transform: expanded ? "translateX(0)" : "translateX(12px)",
        transition: "opacity 0.2s ease, transform 0.2s ease",
        pointerEvents: expanded ? "auto" : "none",
      }}
    >
      <div
        style={{
          padding: "4px 10px",
          borderRadius: 20,
          background: theme.bg.elevated,
          border: `1px solid ${scheme.accentWeak}`,
        }}
      >
        <Text style={{ fontSize: 11, fontWeight: 600, color: theme.text.primary, whiteSpace: "nowrap" }}>{label}</Text>
      </div>
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: "50%",
          background: active ? scheme.headerBg : theme.bg.elevated,
          border: `2px solid ${active ? scheme.accent : scheme.accentWeak}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: scheme.accentControl,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Text style={{ fontSize: 12, color: theme.text.onAccent, fontWeight: 700 }}>{glyph}</Text>
        </div>
      </div>
    </button>
  );
}

function CompactLauncherDock({
  theme,
  scheme,
  menuOpen,
  suflerOpen,
  assistantOpen,
  onToggleMenu,
  onPick,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  menuOpen: boolean;
  suflerOpen: boolean;
  assistantOpen: boolean;
  onToggleMenu: () => void;
  onPick: (target: WindowKey) => void;
}): JSX.Element {
  return (
    <div
      style={{
        position: "absolute",
        right: 14,
        bottom: 12,
        display: "flex",
        alignItems: "center",
        gap: 10,
        zIndex: 7,
      }}
    >
      <CompactModuleIcon
        theme={theme}
        scheme={scheme}
        target="sufler"
        label="Суфлёр"
        glyph="S"
        active={suflerOpen}
        expanded={menuOpen}
        onPick={onPick}
      />
      <CompactModuleIcon
        theme={theme}
        scheme={scheme}
        target="assistant"
        label="Ассистент"
        glyph="A"
        active={assistantOpen}
        expanded={menuOpen}
        onPick={onPick}
      />
      <button
        type="button"
        onClick={onToggleMenu}
        title="AI Hub"
        style={{
          width: 44,
          height: 44,
          borderRadius: "50%",
          border: `2px solid ${menuOpen ? scheme.accent : scheme.accentWeak}`,
          background: menuOpen ? scheme.headerBg : theme.bg.elevated,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          transition: "border-color 0.15s ease, background 0.15s ease",
        }}
      >
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: "50%",
            background: scheme.accentControl,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Text style={{ fontSize: 10, color: theme.text.onAccent, fontWeight: 700 }}>AI</Text>
        </div>
      </button>
    </div>
  );
}

function SplitTrayMenu({
  theme,
  scheme,
  suflerOpen,
  assistantOpen,
  onPick,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  suflerOpen: boolean;
  assistantOpen: boolean;
  onPick: (target: WindowKey) => void;
}): JSX.Element {
  const halfBase: CSSProperties = {
    flex: 1,
    padding: "10px 12px",
    border: "none",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    textAlign: "left",
  };

  return (
    <div
      style={{
        position: "absolute",
        right: 16,
        bottom: 64,
        width: 240,
        border: `1px solid ${scheme.accentWeak}`,
        borderRadius: 8,
        background: scheme.panelBg,
        overflow: "hidden",
        zIndex: 8,
      }}
    >
      <div style={{ padding: "8px 10px", borderBottom: `1px solid ${theme.stroke.tertiary}`, background: scheme.headerBg }}>
        <Text weight="semibold" style={{ fontSize: 11 }}>
          Выбрать модуль
        </Text>
        <Text style={{ fontSize: 10, color: theme.text.tertiary, marginTop: 2 }}>
          По выбору открывается стартовое окно
        </Text>
      </div>
      <Row style={{ gap: 0 }}>
        <button
          type="button"
          style={{
            ...halfBase,
            background: suflerOpen ? scheme.headerBg : scheme.panelBg,
            color: theme.text.primary,
            borderRight: `1px solid ${theme.stroke.tertiary}`,
          }}
          onClick={() => onPick("sufler")}
        >
          <Row style={{ gap: 6, alignItems: "center" }}>
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: 4,
                background: scheme.accentWeak,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Text style={{ fontSize: 9, fontWeight: 700, color: scheme.accentControl }}>S</Text>
            </div>
            <Text style={{ fontSize: 12, fontWeight: 600 }}>Суфлёр</Text>
          </Row>
          <Text style={{ display: "block", fontSize: 10, color: theme.text.tertiary, marginTop: 4, fontWeight: 400 }}>
            {suflerOpen ? "Уже открыт" : "Открыть стартовое"}
          </Text>
        </button>
        <button
          type="button"
          style={{
            ...halfBase,
            background: assistantOpen ? scheme.headerBg : scheme.panelBg,
            color: theme.text.primary,
          }}
          onClick={() => onPick("assistant")}
        >
          <Row style={{ gap: 6, alignItems: "center" }}>
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: 4,
                background: scheme.accentWeak,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Text style={{ fontSize: 9, fontWeight: 700, color: scheme.accentControl }}>A</Text>
            </div>
            <Text style={{ fontSize: 12, fontWeight: 600 }}>Ассистент</Text>
          </Row>
          <Text style={{ display: "block", fontSize: 10, color: theme.text.tertiary, marginTop: 4, fontWeight: 400 }}>
            {assistantOpen ? "Уже открыт" : "Открыть стартовое"}
          </Text>
        </button>
      </Row>
    </div>
  );
}

function ModuleWidgetButton({
  theme,
  scheme,
  label,
  glyph,
  active,
  onClick,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  label: string;
  glyph: string;
  active: boolean;
  onClick: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 10px",
        borderRadius: 8,
        border: `1px solid ${active ? scheme.accent : scheme.accentWeak}`,
        background: active ? scheme.headerBg : theme.bg.elevated,
        cursor: "pointer",
        zIndex: 7,
      }}
    >
      <div
        style={{
          width: 18,
          height: 18,
          borderRadius: 4,
          background: scheme.accentControl,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Text style={{ fontSize: 9, color: theme.text.onAccent, fontWeight: 700 }}>{glyph}</Text>
      </div>
      <Text style={{ fontSize: 11, fontWeight: 600 }}>{label}</Text>
    </button>
  );
}

function DesktopMock({
  theme,
  scheme,
  launcherMode,
  portalHeight,
  suflerOpen,
  suflerExpanded,
  suflerWidth,
  suflerHeight,
  setSuflerSize,
  assistantOpen,
  assistantExpanded,
  assistantWidth,
  assistantHeight,
  setAssistantSize,
  menuOpen,
  onToggleMenu,
  onPickWindow,
  onMinimize,
  onToggleSuflerExpand,
  onToggleAssistantExpand,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  launcherMode: LauncherMode;
  portalHeight: number;
  suflerOpen: boolean;
  suflerExpanded: boolean;
  suflerWidth: number;
  suflerHeight: number;
  setSuflerSize: (w: number, h: number) => void;
  assistantOpen: boolean;
  assistantExpanded: boolean;
  assistantWidth: number;
  assistantHeight: number;
  setAssistantSize: (w: number, h: number) => void;
  menuOpen: boolean;
  onToggleMenu: () => void;
  onPickWindow: (target: WindowKey) => void;
  onMinimize: (target: WindowKey) => void;
  onToggleSuflerExpand: () => void;
  onToggleAssistantExpand: () => void;
}): JSX.Element {
  const desktop: CSSProperties = {
    position: "relative",
    height: portalHeight,
    borderRadius: 0,
    background: theme.fill.quaternary,
    overflow: "hidden",
  };

  const portalHeader: CSSProperties = {
    position: "absolute",
    left: 0,
    right: 0,
    top: 0,
    height: PORTAL_HEADER_HEIGHT,
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-start",
    padding: "0 14px",
    gap: 8,
    background: scheme.panelBg,
    borderBottom: `1px solid ${scheme.accentWeak}`,
    zIndex: 4,
  };

  const portalBtn: CSSProperties = {
    position: "absolute",
    right: 14,
    bottom: 12,
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "4px 8px",
    borderRadius: 4,
    border: `1px solid ${menuOpen ? scheme.accent : scheme.accentWeak}`,
    background: menuOpen ? scheme.headerBg : scheme.panelBg,
    cursor: "pointer",
    zIndex: 7,
  };

  return (
    <div style={desktop}>
      <div style={{ padding: "58px 14px 12px 14px" }}>
        <Text style={{ fontSize: 11, color: theme.text.tertiary }}>
          {launcherMode === "unified"
            ? "Внутренний корпоративный портал банка · кнопка AI Hub в правом нижнем углу"
            : launcherMode === "dual"
              ? "Внутренний корпоративный портал банка · два виджета Суфлёр и Ассистент в правом нижнем углу"
              : "Внутренний корпоративный портал банка · компактная кнопка AI, по клику выезжают иконки модулей"}
        </Text>
      </div>

      <SuflerStartWindow
        theme={theme}
        scheme={scheme}
        open={suflerOpen}
        expanded={suflerExpanded}
        portalHeight={portalHeight}
        panelWidth={suflerWidth}
        panelHeight={suflerHeight}
        setPanelSize={setSuflerSize}
        onMinimize={() => onMinimize("sufler")}
        onToggleExpand={onToggleSuflerExpand}
      />
      <AssistantWindow
        theme={theme}
        scheme={scheme}
        open={assistantOpen}
        expanded={assistantExpanded}
        portalHeight={portalHeight}
        panelWidth={assistantWidth}
        panelHeight={assistantHeight}
        setPanelSize={setAssistantSize}
        onMinimize={() => onMinimize("assistant")}
        onToggleExpand={onToggleAssistantExpand}
      />

      {launcherMode === "unified" && menuOpen ? (
        <SplitTrayMenu
          theme={theme}
          scheme={scheme}
          suflerOpen={suflerOpen}
          assistantOpen={assistantOpen}
          onPick={onPickWindow}
        />
      ) : null}

      <div style={portalHeader}>
        <Text style={{ fontSize: 11, color: theme.text.quaternary }}>Главная · Заявки · База знаний · КЦ</Text>
      </div>

      {launcherMode === "unified" ? (
        <button type="button" style={portalBtn} onClick={onToggleMenu}>
          <div
            style={{
              width: 18,
              height: 18,
              borderRadius: 3,
              background: scheme.accentControl,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Text style={{ fontSize: 9, color: theme.text.onAccent, fontWeight: 700 }}>
              AI
            </Text>
          </div>
          <Text style={{ fontSize: 11, fontWeight: 600 }}>Hub</Text>
          <Pill tone="neutral" size="sm">
            2
          </Pill>
        </button>
      ) : launcherMode === "dual" ? (
        <div
          style={{
            position: "absolute",
            right: 14,
            bottom: 12,
            display: "flex",
            alignItems: "center",
            gap: 8,
            zIndex: 7,
          }}
        >
          <ModuleWidgetButton
            theme={theme}
            scheme={scheme}
            label="Суфлёр"
            glyph="S"
            active={suflerOpen}
            onClick={() => onPickWindow("sufler")}
          />
          <ModuleWidgetButton
            theme={theme}
            scheme={scheme}
            label="Ассистент"
            glyph="A"
            active={assistantOpen}
            onClick={() => onPickWindow("assistant")}
          />
        </div>
      ) : (
        <CompactLauncherDock
          theme={theme}
          scheme={scheme}
          menuOpen={menuOpen}
          suflerOpen={suflerOpen}
          assistantOpen={assistantOpen}
          onToggleMenu={onToggleMenu}
          onPick={onPickWindow}
        />
      )}
    </div>
  );
}

function SpecPanel({
  theme,
  scheme,
  launcherMode,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  launcherMode: LauncherMode;
}): JSX.Element {
  const unifiedRows: [string, string][] = [
    ["Кнопка портала", "AI Hub находится в правом нижнем углу внутреннего корпоративного портала банка"],
    ["Выбор иконки", "По нажатию появляются две иконки: «Ассистент» и «Суфлёр»"],
    ["Открытие окна", "Выбор иконки открывает соответствующее стартовое окно"],
    ["Ресайз", "Высота превью портала и углы окон суфлёра/ассистента — перетаскивание"],
    ["Повторный вызов", "Кнопка AI Hub всегда возвращает меню выбора модулей"],
    ["Одновременно", "Оба окна могут быть открыты параллельно"],
    ["Суфлёр ≠ Hub", "Суфлёр — отдельное окно, не вкладка оболочки Hub"],
    ["Трассировка", "Сценарии повторного вызова и параллельной работы окон"],
  ];
  const dualRows: [string, string][] = [
    ["Два виджета", "В правом нижнем углу — отдельные кнопки «Суфлёр» и «Ассистент»"],
    ["Прямой вызов", "Клик по виджету сразу открывает стартовое окно модуля, без меню выбора"],
    ["Открытие окна", "Суфлёр — окно телефонии/чата; Ассистент — окно вне сессии"],
    ["Ресайз", "Высота превью портала и углы окон суфлёра/ассистента — перетаскивание"],
    ["Повторный вызов", "Повторный клик по виджету открывает или фокусирует то же окно"],
    ["Одновременно", "Оба окна могут быть открыты параллельно"],
    ["Суфлёр ≠ Hub", "Суфлёр — отдельное окно, не вкладка оболочки Hub"],
    ["Варианты", "Два виджета — прямой вызов без меню выбора"],
  ];
  const compactRows: [string, string][] = [
    ["Компактная кнопка", "Минимальное круглое окошко AI в правом нижнем углу"],
    ["Выезд иконок", "По клику влево выезжают две круглые иконки с подписями"],
    ["Дизайн", "Круглые FAB, подпись в pill, активное кольцо при открытом окне"],
    ["Открытие окна", "Клик по иконке открывает стартовое окно модуля"],
    ["Ресайз", "Высота превью портала и углы окон суфлёра/ассистента — перетаскивание"],
    ["Повторный вызов", "Повторный клик AI сворачивает/разворачивает иконки"],
    ["Одновременно", "Оба окна могут быть открыты параллельно"],
    ["Варианты", "Три схемы лаунчера (unified / dual / compact) в одном макете"],
  ];
  const rows =
    launcherMode === "unified" ? unifiedRows : launcherMode === "dual" ? dualRows : compactRows;

  return (
    <Card style={{ borderColor: scheme.accentWeak }}>
      <CardHeader>Требования к макету</CardHeader>
      <CardBody>
        <Grid columns={3} style={{ gap: 12, alignItems: "start" }}>
          {rows.map(([k, v]) => (
            <div key={k}>
              <Text weight="semibold" style={{ fontSize: 12 }}>
                {k}
              </Text>
              <Text style={{ fontSize: 11, color: theme.text.secondary, marginTop: 2, lineHeight: 1.45 }}>{v}</Text>
            </div>
          ))}
        </Grid>
      </CardBody>
    </Card>
  );
}

export default function TrayLauncherMockup(): JSX.Element {
  const theme = useHostTheme();
  const [colorScheme, setColorScheme] = useCanvasState<ColorScheme>("trayLauncherColorScheme", "default");
  const [suflerOpen, setSuflerOpen] = useCanvasState("suflerOpen", false);
  const [suflerExpanded, setSuflerExpanded] = useCanvasState("suflerExpanded", false);
  const [portalHeight, setPortalHeight] = useCanvasState("trayLauncherPortalHeight", DEFAULT_PORTAL_HEIGHT);
  const [suflerWidth, setSuflerWidth] = useCanvasState("trayLauncherSuflerWidth", 620);
  const [suflerHeight, setSuflerHeight] = useCanvasState("trayLauncherSuflerHeight", 380);
  const [assistantOpen, setAssistantOpen] = useCanvasState("assistantOpen", false);
  const [assistantExpanded, setAssistantExpanded] = useCanvasState("assistantExpanded", false);
  const [assistantWidth, setAssistantWidth] = useCanvasState("trayLauncherAssistantWidth", 400);
  const [assistantHeight, setAssistantHeight] = useCanvasState("trayLauncherAssistantHeight", 520);
  const [menuOpen, setMenuOpen] = useCanvasState("menuOpen", true);
  const [launcherMode, setLauncherMode] = useCanvasState<LauncherMode>("trayLauncherMode", "unified");
  const [preset, setPreset] = useCanvasState<PresetId>("preset", "menu_open");
  const [canvasBuild, setCanvasBuild] = useCanvasState("_canvasBuild", "");

  const scheme = getSchemePalette(theme, colorScheme);

  useEffect(() => {
    if (canvasBuild !== CANVAS_MOCKUP_VERSION) {
      setCanvasBuild(CANVAS_MOCKUP_VERSION);
    }
  }, [canvasBuild, setCanvasBuild]);

  const boundedPortalHeight = clampPortalPreviewHeight(portalHeight);

  const setPortalHeightBounded = (h: number) => {
    setPortalHeight(clampPortalPreviewHeight(h));
  };

  const setSuflerSize = (w: number, h: number) => {
    const next = clampSuflerSize(w, h, boundedPortalHeight);
    setSuflerWidth(next.w);
    setSuflerHeight(next.h);
  };

  const setAssistantSize = (w: number, h: number) => {
    const next = clampAssistantSize(w, h, boundedPortalHeight);
    setAssistantWidth(next.w);
    setAssistantHeight(next.h);
  };

  const cycleColorScheme = () => {
    const currentIndex = COLOR_SCHEME_ORDER.indexOf(colorScheme);
    const nextIndex = (currentIndex + 1) % COLOR_SCHEME_ORDER.length;
    setColorScheme(COLOR_SCHEME_ORDER[nextIndex]);
  };

  const pickWindow = (target: WindowKey): void => {
    if (target === "sufler") setSuflerOpen(true);
    else setAssistantOpen(true);
    setMenuOpen(false);
    if (target === "sufler") setSuflerExpanded(false);
    else setAssistantExpanded(false);
    setPreset(
      target === "sufler" && assistantOpen
        ? "both_open"
        : target === "assistant" && suflerOpen
          ? "both_open"
          : target === "sufler"
            ? "sufler_only"
            : "assistant_only",
    );
  };

  const minimize = (target: WindowKey): void => {
    if (target === "sufler") {
      setSuflerOpen(false);
      setSuflerExpanded(false);
    } else {
      setAssistantOpen(false);
      setAssistantExpanded(false);
    }
    if (!suflerOpen && !assistantOpen) setPreset("both_closed");
    else if (target === "sufler" && assistantOpen) setPreset("assistant_only");
    else if (target === "assistant" && suflerOpen) setPreset("sufler_only");
    else setPreset("both_closed");
  };

  const onPresetChange = (id: PresetId): void => {
    setPreset(id);
    applyPreset(id, setSuflerOpen, setAssistantOpen, setMenuOpen);
    if (id !== "both_open") setSuflerExpanded(false);
    if (id !== "both_open") setAssistantExpanded(false);
  };

  const statusLabel =
    suflerOpen && assistantOpen
      ? "Оба окна открыты"
      : suflerOpen
        ? "Открыт суфлёр"
        : assistantOpen
          ? "Открыт ассистент"
          : launcherMode === "unified" && menuOpen
            ? "Меню выбора на портале"
            : launcherMode === "compact" && menuOpen
              ? "Иконки модулей выезжают"
              : "Оба свёрнуты";

  const presetOptions =
    launcherMode === "dual" ? PRESETS.filter((p) => p.id !== "menu_open") : PRESETS;

  const onLauncherModeChange = (mode: LauncherMode): void => {
    setLauncherMode(mode);
    if (mode === "dual") {
      setMenuOpen(false);
      if (preset === "menu_open") setPreset("both_closed");
    }
  };

  return (
    <Stack
      style={{
        gap: 16,
        padding: 16,
        width: "100%",
        maxWidth: "100%",
        borderRadius: 10,
        border: `1px solid ${scheme.accentWeak}`,
        background: scheme.panelBg,
      }}
    >
      <div>
        <H1>Портальный лаунчер: Суфлёр / Ассистент</H1>
      </div>

      <Callout tone="info">
        {launcherMode === "unified" ? (
          <>
            Кликните кнопку <Text weight="semibold">AI Hub</Text> в правом нижнем углу портала. Затем выберите иконку модуля
            («Ассистент» или «Суфлёр») — откроется соответствующее стартовое окно. Размер меняется за угол, как в других
            макетах. Суфлёр — <Text weight="semibold">отдельное окно</Text>, не вкладка оболочки Hub.
          </>
        ) : launcherMode === "dual" ? (
          <>
            В правом нижнем углу — два отдельных виджета <Text weight="semibold">Суфлёр</Text> и{" "}
            <Text weight="semibold">Ассистент</Text>. Клик по виджету сразу открывает стартовое окно модуля без меню выбора.
            Оба окна могут быть открыты одновременно.
          </>
        ) : (
          <>
            Компактная круглая кнопка <Text weight="semibold">AI</Text> в углу портала. По клику влево выезжают две иконки
            модулей с подписями — выберите <Text weight="semibold">Суфлёр</Text> или{" "}
            <Text weight="semibold">Ассистент</Text> для открытия стартового окна.
          </>
        )}
      </Callout>

      <Row style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <Text style={{ fontSize: 12, color: theme.text.secondary }}>Вариант лаунчера:</Text>
        <Pill active={launcherMode === "unified"} onClick={() => onLauncherModeChange("unified")}>
          A · AI Hub + меню
        </Pill>
        <Pill active={launcherMode === "dual"} onClick={() => onLauncherModeChange("dual")}>
          B · Два виджета
        </Pill>
        <Pill active={launcherMode === "compact"} onClick={() => onLauncherModeChange("compact")}>
          C · Компактный AI
        </Pill>
      </Row>

      <Row style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <Text style={{ fontSize: 12, color: theme.text.secondary }}>Схема:</Text>
        <Pill active={colorScheme === "default"} onClick={() => setColorScheme("default")}>
          Текущая
        </Pill>
        <Pill active={colorScheme === "belarusbank_classic"} onClick={() => setColorScheme("belarusbank_classic")}>
          Classic
        </Pill>
        <Pill active={colorScheme === "belarusbank_soft"} onClick={() => setColorScheme("belarusbank_soft")}>
          Soft
        </Pill>
        <Pill active={colorScheme === "belarusbank_emerald"} onClick={() => setColorScheme("belarusbank_emerald")}>
          Emerald
        </Pill>
        <Pill active={colorScheme === "belarusbank_night"} onClick={() => setColorScheme("belarusbank_night")}>
          Night
        </Pill>
        <Button variant="ghost" size="sm" onClick={cycleColorScheme} title="Сменить цветовую схему">
          ◐
        </Button>
      </Row>
      <Row style={{ gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <Text style={{ fontSize: 12, color: theme.text.secondary }}>Пресет состояния:</Text>
        <Select
          value={preset}
          onChange={(v) => onPresetChange(v as PresetId)}
          options={presetOptions.map((p) => ({ value: p.id, label: p.label }))}
        />
        <Pill tone="info">{statusLabel}</Pill>
      </Row>

      <SpecPanel theme={theme} scheme={scheme} launcherMode={launcherMode} />

      <Stack style={{ gap: 12, width: "100%" }}>
        <Row style={{ gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
          <H2 style={{ color: scheme.accentControl }}>Интерактивный экран портала</H2>
          <Text style={{ fontSize: 11, color: theme.text.tertiary }}>
            на всю ширину · высота {boundedPortalHeight}px · ресайз за угол
          </Text>
        </Row>
        <PortalPreviewFrame
          theme={theme}
          scheme={scheme}
          height={portalHeight}
          setHeight={setPortalHeightBounded}
        >
          <DesktopMock
            theme={theme}
            scheme={scheme}
            launcherMode={launcherMode}
            portalHeight={boundedPortalHeight}
            suflerOpen={suflerOpen}
            suflerExpanded={suflerExpanded}
            suflerWidth={suflerWidth}
            suflerHeight={suflerHeight}
            setSuflerSize={setSuflerSize}
            assistantOpen={assistantOpen}
            assistantExpanded={assistantExpanded}
            assistantWidth={assistantWidth}
            assistantHeight={assistantHeight}
            setAssistantSize={setAssistantSize}
            menuOpen={menuOpen}
            onToggleMenu={() => {
              setMenuOpen((m) => !m);
              setPreset((p) => (menuOpen ? p : "menu_open"));
            }}
            onPickWindow={pickWindow}
            onMinimize={minimize}
            onToggleSuflerExpand={() => setSuflerExpanded((v) => !v)}
            onToggleAssistantExpand={() => setAssistantExpanded((v) => !v)}
          />
        </PortalPreviewFrame>
        <Row style={{ gap: 8, flexWrap: "wrap" }}>
          <Button
            variant={suflerOpen ? "primary" : "secondary"}
            size="sm"
            style={suflerOpen ? { background: scheme.accentControl, borderColor: scheme.accentControl } : undefined}
            onClick={() => {
              setSuflerOpen((o) => !o);
              setMenuOpen(false);
            }}
          >
            {suflerOpen ? "Скрыть суфлёр" : "Показать суфлёр"}
          </Button>
          <Button
            variant={assistantOpen ? "primary" : "secondary"}
            size="sm"
            style={assistantOpen ? { background: scheme.accentControl, borderColor: scheme.accentControl } : undefined}
            onClick={() => {
              setAssistantOpen((o) => !o);
              setMenuOpen(false);
            }}
          >
            {assistantOpen ? "Скрыть ассистент" : "Показать ассистент"}
          </Button>
          {launcherMode !== "dual" ? (
            <Button variant="ghost" size="sm" onClick={() => onPresetChange("menu_open")}>
              {launcherMode === "compact" ? "Показать выезд иконок" : "Показать меню выбора"}
            </Button>
          ) : null}
        </Row>
      </Stack>

      <Card style={{ borderColor: scheme.accentWeak }}>
        <CardHeader>Вариант A: один виджет AI Hub</CardHeader>
        <CardBody>
          <div
            style={{
              border: `1px solid ${scheme.accentWeak}`,
              borderRadius: 8,
              overflow: "hidden",
            }}
          >
            <Row>
              <div
                style={{
                  flex: 1,
                  padding: 12,
                  background: scheme.headerBg,
                  borderRight: `1px solid ${scheme.accentWeak}`,
                }}
              >
                <Text weight="semibold" style={{ fontSize: 12 }}>
                  Меню выбора
                </Text>
                <Text style={{ fontSize: 11, color: theme.text.secondary, marginTop: 4 }}>
                  Клик AI Hub → выбор «Суфлёр» или «Ассистент»
                </Text>
              </div>
              <div style={{ flex: 1, padding: 12, background: scheme.panelBg }}>
                <Text weight="semibold" style={{ fontSize: 12 }}>
                  Стартовое окно
                </Text>
                <Text style={{ fontSize: 11, color: theme.text.secondary, marginTop: 4 }}>
                  Открывается после выбора в меню
                </Text>
              </div>
            </Row>
          </div>
        </CardBody>
      </Card>

      <Card style={{ borderColor: scheme.accentWeak }}>
        <CardHeader>Вариант B: два отдельных виджета</CardHeader>
        <CardBody>
          <div
            style={{
              border: `1px solid ${scheme.accentWeak}`,
              borderRadius: 8,
              overflow: "hidden",
            }}
          >
            <Row>
              <div
                style={{
                  flex: 1,
                  padding: 12,
                  background: scheme.headerBg,
                  borderRight: `1px solid ${scheme.accentWeak}`,
                }}
              >
                <Text weight="semibold" style={{ fontSize: 12 }}>
                  Виджет «Суфлёр»
                </Text>
                <Text style={{ fontSize: 11, color: theme.text.secondary, marginTop: 4 }}>Телефония / чат · прямой вызов</Text>
              </div>
              <div style={{ flex: 1, padding: 12, background: scheme.panelBg }}>
                <Text weight="semibold" style={{ fontSize: 12 }}>
                  Виджет «Ассистент»
                </Text>
                <Text style={{ fontSize: 11, color: theme.text.secondary, marginTop: 4 }}>ИИ-ассистент · прямой вызов</Text>
              </div>
            </Row>
          </div>
          <Divider style={{ margin: "12px 0" }} />
          <Text style={{ fontSize: 11, color: theme.text.tertiary, lineHeight: 1.5 }}>
            Переключите «Вариант лаунчера» выше, чтобы интерактивно сравнить все три варианта на экране портала.
          </Text>
        </CardBody>
      </Card>

      <Card style={{ borderColor: scheme.accentWeak }}>
        <CardHeader>Вариант C: компактный AI + выезд иконок</CardHeader>
        <CardBody>
          <div
            style={{
              border: `1px solid ${scheme.accentWeak}`,
              borderRadius: 8,
              overflow: "hidden",
            }}
          >
            <Row>
              <div
                style={{
                  flex: 1,
                  padding: 12,
                  background: scheme.headerBg,
                  borderRight: `1px solid ${scheme.accentWeak}`,
                }}
              >
                <Text weight="semibold" style={{ fontSize: 12 }}>
                  Кнопка AI
                </Text>
                <Text style={{ fontSize: 11, color: theme.text.secondary, marginTop: 4 }}>
                  Минимальное круглое окошко · клик разворачивает иконки
                </Text>
              </div>
              <div style={{ flex: 1, padding: 12, background: scheme.panelBg }}>
                <Text weight="semibold" style={{ fontSize: 12 }}>
                  Иконки модулей
                </Text>
                <Text style={{ fontSize: 11, color: theme.text.secondary, marginTop: 4 }}>
                  Круглые FAB с подписями · выезд влево от кнопки AI
                </Text>
              </div>
            </Row>
          </div>
        </CardBody>
      </Card>
    </Stack>
  );
}
