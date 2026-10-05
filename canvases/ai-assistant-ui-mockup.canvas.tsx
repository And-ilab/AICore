import {
  Button,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  Divider,
  H1,
  H2,
  Pill,
  Row,
  Select,
  Stack,
  Text,
  TextArea,
  TextInput,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";
import type { CanvasHostTheme } from "cursor/canvas";
import type { CSSProperties, JSX } from "react";

type AssistantState = "chat" | "empty" | "streaming" | "error" | "clarify" | "generate" | "summary" | "tools" | "translate";
type ColorScheme =
  | "default"
  | "belarusbank_classic"
  | "belarusbank_soft"
  | "belarusbank_emerald"
  | "belarusbank_night";

const KNOWLEDGE_BASES = [
  { id: "hr", label: "Корпоративные регламенты HR" },
  { id: "legal", label: "Юридические документы" },
  { id: "it", label: "ИТ-инструкции и доступы" },
  { id: "retail", label: "Продукты для физлиц" },
  { id: "corporate", label: "Продукты для юрлиц" },
  { id: "security", label: "Политики ИБ и compliance" },
  { id: "suz", label: "СУЗ · справочник знаний" },
] as const;

type KbId = (typeof KNOWLEDGE_BASES)[number]["id"];

const DEFAULT_KB_SELECTION: Record<KbId, boolean> = {
  hr: true,
  legal: true,
  it: true,
  retail: true,
  corporate: true,
  security: true,
  suz: true,
};

const WINDOW_CONTROLS_WIDTH = 108;

type FeedbackChipChoice = "used" | "not_used" | "partial";

type FeedbackChipPalette = {
  idleBg: string;
  idleBorder: string;
  activeBg: string;
  activeBorder: string;
  activeColor: string;
};

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

const ASSISTANT_FEEDBACK_OPTIONS: { id: FeedbackChipChoice; label: string }[] = [
  { id: "used", label: "Полезно" },
  { id: "partial", label: "Неполный ответ" },
  { id: "not_used", label: "Неверно" },
];

function AssistantFeedbackRow({ t, stateKey }: { t: CanvasHostTheme; stateKey: string }): JSX.Element {
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
      {ASSISTANT_FEEDBACK_OPTIONS.map((option) => (
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

const STATE_OPTIONS = [
  { value: "chat", label: "Чат с источниками" },
  { value: "empty", label: "Пустой сценарий" },
  { value: "streaming", label: "Стриминг" },
  { value: "error", label: "Ошибка" },
  { value: "clarify", label: "Уточнение при низком %" },
  { value: "generate", label: "Генерация документа" },
  { value: "summary", label: "Саммаризация аудио/видео" },
  { value: "tools", label: "Инструменты (Код/SQL, RPA)" },
  { value: "translate", label: "Перевод RU↔EN" },
];

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
          <Text size="small" tone="secondary">
            {entry.key}
          </Text>
        </Row>
      ))}
    </Row>
  );
}

function PanelChrome({
  theme,
  scheme,
  panelWidth,
  panelHeight,
  setPanelSize,
  children,
  dock,
  onClose,
  onMinimize,
  onMaximize,
  maximized,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  panelWidth: number;
  panelHeight: number;
  setPanelSize: (nextWidth: number, nextHeight: number) => void;
  children: JSX.Element;
  dock?: JSX.Element;
  onClose?: () => void;
  onMinimize?: () => void;
  onMaximize?: () => void;
  maximized?: boolean;
}): JSX.Element {
  const boundedWidth = Math.max(360, Math.min(860, panelWidth));
  const boundedHeight = Math.max(420, Math.min(860, panelHeight));
  const schemeBorder = scheme.accentWeak;
  const schemeHeader = scheme.headerBg;

  const startResize = (event: { clientX: number; clientY: number; preventDefault: () => void }) => {
    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const initialWidth = boundedWidth;
    const initialHeight = boundedHeight;

    const handleMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      setPanelSize(initialWidth + deltaX, initialHeight + deltaY);
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

  const shell: CSSProperties = {
    width: boundedWidth,
    height: boundedHeight,
    maxWidth: "100%",
    margin: "0 auto",
    borderRadius: 12,
    border: `1px solid ${schemeBorder}`,
    background: scheme.panelBg,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    minHeight: 0,
    position: "relative",
    transition: "width 160ms ease, height 160ms ease",
  };

  return (
    <div style={shell}>
      <div
        style={{
          position: "relative",
          padding: "10px 12px",
          paddingRight: WINDOW_CONTROLS_WIDTH,
          borderBottom: `1px solid ${theme.stroke.tertiary}`,
          background: schemeHeader,
        }}
      >
        <Stack gap={2}>
          <Text weight="semibold">Беларусбанк AI</Text>
          <Text tone="secondary" size="small">
            Сидоров П.К. · Пользователь ИИ-ассистента
          </Text>
        </Stack>
        <WindowTitleBarControls
          theme={theme}
          onMinimize={onMinimize}
          onMaximize={onMaximize}
          onClose={onClose}
          maximized={maximized}
        />
      </div>

      <div
        style={{
          display: "flex",
          borderBottom: `1px solid ${theme.stroke.tertiary}`,
        }}
      >
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
              borderBottom: i === 0 ? `2px solid ${schemeBorder}` : "2px solid transparent",
              background: i === 0 ? schemeHeader : "transparent",
              opacity: i === 0 ? 1 : 0.45,
            }}
          >
            {label}
          </div>
        ))}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 10, minHeight: 0 }}>{children}</div>

      {dock ? (
        <div
          style={{
            flexShrink: 0,
            padding: "10px 10px 0",
            borderTop: `1px solid ${theme.stroke.secondary}`,
            background: scheme.panelBg,
          }}
        >
          {dock}
        </div>
      ) : null}

      <div
        role="separator"
        aria-label="Resize panel"
        onMouseDown={startResize}
        style={{
          position: "absolute",
          right: 0,
          bottom: 0,
          width: 18,
          height: 18,
          cursor: "nwse-resize",
          background: theme.stroke.secondary,
          borderTop: `1px solid ${theme.stroke.tertiary}`,
          borderLeft: `1px solid ${theme.stroke.tertiary}`,
        }}
      />
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
          <Text tone="secondary" size="small">
            БЗ обновлена · 12:34
          </Text>
        </Row>
      </div>
    </div>
  );
}

function kbSelectionSummary(selected: Record<KbId, boolean>): string {
  const count = KNOWLEDGE_BASES.filter((kb) => selected[kb.id]).length;
  if (count === KNOWLEDGE_BASES.length) return "Все базы знаний";
  if (count === 0) return "Выберите базы знаний";
  if (count === 1) {
    const kb = KNOWLEDGE_BASES.find((k) => selected[k.id]);
    return kb?.label ?? "1 база";
  }
  return `${count} базы выбрано`;
}

function KnowledgeBaseDropdown({ style }: { style?: CSSProperties }): JSX.Element {
  const theme = useHostTheme();
  const [open, setOpen] = useCanvasState("assistantKbDropdownOpen", false);
  const [selected, setSelected] = useCanvasState<Record<KbId, boolean>>(
    "assistantKbSelection",
    DEFAULT_KB_SELECTION,
  );

  const toggle = (id: KbId, checked: boolean) => {
    setSelected({ ...selected, [id]: checked });
  };

  const selectAll = () => {
    setSelected({ ...DEFAULT_KB_SELECTION });
  };

  const selectedCount = KNOWLEDGE_BASES.filter((kb) => selected[kb.id]).length;

  return (
    <div style={{ position: "relative", ...style }}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "8px 10px",
          borderRadius: 6,
          border: `1px solid ${theme.stroke.secondary}`,
          background: theme.bg.elevated,
          color: theme.text.primary,
          fontSize: 13,
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
          {kbSelectionSummary(selected)}
        </span>
        <span aria-hidden style={{ opacity: 0.55, fontSize: 11 }}>
          {open ? "▴" : "▾"}
        </span>
      </button>

      {open ? (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            marginTop: 4,
            zIndex: 30,
            padding: "8px 10px",
            background: theme.bg.elevated,
            border: `1px solid ${theme.stroke.secondary}`,
            borderRadius: 8,
            boxShadow: "0 8px 24px rgba(0, 0, 0, 0.12)",
          }}
        >
          <Row justify="space-between" align="center" wrap gap={6} style={{ marginBottom: 6 }}>
            <Text tone="secondary" size="small">
              {selectedCount} из {KNOWLEDGE_BASES.length}
            </Text>
            {selectedCount < KNOWLEDGE_BASES.length ? (
              <Button variant="ghost" onClick={selectAll}>
                Выбрать все
              </Button>
            ) : null}
          </Row>
          <Stack gap={4}>
            {KNOWLEDGE_BASES.map((kb) => (
              <Checkbox
                key={kb.id}
                label={kb.label}
                checked={selected[kb.id]}
                onChange={(checked) => toggle(kb.id, checked)}
              />
            ))}
          </Stack>
        </div>
      ) : null}
    </div>
  );
}

function ChatToolbar(): JSX.Element {
  return (
    <>
      <Row gap={6} wrap>
        <KnowledgeBaseDropdown style={{ flex: 1, minWidth: 160 }} />
        <Button variant="secondary">+ Новый</Button>
      </Row>
      <Button variant="ghost" style={{ alignSelf: "flex-start" }}>
        История диалогов
      </Button>
    </>
  );
}

function ChatThread({
  theme,
  scheme,
  streaming,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  streaming?: boolean;
}): JSX.Element {
  return (
    <div
      style={{
        minHeight: 180,
        padding: 10,
        background: theme.fill.quaternary,
        borderRadius: 8,
        border: `1px solid ${theme.stroke.tertiary}`,
      }}
    >
      <Stack gap={10}>
        <div>
          <Text tone="secondary" size="small">
            Вы
          </Text>
          <Text>Как оформить отпуск?</Text>
        </div>
        {streaming ? (
          <Row gap={8} align="center">
            <Text tone="secondary">Ассистент печатает…</Text>
            <Button variant="ghost">Остановить</Button>
          </Row>
        ) : (
          <div>
            <Text tone="secondary" size="small">
              Ассистент
            </Text>
            <Text>
              Для оформления отпуска подайте заявление в HR-портале не позднее чем за 5 рабочих дней. При
              необходимости приложите согласование руководителя.
            </Text>
            <Stack gap={4} style={{ marginTop: 8 }}>
              <Text weight="semibold" size="small">
                Источники (2)
              </Text>
              <Row gap={6} wrap align="center">
                <Pill size="sm" tone="success">
                  Регламент HR-12 · 94%
                </Pill>
                <Button variant="ghost">Открыть</Button>
                <Button variant="ghost">Копировать</Button>
              </Row>
              <Row gap={6} wrap align="center">
                <Pill size="sm" tone="info">
                  Положение об отпусках · 87%
                </Pill>
                <Button variant="ghost">Открыть</Button>
              </Row>
            </Stack>
            <AssistantFeedbackRow t={theme} stateKey="assistantFeedback_demo" />
          </div>
        )}
      </Stack>
    </div>
  );
}

function ChatInputBar({ theme, scheme }: { theme: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
  const [input, setInput] = useCanvasState("asstInput", "");
  const maxChars = 500;
  const charCount = input.length;
  const progress = Math.max(0, Math.min(100, Math.round((charCount / maxChars) * 100)));

  return (
    <>
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
      <Text tone="secondary" size="small">
        {charCount} / {maxChars} символов
      </Text>
      <div
        style={{
          height: 4,
          borderRadius: 2,
          background: theme.fill.tertiary,
          overflow: "hidden",
        }}
      >
        <div style={{ width: `${progress}%`, height: "100%", background: scheme.badge }} />
      </div>
    </>
  );
}

function ChatThreadShell({ theme, children }: { theme: CanvasHostTheme; children: JSX.Element }): JSX.Element {
  return (
    <div
      style={{
        minHeight: 180,
        padding: 10,
        background: theme.fill.quaternary,
        borderRadius: 8,
        border: `1px solid ${theme.stroke.tertiary}`,
      }}
    >
      {children}
    </div>
  );
}

function AssistantFeatureLayout({ thread }: { thread: JSX.Element }): JSX.Element {
  return (
    <Stack gap={10}>
      <ChatToolbar />
      {thread}
    </Stack>
  );
}

function ChatContent({
  theme,
  scheme,
  streaming,
}: {
  theme: CanvasHostTheme;
  scheme: SchemePalette;
  streaming?: boolean;
}): JSX.Element {
  return (
    <Stack gap={10}>
      <ChatToolbar />
      <ChatThread theme={theme} scheme={scheme} streaming={streaming} />
    </Stack>
  );
}

function EmptyContent(): JSX.Element {
  return (
    <Stack gap={12} style={{ padding: "32px 16px", textAlign: "center", alignItems: "center" }}>
      <Text weight="semibold">Выберите базы знаний и задайте вопрос</Text>
      <Text tone="secondary" size="small">
        По умолчанию поиск ведётся по всем доступным базам. Откройте список и снимите галочки, чтобы сузить область.
      </Text>
      <KnowledgeBaseDropdown style={{ width: "100%", maxWidth: 320 }} />
    </Stack>
  );
}

function ErrorContent({ theme, scheme }: { theme: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
  return (
    <Stack gap={10}>
      <Callout tone="danger">
        <Text>Не удалось получить ответ от LLM. Повторите запрос или обратитесь в поддержку.</Text>
      </Callout>
      <ChatContent theme={theme} scheme={scheme} />
    </Stack>
  );
}

function ClarifyContent({ theme, scheme }: { theme: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
  return (
    <Stack gap={10}>
      <ChatContent theme={theme} scheme={scheme} />
      <Callout tone="warning">
        <Stack gap={6}>
          <Text weight="semibold">Низкая релевантность (41%) — нужен уточняющий вопрос</Text>
          <Text size="small" tone="secondary">
            Покажите пользователю варианты уточнения до финального ответа.
          </Text>
          <Row gap={6} wrap>
            <Pill active>Уточнить подразделение</Pill>
            <Pill active>Уточнить тип документа</Pill>
            <Pill active>Показать шаблоны запроса</Pill>
          </Row>
        </Stack>
      </Callout>
    </Stack>
  );
}

function GenerateModal({ theme, scheme }: { theme: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
  return (
    <div
      style={{
        position: "relative",
        flex: 1,
        minHeight: 360,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Stack gap={10} style={{ flex: 1, opacity: 0.35, pointerEvents: "none" }} aria-hidden>
        <ChatToolbar />
        <ChatThread theme={theme} scheme={scheme} />
      </Stack>

      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "center",
          padding: "16px 12px",
          background: "rgba(0, 0, 0, 0.28)",
          borderRadius: 8,
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 340,
            padding: 16,
            background: theme.bg.elevated,
            border: `1px solid ${theme.stroke.secondary}`,
            borderRadius: 8,
            boxShadow: "0 12px 32px rgba(0, 0, 0, 0.18)",
          }}
        >
          <Stack gap={10}>
            <Text weight="semibold">Сгенерировать документ</Text>
            <Select
              value="word"
              onChange={() => undefined}
              options={[
                { value: "word", label: "Word — заявление на отпуск" },
                { value: "pdf", label: "PDF — служебная записка" },
              ]}
            />
            <Stack gap={4}>
              <Text tone="secondary" size="small">
                ФИО
              </Text>
              <TextInput value="Сидоров Пётр Константинович" onChange={() => undefined} />
            </Stack>
            <Stack gap={4}>
              <Text tone="secondary" size="small">
                Подразделение
              </Text>
              <TextInput value="Департамент ИТ" onChange={() => undefined} />
            </Stack>
            <Stack gap={4}>
              <Text tone="secondary" size="small">
                Дата начала
              </Text>
              <TextInput value="15.07.2026" onChange={() => undefined} />
            </Stack>
            <Row gap={8} justify="end" wrap>
              <Button variant="ghost">Отмена</Button>
              <Button variant="secondary">Создать черновик</Button>
              <Button variant="primary">Скачать</Button>
            </Row>
          </Stack>
        </div>
      </div>
    </div>
  );
}

function SummaryContent({ theme }: { theme: CanvasHostTheme }): JSX.Element {
  return (
    <AssistantFeatureLayout
      thread={
        <ChatThreadShell theme={theme}>
          <Stack gap={10}>
            <div>
              <Text tone="secondary" size="small">
                Вы
              </Text>
              <Stack gap={6}>
                <Row gap={8} wrap>
                  <Pill tone="info" size="sm">
                    meeting-2026-06-10.mp4
                  </Pill>
                  <Pill tone="success" size="sm">
                    Длительность 00:37:24
                  </Pill>
                </Row>
                <Text>Сделай саммаризацию записи совещания</Text>
              </Stack>
            </div>
            <div>
              <Text tone="secondary" size="small">
                Ассистент
              </Text>
              <Stack gap={10} style={{ marginTop: 4 }}>
                <Text weight="semibold">Саммаризация аудио/видео</Text>
                <Text size="small">
                  Краткое содержание: согласован запуск ассистента для back-office, подтверждена модель выбора базы
                  знаний по AD и подразделению.
                </Text>
                <Stack gap={4}>
                  <Text tone="secondary" size="small">
                    Таймкоды:
                  </Text>
                  <Text size="small">00:03:12 — источники знаний и fallback загрузкой файлов</Text>
                  <Text size="small">00:15:44 — политика SQL read-only и согласование с ИБ</Text>
                  <Text size="small">00:29:07 — KPI по скорости ответа и качеству</Text>
                </Stack>
                <Row gap={8} justify="end" wrap>
                  <Button variant="ghost">Открыть полную расшифровку</Button>
                  <Button variant="primary">Сохранить саммари</Button>
                </Row>
              </Stack>
            </div>
          </Stack>
        </ChatThreadShell>
      }
    />
  );
}

function ToolsContent({ theme }: { theme: CanvasHostTheme }): JSX.Element {
  return (
    <AssistantFeatureLayout
      thread={
        <ChatThreadShell theme={theme}>
          <Stack gap={10}>
            <div>
              <Text tone="secondary" size="small">
                Вы
              </Text>
              <Text>Нужен SQL read-only и запуск RPA-сценария с подтверждением</Text>
            </div>
            <div>
              <Text tone="secondary" size="small">
                Ассистент
              </Text>
              <Stack gap={8} style={{ marginTop: 4 }}>
                <Text weight="semibold">Инструменты ассистента</Text>
                <Row gap={6} wrap>
                  <Pill active>Код</Pill>
                  <Pill active>SQL</Pill>
                  <Pill active>RPA</Pill>
                  <Pill tone="warning" size="sm">
                    SQL: read-only
                  </Pill>
                </Row>
                <Callout tone="info">
                  <Text size="small">Для SQL и RPA требуется role-based доступ и аудит действий.</Text>
                </Callout>
                <Row gap={8} justify="end" wrap>
                  <Button variant="ghost">Показать политику ИБ</Button>
                  <Button variant="secondary">Сформировать SQL</Button>
                  <Button variant="primary">Запустить RPA с confirm</Button>
                </Row>
              </Stack>
            </div>
          </Stack>
        </ChatThreadShell>
      }
    />
  );
}

function TranslateContent({ theme }: { theme: CanvasHostTheme }): JSX.Element {
  return (
    <AssistantFeatureLayout
      thread={
        <ChatThreadShell theme={theme}>
          <Stack gap={10}>
            <div>
              <Text tone="secondary" size="small">
                Вы
              </Text>
              <Text>Подготовьте служебную записку о переносе сроков проекта</Text>
            </div>
            <div>
              <Text tone="secondary" size="small">
                Ассистент
              </Text>
              <Stack gap={8} style={{ marginTop: 4 }}>
                <Text weight="semibold">Перевод RU↔EN</Text>
                <Row gap={6} wrap align="center">
                  <Pill active>Исходный: RU</Pill>
                  <Pill active>Целевой: EN</Pill>
                  <Pill size="sm" tone="success">
                    Двуязычный ответ
                  </Pill>
                </Row>
                <Text size="small">RU: Подготовьте служебную записку о переносе сроков проекта.</Text>
                <Divider />
                <Text size="small">EN: Please prepare an internal memo regarding the project timeline shift.</Text>
                <Text size="small" tone="secondary">
                  Примечание: переводится текст запроса/ответа, не формат вложенного файла.
                </Text>
              </Stack>
            </div>
          </Stack>
        </ChatThreadShell>
      }
    />
  );
}

function usesInputDock(state: AssistantState): boolean {
  return state !== "generate";
}

function renderState(state: AssistantState, theme: CanvasHostTheme, scheme: SchemePalette): JSX.Element {
  switch (state) {
    case "empty":
      return <EmptyContent />;
    case "streaming":
      return <ChatContent theme={theme} scheme={scheme} streaming />;
    case "error":
      return <ErrorContent theme={theme} scheme={scheme} />;
    case "clarify":
      return <ClarifyContent theme={theme} scheme={scheme} />;
    case "generate":
      return <GenerateModal theme={theme} scheme={scheme} />;
    case "summary":
      return <SummaryContent theme={theme} />;
    case "tools":
      return <ToolsContent theme={theme} />;
    case "translate":
      return <TranslateContent theme={theme} />;
    default:
      return <ChatContent theme={theme} scheme={scheme} />;
  }
}

export default function AiAssistantUiMockup(): JSX.Element {
  const theme = useHostTheme();
  const [colorScheme, setColorScheme] = useCanvasState<ColorScheme>("assistantUiColorScheme", "default");
  const [state, setState] = useCanvasState<AssistantState>("assistantUiState", "chat");
  const [panelOpen, setPanelOpen] = useCanvasState("asstPanelOpen", true);
  const [panelMaximized, setPanelMaximized] = useCanvasState("assistantUiPanelMaximized", false);
  const [panelWidth, setPanelWidth] = useCanvasState("assistantUiPanelWidth", 400);
  const [panelHeight, setPanelHeight] = useCanvasState("assistantUiPanelHeight", 640);
  const scheme = getSchemePalette(theme, colorScheme);
  const setPanelSize = (nextWidth: number, nextHeight: number) => {
    setPanelWidth(Math.max(360, Math.min(860, Math.round(nextWidth))));
    setPanelHeight(Math.max(420, Math.min(860, Math.round(nextHeight))));
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
      <H1>ИИ-ассистент — макет UI</H1>
      <Text tone="secondary">
        Оболочка AI Hub: «Ассистент» и «Документы». Суфлёр — отдельное окно для операторов телефонии и чата.
        Ниже — состояния вкладки «Ассистент».
      </Text>

      <Card style={{ borderColor: scheme.accent }}>
        <CardHeader>Состояние экрана</CardHeader>
        <CardBody>
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
            <Select value={state} onChange={(v) => setState(v as AssistantState)} options={STATE_OPTIONS} />
            <Button variant="ghost" onClick={() => setState("chat")}>
              Сброс
            </Button>
          </Row>
          <Divider />
          <Row gap={6} wrap>
            {STATE_OPTIONS.map((opt) => (
              <Button
                key={opt.value}
                variant={state === opt.value ? "primary" : "ghost"}
                onClick={() => setState(opt.value as AssistantState)}
              >
                {opt.label}
              </Button>
            ))}
          </Row>
        </CardBody>
      </Card>

      <H2 style={{ color: scheme.accentControl }}>Превью панели</H2>

      {!panelOpen ? (
        <Row justify="end">
          <Button variant="primary" onClick={() => setPanelOpen(true)} style={{ background: scheme.accentControl }}>
            Открыть панель (FAB)
          </Button>
        </Row>
      ) : (
        <PanelChrome
          theme={theme}
          scheme={scheme}
          panelWidth={panelMaximized ? 860 : panelWidth}
          panelHeight={panelMaximized ? 860 : panelHeight}
          setPanelSize={setPanelSize}
          onMinimize={() => setPanelOpen(false)}
          onMaximize={() => setPanelMaximized(!panelMaximized)}
          onClose={() => setPanelOpen(false)}
          maximized={panelMaximized}
          dock={
            usesInputDock(state) ? <ChatInputBar theme={theme} scheme={scheme} /> : undefined
          }
        >
          {renderState(state, theme, scheme)}
        </PanelChrome>
      )}
    </Stack>
  );
}
