import {
  Button,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  Divider,
  Grid,
  H1,
  H2,
  IconButton,
  Pill,
  Row,
  Select,
  Spacer,
  Stack,
  Stat,
  Table,
  Text,
  TextArea,
  TextInput,
  Toggle,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";
import type { CanvasHostTheme } from "cursor/canvas";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties, JSX, PointerEvent as ReactPointerEvent } from "react";

const PANEL_MIN_W = 360;
const PANEL_MAX_W = 960;
const PANEL_MIN_H = 420;
const PANEL_MAX_H = 860;

function clampPanelSize(width: number, height: number): { w: number; h: number } {
  return {
    w: Math.max(PANEL_MIN_W, Math.min(PANEL_MAX_W, Math.round(width))),
    h: Math.max(PANEL_MIN_H, Math.min(PANEL_MAX_H, Math.round(height))),
  };
}

type FeedbackChipChoice = "used" | "not_used" | "partial";

type FeedbackChipPalette = {
  idleBg: string;
  idleBorder: string;
  activeBg: string;
  activeBorder: string;
  activeColor: string;
};

/** Разноцветные чипы оценки (как в суфлёре): зелёный / сине-серый / янтарный. */
function feedbackChipPalette(_t: CanvasHostTheme, choice: FeedbackChipChoice): FeedbackChipPalette {
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

function feedbackChipStyle(
  t: CanvasHostTheme,
  choice: FeedbackChipChoice,
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

const SUFLER_FEEDBACK_OPTIONS: { id: FeedbackChipChoice; label: string }[] = [
  { id: "used", label: "Воспользовался" },
  { id: "not_used", label: "Не воспользовался" },
  { id: "partial", label: "Неполный ответ" },
];

const ASSISTANT_FEEDBACK_OPTIONS: { id: FeedbackChipChoice; label: string }[] = [
  { id: "used", label: "Полезно" },
  { id: "partial", label: "Неполный ответ" },
  { id: "not_used", label: "Неверно" },
];

function FeedbackChipRow({
  t,
  options,
  stateKey,
}: {
  t: CanvasHostTheme;
  options: { id: FeedbackChipChoice; label: string }[];
  stateKey: string;
}): JSX.Element {
  const [selected, setSelected] = useCanvasState<FeedbackChipChoice | null>(stateKey, null);

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

/** Роли ПО — по Прил. 1 и планам ТЗ модулей (не вымышленные AD-группы). */
type RoleId =
  | "system_admin"
  | "cc_admin"
  | "cc_operator"
  | "cc_supervisor"
  | "cc_internal_user"
  | "analyst"
  | "assistant_user"
  | "kb_admin"
  | "doc_verifier"
  | "doc_type_admin"
  | "auditor";

type MainTab = "assistant" | "documents";
type OcrSubTab = "queue" | "upload" | "review";
type AssistantSlide = "chat" | "clarify" | "tools" | "summary" | "translate";
type ColorScheme =
  | "default"
  | "belarusbank_classic"
  | "belarusbank_soft"
  | "belarusbank_emerald"
  | "belarusbank_night";

const WINDOW_CONTROLS_WIDTH = 108;

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

type SchemePalette = {
  label: string;
  accent: string;
  accentWeak: string;
  accentControl: string;
  headerBg: string;
  panelBg: string;
  badge: string;
};

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

type TranscriptLine = {
  id: string;
  speaker: "client" | "operator";
  text: string;
};

type HintCard = {
  id: string;
  utteranceId: string;
  title: string;
  text: string;
  relevance: number;
  tone: "success" | "info" | "warning";
  article?: string;
};

const INITIAL_UTTERANCES: TranscriptLine[] = [
  { id: "u1", speaker: "client", text: "Хочу закрыть вклад, что для этого нужно?" },
  { id: "u2", speaker: "operator", text: "Сейчас подскажу порядок действий…" },
];

const INITIAL_HINTS: HintCard[] = [
  {
    id: "h1",
    utteranceId: "u1",
    title: "Подсказка",
    text: "Порядок закрытия: проверить остаток и аресты → заявление в отделении или интернет-банк.",
    relevance: 92,
    tone: "success",
    article: "Закрытие вклада физлиц",
  },
  {
    id: "h1b",
    utteranceId: "u1",
    title: "Подсказка",
    text: "При наличии автоплатежей и привязок к карте — предупредите о необходимости отключить их до закрытия.",
    relevance: 84,
    tone: "info",
    article: "Автоплатежи при закрытии",
  },
  {
    id: "h1c",
    utteranceId: "u1",
    title: "Подсказка",
    text: "Срок зачисления остатка на счёт зачисления — до 3 рабочих дней после подписания заявления.",
    relevance: 76,
    tone: "warning",
    article: "Сроки зачисления остатка",
  },
];

const NEXT_CLIENT_REPLIES: { text: string; hints: Omit<HintCard, "id" | "utteranceId">[] }[] = [
  {
    text: "У меня срочный вклад, можно закрыть досрочно?",
    hints: [
      {
        title: "Подсказка 3",
        text: "При досрочном закрытии срочного вклада проценты пересчитываются по ставке «до востребования». Предупредите клиента о возможной потере дохода.",
        relevance: 88,
        tone: "success",
        article: "Досрочное закрытие вклада",
      },
    ],
  },
  {
    text: "А если на вкладе есть арест?",
    hints: [
      {
        title: "Подсказка 4",
        text: "Закрытие при аресте невозможно до снятия ограничений. Направьте клиента в отделение с документами об основании ареста.",
        relevance: 95,
        tone: "warning",
        article: "Арест на счёте",
      },
    ],
  },
];

type RoleConfig = {
  label: string;
  source: string;
  subtitle: string;
  tabs: { assistant: boolean; documents: boolean };
  /** Суфлёр — отдельный интерфейс (протокол 23.06 §3.4), не вкладка Hub */
  suflerInterface: string | null;
};

const ROLES: Record<RoleId, RoleConfig> = {
  system_admin: {
    label: "Администратор системы",
    source: "Core Platform",
    subtitle: "Козлов Д.В.",
    tabs: { assistant: true, documents: true },
    suflerInterface: null,
  },
  cc_admin: {
    label: "Администратор КЦ",
    source: "Администрирование КЦ",
    subtitle: "Новикова Е.П.",
    tabs: { assistant: false, documents: false },
    suflerInterface: "Центр настроек / АРМ (не Hub в смене)",
  },
  cc_operator: {
    label: "Оператор КЦ · телефония",
    source: "Суфлёр · телефония",
    subtitle: "Иванов И.И.",
    tabs: { assistant: false, documents: false },
    suflerInterface: "Отдельное окно · Суфлёр · телефония",
  },
  cc_supervisor: {
    label: "Супервайзер КЦ",
    source: "Онлайн-чат",
    subtitle: "Морозова Т.В.",
    tabs: { assistant: false, documents: false },
    suflerInterface: "АРМ супервизора · Онлайн-чат",
  },
  cc_internal_user: {
    label: "Внутренний пользователь КЦ",
    source: "Тестирование баз знаний",
    subtitle: "Лебедев А.Н.",
    tabs: { assistant: true, documents: false },
    suflerInterface: "Тест-диалог · внутренний пользователь КЦ",
  },
  analyst: {
    label: "Аналитик",
    source: "Отчётность",
    subtitle: "Волкова М.С.",
    tabs: { assistant: false, documents: true },
    suflerInterface: null,
  },
  assistant_user: {
    label: "Пользователь ИИ-ассистента",
    source: "ИИ-ассистент",
    subtitle: "Сидоров П.К.",
    tabs: { assistant: true, documents: false },
    suflerInterface: null,
  },
  kb_admin: {
    label: "Администратор баз знаний",
    source: "Управление базами знаний",
    subtitle: "Орлова В.И.",
    tabs: { assistant: true, documents: false },
    suflerInterface: null,
  },
  doc_verifier: {
    label: "Оператор/верификатор документов",
    source: "OCR / IDP",
    subtitle: "Петрова А.С.",
    tabs: { assistant: false, documents: true },
    suflerInterface: null,
  },
  doc_type_admin: {
    label: "Администратор типов документов",
    source: "OCR / IDP",
    subtitle: "Кравцов О.Л.",
    tabs: { assistant: false, documents: true },
    suflerInterface: null,
  },
  auditor: {
    label: "Read-only просмотр",
    source: "Security & Audit",
    subtitle: "Зайцева Л.Р.",
    tabs: { assistant: true, documents: true },
    suflerInterface: null,
  },
};

const ROLE_OPTIONS: { value: RoleId; label: string }[] = [
  { value: "system_admin", label: "Администратор системы" },
  { value: "cc_admin", label: "Администратор КЦ" },
  { value: "cc_operator", label: "Оператор КЦ" },
  { value: "cc_supervisor", label: "Супервайзер КЦ" },
  { value: "cc_internal_user", label: "Внутренний пользователь КЦ" },
  { value: "analyst", label: "Аналитик" },
  { value: "assistant_user", label: "Пользователь ИИ-ассистента" },
  { value: "kb_admin", label: "Администратор баз знаний" },
  { value: "doc_verifier", label: "Оператор/верификатор документов" },
  { value: "doc_type_admin", label: "Администратор типов документов" },
  { value: "auditor", label: "Read-only просмотр" },
];

const MAIN_TABS: { id: MainTab; label: string }[] = [
  { id: "assistant", label: "Ассистент" },
  { id: "documents", label: "Документы" },
];

function firstAllowedTab(tabs: RoleConfig["tabs"]): MainTab {
  if (tabs.assistant) return "assistant";
  if (tabs.documents) return "documents";
  return "assistant";
}

function hubHasAnyTab(tabs: RoleConfig["tabs"]): boolean {
  return tabs.assistant || tabs.documents;
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
    <Row gap={8} wrap>
      {entries.map((entry) => (
        <Row key={entry.key} gap={6} align="center" style={{ padding: "2px 6px", borderRadius: 6, border: `1px solid ${theme.stroke.tertiary}` }}>
          <span
            aria-label={entry.key}
            style={{
              width: 12,
              height: 12,
              borderRadius: 3,
              background: entry.value,
              display: "inline-block",
              border: `1px solid ${theme.stroke.tertiary}`,
            }}
          />
          <Text size={10} tone="secondary">
            {entry.key}
          </Text>
        </Row>
      ))}
    </Row>
  );
}

function AdminCenterPreview({
  theme,
  scheme,
  onBack,
  onMinimize,
  onMaximize,
  onClose,
  maximized,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  onBack: () => void;
  onMinimize?: () => void;
  onMaximize?: () => void;
  onClose?: () => void;
  maximized?: boolean;
}): JSX.Element {
  const adminNav = [
    { group: "ОБЩЕЕ", items: ["Подразделения и журнал"] },
    { group: "АССИСТЕНТ", items: ["★ Конфигурация LLM", "Параметры модели LLM", "Промпты ассистента"] },
    { group: "СУФЛЁР / КЦ", items: ["★ Конфигурация LLM КЦ", "Редактор сценариев", "Тест сценария"] },
    { group: "ДОКУМЕНТЫ", items: ["Типы документов"] },
  ];
  return (
    <div
      style={{
        width: "100%",
        minHeight: 520,
        display: "flex",
        flexDirection: "column",
        border: `1px solid ${scheme.accentWeak}`,
        borderRadius: 12,
        overflow: "hidden",
        background: theme.bg.elevated,
      }}
    >
      <div
        style={{
          position: "relative",
          padding: "10px 14px",
          paddingRight: WINDOW_CONTROLS_WIDTH,
          borderBottom: `1px solid ${theme.stroke.tertiary}`,
          background: scheme.headerBg,
        }}
      >
        <Row gap={8} align="center">
          <Button variant="ghost" size="sm" onClick={onBack}>
            ← Панель AI
          </Button>
          <H2 style={{ margin: 0, fontSize: 16, color: scheme.accentControl }}>Центр настроек AI Hub</H2>
          <Pill tone="neutral" size="sm">
            /ai-hub/admin
          </Pill>
        </Row>
        <WindowTitleBarControls
          theme={theme}
          onMinimize={onMinimize}
          onMaximize={onMaximize}
          onClose={onClose ?? onBack}
          maximized={maximized}
        />
      </div>
      <Row align="stretch" style={{ flex: 1, minHeight: 460 }}>
        <nav
          style={{
            width: 240,
            padding: 12,
            borderRight: `1px solid ${theme.stroke.tertiary}`,
            background: theme.fill.tertiary,
          }}
        >
          <Stack gap={10}>
            {adminNav.map(({ group, items }) => (
              <Stack key={group} gap={4}>
                <Text tone="secondary" size={11}>
                  {group}
                </Text>
                {items.map((label) => (
                  <Text key={label} size={12} tone={label.startsWith("★") ? "primary" : "secondary"}>
                    {label}
                  </Text>
                ))}
              </Stack>
            ))}
          </Stack>
        </nav>
        <Stack gap={12} style={{ flex: 1, padding: 20 }}>
          <Text tone="secondary" size={11}>
            Конфигурация LLM · assistant_bank
          </Text>
          <Row gap={12} wrap>
            <Stat label="Слои" value="7" tone="neutral" />
            <Stat label="Профиль" value="assistant_bank" tone="success" />
            <Stat label="Preset" value="настроен" tone="neutral" />
          </Row>
          <Callout tone="info">
            Полный интерактивный макет (18 экранов, RBAC, редактор сценариев) — canvas{" "}
            <strong>ai-hub-settings-mockup</strong>. В чате: «Open canvas ai-hub-settings-mockup».
          </Callout>
        </Stack>
      </Row>
    </div>
  );
}

function PanelShell({
  theme,
  scheme,
  roleConfig,
  activeTab,
  setActiveTab,
  panelWidth,
  panelHeight,
  pinned,
  setPinned,
  onClose,
  onMinimize,
  setPanelSize,
  children,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  roleConfig: RoleConfig;
  activeTab: MainTab;
  setActiveTab: (t: MainTab) => void;
  panelWidth: number;
  panelHeight: number;
  pinned: boolean;
  setPinned: (v: boolean) => void;
  onClose: () => void;
  onMinimize: () => void;
  setPanelSize: (nextWidth: number, nextHeight: number) => void;
  children: JSX.Element;
}): JSX.Element {
  const [menuOpen, setMenuOpen] = useCanvasState("hubMenuOpen", false);
  const [, setAdminCenterOpen] = useCanvasState("hubAdminCenterOpen", false);
  const [isResizing, setIsResizing] = useState(false);
  const [liveSize, setLiveSize] = useState<{ w: number; h: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const liveSizeRef = useRef<{ w: number; h: number } | null>(null);
  const boundedWidth = clampPanelSize(panelWidth, panelHeight).w;
  const boundedHeight = clampPanelSize(panelWidth, panelHeight).h;
  const displayWidth = liveSize?.w ?? boundedWidth;
  const displayHeight = liveSize?.h ?? boundedHeight;
  const schemeBorder = scheme.accentWeak;
  const schemeHeader = scheme.headerBg;

  useEffect(() => {
    if (isResizing) return;
    setLiveSize(null);
    liveSizeRef.current = null;
  }, [panelWidth, panelHeight, isResizing]);

  const handleTabClick = (tabId: MainTab) => {
    if (!roleConfig.tabs[tabId]) return;
    setActiveTab(tabId);
  };

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (pinned) setPinned(false);

    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);

    const startX = event.clientX;
    const startY = event.clientY;
    const initialWidth = displayWidth;
    const initialHeight = displayHeight;

    setIsResizing(true);
    document.body.style.cursor = "nwse-resize";
    document.body.style.userSelect = "none";

    const applySize = (width: number, height: number) => {
      const next = clampPanelSize(width, height);
      liveSizeRef.current = next;
      setLiveSize(next);
      if (panelRef.current) {
        panelRef.current.style.width = `${next.w}px`;
        panelRef.current.style.height = `${next.h}px`;
      }
    };

    const handleMove = (moveEvent: globalThis.PointerEvent) => {
      if (moveEvent.pointerId !== event.pointerId) return;
      applySize(
        initialWidth + moveEvent.clientX - startX,
        initialHeight + moveEvent.clientY - startY,
      );
    };

    const finish = (upEvent: globalThis.PointerEvent) => {
      if (upEvent.pointerId !== event.pointerId) return;
      handle.releasePointerCapture(event.pointerId);
      handle.removeEventListener("pointermove", handleMove);
      handle.removeEventListener("pointerup", finish);
      handle.removeEventListener("pointercancel", finish);
      const finalSize = liveSizeRef.current ?? clampPanelSize(initialWidth, initialHeight);
      setPanelSize(finalSize.w, finalSize.h);
      liveSizeRef.current = null;
      setLiveSize(null);
      setIsResizing(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    handle.addEventListener("pointermove", handleMove);
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
  };

  const panelStyle: CSSProperties = {
    width: displayWidth,
    height: displayHeight,
    display: "flex",
    flexDirection: "column",
    background: theme.bg.elevated,
    border: `1px solid ${schemeBorder}`,
    borderRadius: 12,
    overflow: "hidden",
    position: "relative",
    flexShrink: 0,
    transition: isResizing ? "none" : "width 160ms ease, height 160ms ease",
  };

  return (
    <div ref={panelRef} style={panelStyle}>
      <div
        style={{
          position: "relative",
          padding: "10px 12px",
          paddingRight: WINDOW_CONTROLS_WIDTH,
          borderBottom: `1px solid ${theme.stroke.tertiary}`,
          background: schemeHeader,
        }}
      >
        <Row gap={6} align="center">
          <div style={{ position: "relative" }}>
            <IconButton
              title="Меню"
              onClick={() => setMenuOpen((open) => !open)}
            >
              ≡
            </IconButton>
            {menuOpen && (
              <div
                style={{
                  position: "absolute",
                  top: "100%",
                  left: 0,
                  marginTop: 4,
                  minWidth: 220,
                  zIndex: 20,
                  background: theme.bg.elevated,
                  border: `1px solid ${theme.stroke.secondary}`,
                  borderRadius: 8,
                  padding: 4,
                }}
              >
                <Button
                  variant="ghost"
                  size="sm"
                  style={{ width: "100%", justifyContent: "flex-start" }}
                  onClick={() => {
                    setMenuOpen(false);
                    setAdminCenterOpen(true);
                  }}
                >
                  Центр настроек
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  style={{ width: "100%", justifyContent: "flex-start" }}
                  onClick={() => setMenuOpen(false)}
                >
                  БЗ · полное окно
                </Button>
              </div>
            )}
          </div>
          <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
            <Text weight="semibold" size={13}>
              Беларусбанк AI
            </Text>
            <Text tone="secondary" size={11} truncate>
              {roleConfig.subtitle} · {roleConfig.label}
            </Text>
          </Stack>
        </Row>
        <WindowTitleBarControls
          theme={theme}
          onMinimize={onMinimize}
          onMaximize={() => {
            const nextPinned = !pinned;
            setPinned(nextPinned);
            if (nextPinned) setPanelSize(PANEL_MAX_W, PANEL_MAX_H);
          }}
          onClose={onClose}
          maximized={pinned}
        />
      </div>

      <Row
        gap={0}
        style={{
          borderBottom: `1px solid ${theme.stroke.tertiary}`,
        }}
      >
        {MAIN_TABS.map((tab) => {
          const allowed = roleConfig.tabs[tab.id];
          const isActive = activeTab === tab.id;
          if (!allowed) {
            return (
              <button
                key={tab.id}
                type="button"
                disabled
                title="Нет доступа (RBAC)"
                style={{
                  flex: 1,
                  padding: "10px 8px",
                  border: "none",
                  borderBottom: "2px solid transparent",
                  background: "transparent",
                  color: theme.text.tertiary,
                  fontWeight: 400,
                  fontSize: 12,
                  cursor: "not-allowed",
                  opacity: 0.45,
                }}
              >
                {tab.label}
              </button>
            );
          }
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => handleTabClick(tab.id)}
              style={{
                flex: 1,
                padding: "10px 8px",
                border: "none",
                borderBottom: isActive ? `2px solid ${scheme.accent}` : "2px solid transparent",
                background: isActive ? theme.fill.quaternary : "transparent",
                color: isActive ? theme.text.primary : theme.text.secondary,
                fontWeight: isActive ? 600 : 400,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </Row>

      <div
        style={{
          flex: 1,
          overflow: "hidden",
          padding: 10,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "auto" }}>
          {children}
        </div>
      </div>

      <div
        style={{
          padding: "8px 12px",
          borderTop: `1px solid ${theme.stroke.tertiary}`,
          background: schemeHeader,
        }}
      >
        <Row gap={8} align="center">
          <Pill size="sm" tone="success" active>
            Подключено
          </Pill>
          <Text tone="secondary" size={11}>
            БЗ обновлена · 12:34
          </Text>
        </Row>
      </div>
      <div
        role="separator"
        aria-label="Resize panel"
        onPointerDown={startResize}
        style={{
          position: "absolute",
          right: 0,
          bottom: 0,
          width: 22,
          height: 22,
          zIndex: 20,
          touchAction: "none",
          cursor: "nwse-resize",
          background: theme.stroke.secondary,
          borderTop: `1px solid ${theme.stroke.tertiary}`,
          borderLeft: `1px solid ${theme.stroke.tertiary}`,
        }}
      />
    </div>
  );
}

function AssistantTab({ theme }: { theme: CanvasHostTheme }): JSX.Element {
  const [input, setInput] = useCanvasState("assistantInput", "");
  const [assistantSlide, setAssistantSlide] = useCanvasState<AssistantSlide>("assistantSlide", "chat");

  return (
    <Stack gap={10} style={{ flex: 1, minHeight: 0, height: "100%" }}>
      <Row gap={6} wrap>
        <Select
          value={assistantSlide}
          onChange={(v) => setAssistantSlide(v as AssistantSlide)}
          options={[
            { value: "chat", label: "Чат с источниками" },
            { value: "clarify", label: "Уточнение" },
            { value: "tools", label: "Инструменты" },
            { value: "summary", label: "Саммаризация" },
            { value: "translate", label: "Перевод RU↔EN" },
          ]}
          style={{ flex: 1, minWidth: 200 }}
        />
      </Row>
      <Row gap={6} wrap>
        <Select
          value="hr"
          onChange={() => undefined}
          options={[
            { value: "hr", label: "Корпоративные регламенты" },
            { value: "legal", label: "Юридические документы" },
          ]}
          style={{ flex: 1, minWidth: 160 }}
        />
        <Button variant="secondary">+ Новый</Button>
      </Row>
      <Button variant="ghost" style={{ alignSelf: "flex-start" }}>
        История диалогов
      </Button>

      <div
        style={{
          flex: 1,
          minHeight: 120,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          padding: 10,
          background: theme.fill.quaternary,
          borderRadius: 8,
          border: `1px solid ${theme.stroke.tertiary}`,
        }}
      >
        <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
          <Stack gap={10}>
            <div>
              <Text tone="secondary" size={11}>
                Вы
              </Text>
              <Text>Как оформить отпуск?</Text>
            </div>
            <div>
              <Text tone="secondary" size={11}>
                Ассистент
              </Text>
              <Text>
                Для оформления отпуска подайте заявление в HR-портале не позднее чем за 5 рабочих дней. При
                необходимости приложите согласование руководителя.
              </Text>
              <Stack gap={4} style={{ marginTop: 8 }}>
                <Text weight="semibold" size={11}>
                  Источники
                </Text>
                <Row gap={6} wrap align="center">
                  <Pill size="sm" tone="success">
                    Регламент HR-12 · 94%
                  </Pill>
                  <Button variant="ghost">Открыть</Button>
                </Row>
                <Row gap={6} wrap align="center">
                  <Pill size="sm" tone="info">
                    Положение об отпусках · 87%
                  </Pill>
                  <Button variant="ghost">Открыть</Button>
                </Row>
              </Stack>
              <FeedbackChipRow t={theme} options={ASSISTANT_FEEDBACK_OPTIONS} stateKey="assistantFeedback_demo" />
            </div>
          </Stack>
        </div>
      </div>

      {assistantSlide === "clarify" && (
        <Callout tone="warning">
          <Stack gap={6}>
            <Text weight="semibold" size={12}>
              Низкая релевантность (41%) — уточните запрос
            </Text>
            <Row gap={6} wrap>
              <Pill size="sm" active>
                Уточнить подразделение
              </Pill>
              <Pill size="sm" active>
                Уточнить тип документа
              </Pill>
            </Row>
          </Stack>
        </Callout>
      )}

      {assistantSlide === "tools" && (
        <Callout tone="info">
          <Row gap={6} wrap align="center">
            <Pill size="sm" active>
              Код
            </Pill>
            <Pill size="sm" active>
              SQL read-only
            </Pill>
            <Pill size="sm" active>
              RPA c confirm
            </Pill>
          </Row>
        </Callout>
      )}

      {assistantSlide === "summary" && (
        <Callout tone="info">
          <Text size={11}>Саммаризация аудио/видео: таймкоды, ключевые решения, действия.</Text>
        </Callout>
      )}

      {assistantSlide === "translate" && (
        <Callout tone="success">
          <Text size={11}>Переводится текст запроса/ответа RU↔EN, без конвертации формата вложений.</Text>
        </Callout>
      )}

      <Row gap={6}>
        <Button variant="ghost">Прикрепить</Button>
        <Button variant="ghost">Инструменты</Button>
      </Row>
      <Row gap={6} align="end">
        <TextArea
          value={input}
          onChange={setInput}
          placeholder="Задайте вопрос…"
          rows={2}
          style={{ flex: 1 }}
        />
        <Button variant="primary">Отправить</Button>
      </Row>
    </Stack>
  );
}

function PassportSpreadSchematic({ theme }: { theme: CanvasHostTheme }): JSX.Element {
  const pageFill = theme.fill.secondary;
  const pageStroke = theme.stroke.secondary;
  const accent = theme.accent.primary;
  const ok = theme.palette.diffStripAdded;
  const warn = theme.accent.primary;
  const textMuted = theme.text.tertiary;
  const photoFill = theme.fill.tertiary;

  return (
    <svg
      viewBox="0 0 300 148"
      width="100%"
      height="148"
      style={{ display: "block", marginTop: 6 }}
      aria-label="Схема разворота паспорта"
    >
      <rect x="4" y="4" width="142" height="140" rx="3" fill={pageFill} stroke={pageStroke} strokeWidth="1" />
      <rect x="154" y="4" width="142" height="140" rx="3" fill={pageFill} stroke={pageStroke} strokeWidth="1" />
      <rect x="4" y="4" width="142" height="10" fill={theme.palette.diffStripRemoved} opacity="0.55" />
      <text x="12" y="26" fill={textMuted} fontSize="7" fontFamily="sans-serif">
        РЭСПУБЛІКА БЕЛАРУСЬ
      </text>
      <text x="12" y="40" fill={theme.text.secondary} fontSize="11" fontWeight="600" fontFamily="sans-serif">
        ПАСПОРТ
      </text>
      <circle cx="52" cy="88" r="22" fill={photoFill} stroke={pageStroke} strokeWidth="1" />
      <text x="40" y="92" fill={textMuted} fontSize="6" fontFamily="sans-serif">
        герб
      </text>
      <rect x="162" y="14" width="44" height="54" rx="2" fill={photoFill} stroke={pageStroke} strokeWidth="1" />
      <text x="168" y="44" fill={textMuted} fontSize="6" fontFamily="sans-serif">
        фото
      </text>
      <rect x="212" y="22" width="74" height="12" rx="1" fill="none" stroke={ok} strokeWidth="1.5" />
      <text x="214" y="20" fill={ok} fontSize="5" fontFamily="sans-serif">
        ФИО
      </text>
      <line x1="212" y1="34" x2="284" y2="34" stroke={textMuted} strokeWidth="0.5" />
      <text x="212" y="33" fill={theme.text.primary} fontSize="6" fontFamily="sans-serif">
        ІВАНОЎ ІВАН
      </text>
      <rect x="212" y="42" width="52" height="10" rx="1" fill="none" stroke={ok} strokeWidth="1.5" />
      <text x="214" y="40" fill={ok} fontSize="5" fontFamily="sans-serif">
        №
      </text>
      <text x="212" y="51" fill={theme.text.primary} fontSize="6" fontFamily="sans-serif">
        MP1234567
      </text>
      <rect x="212" y="58" width="60" height="10" rx="1" fill="none" stroke={warn} strokeWidth="1.5" />
      <text x="214" y="56" fill={warn} fontSize="5" fontFamily="sans-serif">
        дата
      </text>
      <text x="212" y="67" fill={theme.text.primary} fontSize="6" fontFamily="sans-serif">
        12.05.2019
      </text>
      <rect x="162" y="118" width="126" height="18" rx="1" fill={theme.fill.quaternary} stroke={pageStroke} strokeWidth="0.5" />
      <text x="166" y="128" fill={textMuted} fontSize="5" fontFamily="monospace">
        P&lt;BLRIVANOW&lt;&lt;IVAN&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;
      </text>
      <text x="166" y="136" fill={textMuted} fontSize="5" fontFamily="monospace">
        MP1234567&lt;BLR9001011M2501012&lt;&lt;&lt;&lt;&lt;&lt;2
      </text>
      <line x1="154" y1="4" x2="154" y2="144" stroke={accent} strokeWidth="1" strokeDasharray="2 2" opacity="0.4" />
    </svg>
  );
}

function DocumentsTab({
  theme,
  subTab,
  setSubTab,
}: {
  theme: CanvasHostTheme;
  subTab: OcrSubTab;
  setSubTab: (t: OcrSubTab) => void;
}): JSX.Element {
  return (
    <Stack gap={10} style={{ flex: 1, minHeight: 0, height: "100%" }}>
      <Row gap={6} wrap>
        {(
          [
            { id: "queue" as const, label: "Очередь" },
            { id: "upload" as const, label: "Загрузить" },
            { id: "review" as const, label: "Проверка" },
          ] as const
        ).map((t) => (
          <Pill key={t.id} active={subTab === t.id} onClick={() => setSubTab(t.id)}>
            {t.label}
          </Pill>
        ))}
      </Row>

      {subTab === "queue" && (
        <Stack gap={8} style={{ minHeight: 360 }}>
          <Row gap={6} wrap>
            <Stat label="В очереди" value="24" tone="warning" />
            <Stat label="SLA < 5 мин" value="18" tone="success" />
            <Stat label="HITL-проверка" value="6" tone="neutral" />
          </Row>
          <Row gap={6} wrap>
            <Select
              value="all"
              onChange={() => undefined}
              options={[
                { value: "all", label: "Все типы" },
                { value: "passport", label: "Паспорт" },
                { value: "application", label: "Заявление" },
                { value: "contract", label: "Договор" },
                { value: "payment", label: "Платёжный документ" },
              ]}
              style={{ flex: 1, minWidth: 100 }}
            />
            <Select
              value="status"
              onChange={() => undefined}
              options={[
                { value: "status", label: "Статус" },
                { value: "review", label: "На проверке (HITL)" },
                { value: "processing", label: "В обработке" },
                { value: "done", label: "Готово к экспорту" },
              ]}
              style={{ flex: 1, minWidth: 100 }}
            />
          </Row>
          <TextInput placeholder="Поиск по файлу…" />
          <Table
            framed
            headers={["Файл", "Тип", "Статус", "Точность", ""]}
            rows={[
              [
                "scan_001.pdf",
                "Паспорт",
                <Pill size="sm" tone="warning">HITL</Pill>,
                <Pill size="sm" tone="success">96%</Pill>,
                <Button variant="ghost" onClick={() => setSubTab("review")}>Открыть</Button>,
              ],
              [
                "invoice.pdf",
                "Счёт",
                <Pill size="sm" tone="info">В обработке</Pill>,
                <Pill size="sm" tone="warning">78%</Pill>,
                <Button variant="ghost" onClick={() => setSubTab("review")}>Открыть</Button>,
              ],
              [
                "batch.zip",
                "—",
                <Stack gap={4}>
                  <Pill size="sm">В обработке</Pill>
                  <div
                    style={{
                      height: 4,
                      borderRadius: 2,
                      background: theme.fill.tertiary,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        width: "62%",
                        height: "100%",
                        background: theme.accent.primary,
                      }}
                    />
                  </div>
                </Stack>,
                <Text tone="secondary" size={11}>—</Text>,
                <Text tone="secondary" size={11}>—</Text>,
              ],
            ]}
          />
          <Spacer />
          <Button variant="secondary" onClick={() => setSubTab("upload")}>
            Загрузить документы
          </Button>
        </Stack>
      )}

      {subTab === "upload" && (
        <Stack gap={10}>
          <div
            style={{
              padding: 24,
              textAlign: "center",
              border: `2px dashed ${theme.stroke.secondary}`,
              borderRadius: 8,
              background: theme.fill.quaternary,
            }}
          >
            <Text weight="semibold">Перетащите PDF, JPG/JPEG, PNG, TIFF</Text>
            <Text tone="secondary" size={11}>
              До 10 МБ, до 50 стр.
            </Text>
          </div>
          <Select
            value="auto"
            onChange={() => undefined}
            options={[
              { value: "auto", label: "Тип: определить автоматически" },
              { value: "passport", label: "Паспорт" },
              { value: "application", label: "Заявление" },
              { value: "contract", label: "Договор" },
            ]}
          />
          <Checkbox label="Пакетная обработка" checked={false} onChange={() => undefined} />
          <Checkbox label="Сразу отправить в HITL при точности < 90%" checked onChange={() => undefined} />
          <Button variant="primary">Начать распознавание</Button>
        </Stack>
      )}

      {subTab === "review" && (
        <Stack gap={8}>
          <Grid columns="1fr 1fr" gap={8}>
            <div
              style={{
                minHeight: 200,
                padding: 8,
                background: theme.fill.quaternary,
                border: `1px solid ${theme.stroke.tertiary}`,
                borderRadius: 8,
              }}
            >
              <Row gap={6} align="center">
                <Text tone="secondary" size={11}>
                  Паспорт · разворот 2–3
                </Text>
                <Pill size="sm" tone="info">
                  схема
                </Pill>
              </Row>
              <PassportSpreadSchematic theme={theme} />
              <Text tone="secondary" size={10}>
                Зелёная рамка — поле распознано; жёлтая — на проверку
              </Text>
            </div>
            <Stack gap={6}>
              <Text weight="semibold" size={12}>
                Поля документа
              </Text>
              <Row gap={6} align="center">
                <Text size={11} style={{ width: 48 }}>
                  ФИО
                </Text>
                <TextInput value="Иванов И.И." onChange={() => undefined} style={{ flex: 1 }} />
                <Pill size="sm" tone="success">
                  98%
                </Pill>
              </Row>
              <Row gap={6} align="center">
                <Text size={11} style={{ width: 72 }}>
                  Серия/номер
                </Text>
                <TextInput value="MP1234567" onChange={() => undefined} style={{ flex: 1 }} />
                <Pill size="sm" tone="success">
                  96%
                </Pill>
              </Row>
              <Row gap={6} align="center">
                <Text size={11} style={{ width: 72 }}>
                  Дата выдачи
                </Text>
                <TextInput value="12.05.2019" onChange={() => undefined} style={{ flex: 1 }} />
                <Pill size="sm" tone="warning">
                  проверка
                </Pill>
              </Row>
              <Callout tone="info">
                <Text size={11}>LLM: предложить правку даты — Принять / Отклонить (шаг HITL)</Text>
              </Callout>
            </Stack>
          </Grid>
          <Select
            value="edo_json"
            onChange={() => undefined}
            options={[
              { value: "edo_json", label: "Экспорт: ЭДО JSON" },
              { value: "abs_csv", label: "Экспорт: ABS CSV" },
              { value: "archive_pdf", label: "Экспорт: Архив PDF" },
            ]}
          />
          <Row gap={6} wrap>
            <Button variant="ghost">Повторить OCR</Button>
            <Button variant="ghost">Отклонить</Button>
            <Spacer />
            <Button variant="secondary">Утвердить всё</Button>
            <Button variant="primary">Утвердить и экспорт</Button>
          </Row>
        </Stack>
      )}
    </Stack>
  );
}

function groupSuflerPairs(
  utterances: TranscriptLine[],
  hints: HintCard[],
): { utterance: TranscriptLine; hints: HintCard[] }[] {
  return utterances
    .filter((u) => u.speaker === "client")
    .map((utterance) => ({
      utterance,
      hints: hints.filter((h) => h.utteranceId === utterance.id).slice(0, 3),
    }));
}

function SuflerFeedbackRow({ t, cardId }: { t: CanvasHostTheme; cardId: string }): JSX.Element {
  return <FeedbackChipRow t={t} options={SUFLER_FEEDBACK_OPTIONS} stateKey={`suflerFeedback_${cardId}`} />;
}

function SuflerPairBlock({
  theme,
  clientText,
  hints,
  isLatest,
  readingHintId,
  onToggleRead,
}: {
  theme: CanvasHostTheme;
  clientText: string;
  hints: HintCard[];
  isLatest: boolean;
  readingHintId: string | null;
  onToggleRead: (hintId: string) => void;
}): JSX.Element {
  return (
    <div
      style={{
        padding: "8px 10px",
        borderRadius: 8,
        border: `1px solid ${isLatest ? theme.stroke.secondary : theme.stroke.tertiary}`,
        background: isLatest ? theme.fill.tertiary : theme.fill.quaternary,
        borderLeft: `3px solid ${isLatest ? theme.accent.primary : theme.stroke.tertiary}`,
      }}
    >
      <Text tone="secondary" size={10}>
        Клиент
      </Text>
      <Text size={12} weight="semibold" style={{ marginTop: 2 }}>
        «{clientText}»
      </Text>
      {hints.length === 0 ? (
        <Text tone="secondary" size={11} style={{ marginTop: 8 }}>
          Подсказка формируется…
        </Text>
      ) : (
        hints.map((hint) => {
          const isReading = readingHintId === hint.id;
          const compactText =
            hint.text.length > 110 ? `${hint.text.slice(0, 110).trimEnd()}…` : hint.text;
          return (
            <div
              id={`sufler-hint-${hint.id}`}
              key={hint.id}
              style={{
                marginTop: 8,
                padding: isReading ? "10px" : "8px 0 0",
                borderTop: isReading ? "none" : `1px solid ${theme.stroke.tertiary}`,
                border: isReading ? `1px solid ${theme.accent.primary}` : undefined,
                borderRadius: isReading ? 8 : undefined,
                background: isReading ? theme.bg.editor : undefined,
                position: isReading ? "sticky" : "static",
                top: isReading ? 0 : undefined,
                zIndex: isReading ? 2 : undefined,
                transition: "all 160ms ease",
              }}
            >
              <Row gap={6} align="center">
                <Text tone="secondary" size={10}>
                  Подсказка
                </Text>
                <Pill size="sm" tone={hint.tone}>
                  {hint.relevance}%
                </Pill>
                {isReading && (
                  <Pill size="sm" tone="accent" active>
                    Зачитывается
                  </Pill>
                )}
              </Row>
              <Text size={12} style={{ marginTop: 4, lineHeight: 1.4 }}>
                {isReading ? hint.text : compactText}
              </Text>
              <Row gap={6} wrap style={{ marginTop: 4 }}>
                <Button
                  variant={isReading ? "secondary" : "ghost"}
                  style={{ fontSize: 11, padding: "2px 8px" }}
                  onClick={() => onToggleRead(hint.id)}
                >
                  {isReading ? "Остановить зачитывание" : "Начать зачитывание"}
                </Button>
                {hint.article && (
                  <Button variant="ghost" style={{ fontSize: 11, padding: 0, minHeight: 0 }}>
                    СУЗ ↗ {hint.article}
                  </Button>
                )}
              </Row>
              <SuflerFeedbackRow t={theme} cardId={hint.id} />
            </div>
          );
        })
      )}
    </div>
  );
}

function SuflerTab({ theme, callActive }: { theme: CanvasHostTheme; callActive: boolean }): JSX.Element {
  const [enabled, setEnabled] = useCanvasState("suflerEnabled", true);
  const [mode, setMode] = useCanvasState<"consult" | "service">("suflerMode", "consult");
  const [utterances, setUtterances] = useCanvasState<TranscriptLine[]>("suflerUtterances", INITIAL_UTTERANCES);
  const [hints, setHints] = useCanvasState<HintCard[]>("suflerHints", INITIAL_HINTS);
  const [replyIndex, setReplyIndex] = useCanvasState("suflerReplyIndex", 0);
  const [readingHintId, setReadingHintId] = useCanvasState<string | null>("suflerReadingHintId", null);
  const pairsViewportRef = useRef<HTMLDivElement | null>(null);

  const pairs = groupSuflerPairs(utterances, hints);
  const pairsViewportMaxHeight = Math.min(560, 220 + pairs.length * 110);

  const simulateNewUtterance = () => {
    const next = NEXT_CLIENT_REPLIES[replyIndex % NEXT_CLIENT_REPLIES.length];
    const utteranceId = `u${Date.now()}`;
    setUtterances([...utterances, { id: utteranceId, speaker: "client", text: next.text }]);
    setHints([
      ...hints,
      ...next.hints.slice(0, 1).map((h, i) => ({
        ...h,
        id: `h${Date.now()}-${i}`,
        utteranceId,
        title: "Подсказка",
      })),
    ]);
    setReplyIndex(replyIndex + 1);
  };

  const toggleReadHint = (hintId: string) => {
    if (readingHintId === hintId) {
      setReadingHintId(null);
      return;
    }
    setReadingHintId(hintId);
  };

  useEffect(() => {
    if (!readingHintId || mode !== "consult") return;
    const activeHintEl = document.getElementById(`sufler-hint-${readingHintId}`);
    if (!activeHintEl) return;
    activeHintEl.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
  }, [readingHintId, mode, utterances.length, hints.length]);

  useEffect(() => {
    if (mode !== "consult") return;
    const viewport = pairsViewportRef.current;
    if (!viewport) return;
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
  }, [pairs.length, mode]);

  if (!enabled) {
    return (
      <Stack gap={12} style={{ paddingTop: 24, textAlign: "center" }}>
        <Text tone="secondary">Суфлёр свёрнут. Разверните для подсказок.</Text>
        <Button variant="primary" onClick={() => setEnabled(true)}>
          Развернуть суфлёр
        </Button>
      </Stack>
    );
  }

  return (
    <Stack gap={8}>
      <Row gap={6} align="center" wrap>
        {callActive && (
          <Pill size="sm" tone="warning" active>
            Звонок
          </Pill>
        )}
        <Pill
          active={mode === "consult"}
          onClick={() => {
            setMode("consult");
            setReadingHintId(null);
          }}
        >
          Консультация
        </Pill>
        <Pill
          active={mode === "service"}
          onClick={() => {
            setMode("service");
            setReadingHintId(null);
          }}
        >
          Услуга
        </Pill>
        <Spacer />
        <Button variant="ghost" onClick={() => setEnabled(false)}>
          Свернуть
        </Button>
      </Row>

      {mode === "consult" && (
        <>
          <div
            ref={pairsViewportRef}
            style={{
              maxHeight: pairsViewportMaxHeight,
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 8,
              transition: "max-height 220ms ease",
            }}
          >
            {pairs.map((pair, idx) => (
              <SuflerPairBlock
                key={pair.utterance.id}
                theme={theme}
                clientText={pair.utterance.text}
                hints={pair.hints}
                isLatest={idx === pairs.length - 1}
                readingHintId={readingHintId}
                onToggleRead={toggleReadHint}
              />
            ))}
          </div>

          <Button variant="secondary" onClick={simulateNewUtterance}>
            Симулировать новую реплику клиента
          </Button>
        </>
      )}
    </Stack>
  );
}

export default function AiHubPanelMockup(): JSX.Element {
  const theme = useHostTheme();
  const [colorScheme, setColorScheme] = useCanvasState<ColorScheme>("aiHubPanelColorScheme", "default");
  const [role, setRole] = useCanvasState<RoleId>("mockupRole", "assistant_user");
  const [panelOpen, setPanelOpen] = useCanvasState("panelOpen", true);
  const [panelWidth, setPanelWidth] = useCanvasState("panelWidthPx", 560);
  const [panelHeight, setPanelHeight] = useCanvasState("panelHeightPx", 560);
  const [pinned, setPinned] = useCanvasState("panelPinned", false);
  const [activeTab, setActiveTab] = useCanvasState<MainTab>("mainTab", "assistant");
  const [ocrSubTab, setOcrSubTab] = useCanvasState<OcrSubTab>("ocrSubTab", "queue");
  const [adminCenterOpen, setAdminCenterOpen] = useCanvasState("hubAdminCenterOpen", false);

  const roleConfig = ROLES[role];
  const scheme = getSchemePalette(theme, colorScheme);
  const schemeBorder = scheme.accentWeak;
  const schemeHeader = scheme.headerBg;
  const showHubPanel = hubHasAnyTab(roleConfig.tabs);

  const setPanelSize = (nextWidth: number, nextHeight: number) => {
    const next = clampPanelSize(nextWidth, nextHeight);
    setPanelWidth(next.w);
    setPanelHeight(next.h);
  };

  const applyDemo = (nextRole: RoleId, tab: MainTab) => {
    setRole(nextRole);
    setPanelOpen(true);
    if (ROLES[nextRole].tabs[tab]) {
      setActiveTab(tab);
    } else {
      setActiveTab(firstAllowedTab(ROLES[nextRole].tabs));
    }
    if (tab === "documents") setOcrSubTab("queue");
  };

  const setRoleAndTab = (nextRole: RoleId) => {
    setRole(nextRole);
    const tabs = ROLES[nextRole].tabs;
    if (!tabs[activeTab]) {
      setActiveTab(firstAllowedTab(tabs));
    }
  };

  useEffect(() => {
    if (!hubHasAnyTab(roleConfig.tabs)) return;
    if (!roleConfig.tabs[activeTab]) {
      setActiveTab(firstAllowedTab(roleConfig.tabs));
    }
  }, [activeTab, roleConfig, setActiveTab]);

  const renderTabContent = (): JSX.Element => {
    if (activeTab === "assistant") return <AssistantTab theme={theme} />;
    return <DocumentsTab theme={theme} subTab={ocrSubTab} setSubTab={setOcrSubTab} />;
  };

  return (
    <Stack
      gap={16}
      style={{
        padding: 12,
        borderRadius: 10,
        border: `1px solid ${scheme.accentWeak}`,
        background: scheme.panelBg,
      }}
    >
      <H1>AI Hub Panel — оболочка back-office</H1>
      <Text tone="secondary">
        Только «Ассистент» и «Документы». Суфлёр — **отдельный интерфейс**: телефония и онлайн-чат открываются в
        собственных окнах оператора.
      </Text>

      <Card style={{ borderColor: schemeBorder }}>
        <CardHeader>Роль ПО</CardHeader>
        <CardBody>
          <Stack gap={10}>
            <Row gap={12} align="center" wrap>
              <Text tone="secondary">Схема:</Text>
              <Row gap={6} wrap>
                <Pill active={colorScheme === "default"} onClick={() => setColorScheme("default")}>
                  Текущая
                </Pill>
                <Pill
                  active={colorScheme === "belarusbank_classic"}
                  onClick={() => setColorScheme("belarusbank_classic")}
                >
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
              </Row>
            </Row>
            <Row gap={12} align="center" wrap>
              <Text tone="secondary">Роль:</Text>
              <Select value={role} onChange={(v) => setRoleAndTab(v as RoleId)} options={ROLE_OPTIONS} />
              <Toggle checked={panelOpen} onChange={setPanelOpen} label="Панель открыта" />
              <Toggle
                checked={pinned}
                onChange={(v) => {
                  setPinned(v);
                  if (v) setPanelSize(PANEL_MAX_W, PANEL_MAX_H);
                }}
                label="Развёрнуто"
              />
              <Row gap={6} align="center">
                <Text tone="secondary" size={11}>
                  W:
                </Text>
                <TextInput
                  value={String(panelWidth)}
                  onChange={(v) => {
                    const n = Number(v);
                    if (!Number.isNaN(n)) setPanelSize(n, panelHeight);
                  }}
                  style={{ width: 64 }}
                />
                <Text tone="secondary" size={11}>
                  H:
                </Text>
                <TextInput
                  value={String(panelHeight)}
                  onChange={(v) => {
                    const n = Number(v);
                    if (!Number.isNaN(n)) setPanelSize(panelWidth, n);
                  }}
                  style={{ width: 64 }}
                />
                <Button variant="ghost" onClick={() => setPanelSize(panelWidth + 40, panelHeight + 20)}>
                  + размер
                </Button>
                <Button variant="ghost" onClick={() => setPanelSize(panelWidth - 40, panelHeight - 20)}>
                  - размер
                </Button>
              </Row>
            </Row>
            <Text tone="secondary" size={11}>
              {roleConfig.source}
            </Text>
            <Stack gap={6}>
              <Text tone="secondary" size={11}>
                Быстрый переход (демо)
              </Text>
              <Row gap={6} wrap>
                <Button variant="secondary" onClick={() => applyDemo("assistant_user", "assistant")}>
                  Back-office · Ассистент
                </Button>
                <Button variant="ghost" onClick={() => applyDemo("doc_verifier", "documents")}>
                  OCR · Документы
                </Button>
                <Button variant="ghost" onClick={() => applyDemo("cc_operator", "assistant")}>
                  Оператор телефонии (без Hub)
                </Button>
                <Button variant="ghost" onClick={() => applyDemo("system_admin", "assistant")}>
                  Админ системы
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setPanelOpen(true);
                    setAdminCenterOpen(true);
                  }}
                >
                  Центр настроек (≡ меню)
                </Button>
              </Row>
            </Stack>
          </Stack>
        </CardBody>
      </Card>

      <Card collapsible defaultOpen style={{ borderColor: schemeBorder }}>
        <CardHeader>Роли ПО — видимость вкладок</CardHeader>
        <CardBody style={{ padding: 0 }}>
          <Table
            headers={["Роль", "Ассистент", "Документы", "Суфлёр (отдельно)"]}
            rows={ROLE_OPTIONS.map((opt) => {
              const r = ROLES[opt.value];
              const cell = (on: boolean) => (on ? "да" : "—");
              const suflerCell = r.suflerInterface ?? "—";
              return [opt.label, cell(r.tabs.assistant), cell(r.tabs.documents), suflerCell];
            })}
            rowTone={ROLE_OPTIONS.map((opt) => (opt.value === role ? "info" : undefined))}
            columnAlign={["left", "center", "center", "center"]}
            framed
            stickyHeader
          />
          <div style={{ padding: "8px 12px" }}>
            <Text tone="secondary" size={11}>
              Маппинг на группы AD — зона ответственности Заказчика. Суфлёр не входит в tab bar Hub.
            </Text>
          </div>
        </CardBody>
      </Card>

      <H2 style={{ color: scheme.accentControl }}>
        Preview: {adminCenterOpen ? "Центр настроек" : "панель AI"}
      </H2>

      <div
        style={{
          position: "relative",
          minHeight: Math.max(580, panelHeight + 32),
          padding: 16,
          display: "flex",
          justifyContent: adminCenterOpen ? "stretch" : "flex-end",
          alignItems: "flex-start",
          overflow: "visible",
          background: scheme.panelBg,
          borderRadius: 8,
          border: `1px solid ${schemeBorder}`,
        }}
      >
        {adminCenterOpen ? (
          <AdminCenterPreview
            theme={theme}
            scheme={scheme}
            onBack={() => setAdminCenterOpen(false)}
            onMinimize={() => setAdminCenterOpen(false)}
            onMaximize={() => setPinned(!pinned)}
            onClose={() => setAdminCenterOpen(false)}
            maximized={pinned}
          />
        ) : (
          <>
        {!showHubPanel && panelOpen && (
          <Card style={{ width: "100%", maxWidth: 520, borderColor: schemeBorder }}>
            <CardHeader>Hub недоступен в рабочей сессии</CardHeader>
            <CardBody>
              <Stack gap={10}>
                <Text size={13}>
                  Роль «{roleConfig.label}» не использует FAB-панель Hub с вкладками «Ассистент» / «Документы» — операционный
                  риск смешения контекстов.
                </Text>
                {roleConfig.suflerInterface && (
                  <Callout tone="info">
                    <Text size={12} weight="semibold">
                      Суфлёр / рабочее место:
                    </Text>
                    <Text size={12}>{roleConfig.suflerInterface}</Text>
                  </Callout>
                )}
              </Stack>
            </CardBody>
          </Card>
        )}
        {showHubPanel && panelOpen && (
          <PanelShell
            theme={theme}
            scheme={scheme}
            roleConfig={roleConfig}
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            panelWidth={panelWidth}
            panelHeight={panelHeight}
            pinned={pinned}
            setPinned={setPinned}
            onClose={() => setPanelOpen(false)}
            onMinimize={() => setPanelOpen(false)}
            setPanelSize={setPanelSize}
          >
            {renderTabContent()}
          </PanelShell>
        )}

        {!panelOpen && !showHubPanel && (
          <Callout tone="neutral">
            <Text size={12}>FAB Hub скрыт для роли без вкладок. Суфлёр — в отдельном canvas.</Text>
          </Callout>
        )}

        {!panelOpen && showHubPanel && (
          <button
            type="button"
            onClick={() => setPanelOpen(true)}
            style={{
              position: "absolute",
              right: 24,
              bottom: 24,
              width: 56,
              height: 56,
              borderRadius: 28,
              border: "none",
              background: scheme.accentControl,
              color: theme.text.onAccent,
              fontWeight: 700,
              fontSize: 14,
              cursor: "pointer",
            }}
            title="Открыть Беларусбанк AI"
          >
            AI
            <span
              style={{
                position: "absolute",
                top: 4,
                right: 4,
                minWidth: 18,
                height: 18,
                borderRadius: 9,
                background: scheme.badge,
                color: theme.text.onAccent,
                fontSize: 10,
                lineHeight: "18px",
                textAlign: "center",
              }}
            >
              2
            </span>
          </button>
        )}
          </>
        )}
      </div>

      <Row gap={16} wrap>
        <Stat value={roleConfig.tabs.assistant ? "да" : "—"} label="Ассистент" tone={roleConfig.tabs.assistant ? "success" : "neutral"} />
        <Stat value={roleConfig.tabs.documents ? "да" : "—"} label="Документы" tone={roleConfig.tabs.documents ? "success" : "neutral"} />
        <Stat value={roleConfig.suflerInterface ? "отдельно" : "—"} label="Суфлёр" tone={roleConfig.suflerInterface ? "warning" : "neutral"} />
      </Row>

      <Callout tone="info">
        <Text size={12}>
          В Hub доступны только «Ассистент» и «Документы». Подсказки суфлёра — в отдельных окнах телефонии и
          онлайн-чата; tab lock в Hub для них не применяется.
        </Text>
      </Callout>
    </Stack>
  );
}
