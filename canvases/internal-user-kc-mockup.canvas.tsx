import {
  Button,
  Divider,
  Pill,
  Row,
  Select,
  Stack,
  Text,
  TextArea,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";
import type { CanvasHostTheme } from "cursor/canvas";
import type { CSSProperties, JSX } from "react";
import { useEffect } from "react";

const CANVAS_MOCKUP_VERSION = "v1.0.0";
const WINDOW_CONTROLS_WIDTH = 108;
const RADIUS = 8;
const PREVIEW_MIN_WIDTH = 360;
const PREVIEW_MAX_WIDTH = 960;
const PREVIEW_MIN_HEIGHT = 280;
const PREVIEW_MAX_HEIGHT = 800;

type SchemePalette = {
  accentWeak: string;
  headerBg: string;
  panelBg: string;
};

type LlmSource = {
  title: string;
  scenario?: string;
};

type ChatTurn = {
  id: string;
  userText: string;
  userTime: string;
  llmText: string;
  relevance: string;
  relevanceTone: "success" | "warning" | "danger";
  sources: LlmSource[];
  etalon?: string;
};

const CHAT_HISTORY: ChatTurn[] = [
  {
    id: "turn-1",
    userText: "Какой срок действия вклада «Стройсбережения»?",
    userTime: "10:14",
    llmText:
      "Срок вклада «Стройсбережения» определяется договором; минимальный срок — 12 месяцев. Досрочное расторжение — по регламенту продукта.",
    relevance: "91%",
    relevanceTone: "success",
    sources: [{ title: "Вклады · Стройсбережения", scenario: "CC-SCR-008" }],
    etalon: "Срок вклада «Стройсбережения»",
  },
  {
    id: "turn-2",
    userText: "На какой период можно открыть вклад «Стройсбережения»?",
    userTime: "10:15",
    llmText:
      "Вклад «Стройсбережения» открывается на срок от 12 до 36 месяцев. Конкретный срок указывается в договоре вклада при оформлении.",
    relevance: "88%",
    relevanceTone: "success",
    sources: [{ title: "Вклады · Стройсбережения", scenario: "CC-SCR-008" }],
    etalon: "Срок вклада «Стройсбережения»",
  },
  {
    id: "turn-3",
    userText: "Можно ли закрыть вклад досрочно без потери процентов?",
    userTime: "10:16",
    llmText:
      "При досрочном расторжении вклада «Стройсбережения» проценты пересчитываются по ставке вклада «до востребования» на дату расторжения. Полное сохранение начисленных процентов при досрочном закрытии не предусмотрено.",
    relevance: "76%",
    relevanceTone: "warning",
    sources: [{ title: "Вклады · досрочное расторжение", scenario: "CC-SCR-008" }],
  },
];

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
      aria-label="Изменить размер окна"
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

function getSchemePalette(theme: CanvasHostTheme): SchemePalette {
  return {
    accentWeak: theme.stroke.secondary,
    headerBg: theme.fill.tertiary,
    panelBg: theme.bg.elevated,
  };
}

function panel(scheme: SchemePalette, extra?: CSSProperties): CSSProperties {
  return {
    background: scheme.panelBg,
    border: `1px solid ${scheme.accentWeak}`,
    borderRadius: RADIUS,
    ...extra,
  };
}

function UserMessage({
  t,
  scheme,
  text,
  time,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  text: string;
  time: string;
}): JSX.Element {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
      <div
        style={{
          maxWidth: "82%",
          padding: "10px 12px",
          borderRadius: 8,
          borderBottomRightRadius: 3,
          background: t.bg.secondary,
          border: `1px solid ${scheme.accentWeak}`,
          borderRight: `3px solid ${t.accent.primary}`,
        }}
      >
        <Text style={{ fontSize: 10, color: t.text.tertiary, marginBottom: 4 }}>Запрос · {time}</Text>
        <Text style={{ fontSize: 13, lineHeight: 1.45 }}>{text}</Text>
      </div>
    </div>
  );
}

function LlmResponse({
  t,
  scheme,
  text,
  relevance,
  relevanceTone,
  sources,
  etalon,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  text: string;
  relevance: string;
  relevanceTone: "success" | "warning" | "danger";
  sources: LlmSource[];
  etalon?: string;
}): JSX.Element {
  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          ...panel(scheme, { padding: "10px 12px" }),
          borderLeft: `3px solid ${t.accent.primary}`,
          background: t.bg.elevated,
        }}
      >
        <Row style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <Text weight="semibold" style={{ fontSize: 12 }}>
            Ответ LLM
          </Text>
          <Pill tone={relevanceTone} size="sm">
            {relevance}
          </Pill>
        </Row>
        <Text style={{ fontSize: 13, lineHeight: 1.5 }}>{text}</Text>
        <Row style={{ gap: 6, marginTop: 10, flexWrap: "wrap" }}>
          {sources.map((source) => (
            <Button key={source.title} variant="ghost" size="sm">
              {source.title}
              {source.scenario ? ` · ${source.scenario}` : ""} ↗
            </Button>
          ))}
        </Row>
        {etalon ? (
          <Text style={{ fontSize: 11, color: t.text.tertiary, marginTop: 8 }}>
            Эталон QU: «{etalon}»
          </Text>
        ) : null}
        <Row style={{ gap: 6, marginTop: 10 }}>
          <Button variant="ghost" size="sm">
            Эталон подтверждён
          </Button>
          <Button variant="ghost" size="sm">
            Низкая релевантность
          </Button>
        </Row>
      </div>
    </div>
  );
}

function ChatHistory({
  t,
  scheme,
  turns,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  turns: ChatTurn[];
}): JSX.Element {
  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "12px 14px",
        background: t.fill.quaternary,
        borderRadius: 6,
        border: `1px solid ${t.stroke.tertiary}`,
        minHeight: 0,
      }}
    >
      <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 12 }}>
        История тест-диалога · {turns.length} запроса
      </Text>
      {turns.map((turn, index) => (
        <div key={turn.id}>
          {index > 0 ? <Divider style={{ margin: "4px 0 14px" }} /> : null}
          <UserMessage t={t} scheme={scheme} text={turn.userText} time={turn.userTime} />
          <LlmResponse
            t={t}
            scheme={scheme}
            text={turn.llmText}
            relevance={turn.relevance}
            relevanceTone={turn.relevanceTone}
            sources={turn.sources}
            etalon={turn.etalon}
          />
        </div>
      ))}
    </div>
  );
}

export default function InternalUserKcMockup(): JSX.Element {
  const t = useHostTheme();
  const [windowOpen, setWindowOpen] = useCanvasState("internalKcWindowOpen", true);
  const [maximized, setMaximized] = useCanvasState("internalKcWindowMaximized", false);
  const [scenario, setScenario] = useCanvasState("internalKcScenario", "CC-SCR-008");
  const [draft, setDraft] = useCanvasState(
    "internalKcDraft",
    "А какие документы нужны для открытия вклада?",
  );
  const [previewWidth, setPreviewWidth] = useCanvasState("internalKcPreviewWidth", 680);
  const [previewHeight, setPreviewHeight] = useCanvasState("internalKcPreviewHeight", 520);
  const [canvasBuild, setCanvasBuild] = useCanvasState("_canvasBuild", "");
  const scheme = getSchemePalette(t);

  useEffect(() => {
    if (canvasBuild !== CANVAS_MOCKUP_VERSION) {
      setCanvasBuild(CANVAS_MOCKUP_VERSION);
    }
  }, [canvasBuild, setCanvasBuild]);

  const minHeight = maximized ? 480 : PREVIEW_MIN_HEIGHT;
  const boundedWidth = Math.max(PREVIEW_MIN_WIDTH, Math.min(PREVIEW_MAX_WIDTH, previewWidth));
  const boundedHeight = Math.max(minHeight, Math.min(PREVIEW_MAX_HEIGHT, previewHeight));

  const setPreviewSize = (nextWidth: number, nextHeight: number) => {
    setPreviewWidth(Math.max(PREVIEW_MIN_WIDTH, Math.min(PREVIEW_MAX_WIDTH, Math.round(nextWidth))));
    setPreviewHeight(Math.max(minHeight, Math.min(PREVIEW_MAX_HEIGHT, Math.round(nextHeight))));
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
    return (
      <Stack style={{ padding: 20, maxWidth: PREVIEW_MAX_WIDTH, margin: "0 auto" }}>
        <Button variant="primary" onClick={() => setWindowOpen(true)}>
          Открыть окно тест-диалога
        </Button>
      </Stack>
    );
  }

  return (
    <Stack style={{ padding: 20, maxWidth: PREVIEW_MAX_WIDTH, margin: "0 auto" }}>
      <div
        style={{
          position: "relative",
          width: boundedWidth,
          maxWidth: "100%",
          height: boundedHeight,
          minHeight: 0,
          transition: "width 160ms ease, height 160ms ease",
          ...panel(scheme, {
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            padding: 0,
          }),
        }}
      >
        <div
          style={{
            position: "relative",
            padding: "10px 16px",
            paddingRight: WINDOW_CONTROLS_WIDTH,
            borderBottom: `1px solid ${t.stroke.secondary}`,
            background: scheme.headerBg,
            flexShrink: 0,
          }}
        >
          <Text weight="semibold">Тест-диалог · внутренний пользователь КЦ</Text>
          <WindowTitleBarControls
            theme={t}
            onMinimize={() => setWindowOpen(false)}
            onMaximize={() => setMaximized(!maximized)}
            onClose={() => setWindowOpen(false)}
            maximized={maximized}
          />
        </div>

        <div
          style={{
            padding: "12px 16px 0",
            borderBottom: `1px solid ${t.stroke.secondary}`,
            flexShrink: 0,
          }}
        >
          <Row style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ flex: 1, minWidth: 140 }}>
              <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 4 }}>Сценарий</Text>
              <Select
                value={scenario}
                onChange={setScenario}
                options={[
                  { value: "CC-SCR-008", label: "CC-SCR-008 · Вклады" },
                  { value: "CC-SCR-003", label: "CC-SCR-003 · Переводы" },
                  { value: "CC-SCR-001", label: "CC-SCR-001 · Карты" },
                ]}
              />
            </div>
            <div style={{ flex: 1, minWidth: 140 }}>
              <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 4 }}>Промпт</Text>
              <Select
                value="sufler_cc"
                onChange={() => {}}
                options={[{ value: "sufler_cc", label: "sufler_cc (production)" }]}
              />
            </div>
          </Row>
        </div>

        <div style={{ padding: 16, flex: 1, display: "flex", flexDirection: "column", minHeight: 0, gap: 12 }}>
          <ChatHistory t={t} scheme={scheme} turns={CHAT_HISTORY} />

          <div style={{ flexShrink: 0 }}>
            <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 6 }}>Новый тестовый запрос</Text>
            <TextArea
              value={draft}
              onChange={setDraft}
              placeholder="Введите тестовый вопрос или перефразировку эталонной реплики…"
              style={{ minHeight: 64 }}
            />
            <Row style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
              <Button variant="primary">Отправить</Button>
              <Button variant="secondary">Очистить</Button>
              <Button variant="ghost">Новый диалог</Button>
            </Row>
          </div>
        </div>

        <PreviewResizeHandle t={t} onMouseDown={startResize} />
      </div>
    </Stack>
  );
}
