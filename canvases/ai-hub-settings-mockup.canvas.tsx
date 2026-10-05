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
  BarChart,
  PieChart,
} from "cursor/canvas";
import type { CanvasHostTheme } from "cursor/canvas";
import type { CSSProperties, JSX } from "react";

type AdminRole = "kb_admin" | "cc_admin" | "doc_admin" | "auditor";
type ColorScheme =
  | "default"
  | "belarusbank_classic"
  | "belarusbank_soft"
  | "belarusbank_emerald"
  | "belarusbank_night";
const COLOR_SCHEME_ORDER: ColorScheme[] = [
  "default",
  "belarusbank_classic",
  "belarusbank_soft",
  "belarusbank_emerald",
  "belarusbank_night",
];
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

type Screen =
  | "audit"
  | "llm_config_assistant"
  | "model_params"
  | "prompts_assistant"
  | "capabilities"
  | "kb_admin"
  | "qu_admin"
  | "data_sources"
  | "assistant_tools"
  | "monitoring"
  | "llm_config_cc"
  | "scenario_editor"
  | "scenario_test"
  | "scenario_bindings"
  | "sufler_policies"
  | "doc_types"
  | "doc_export"
  | "external";

type NavItem = {
  id: Screen;
  label: string;
  group: string;
  star?: boolean;
  profile?: "assistant" | "cc";
  roles: AdminRole[];
};

const ROLES: Record<AdminRole, string> = {
  kb_admin: "Админ БЗ",
  cc_admin: "Админ сценариев / КЦ",
  doc_admin: "Админ OCR",
  auditor: "Аудитор (read)",
};

const NAV: NavItem[] = [
  { id: "audit", label: "Подразделения и журнал", group: "ОБЩЕЕ", roles: ["kb_admin", "cc_admin", "doc_admin", "auditor"] },
  { id: "llm_config_assistant", label: "Конфигурация LLM", group: "АССИСТЕНТ", star: true, roles: ["kb_admin", "auditor"] },
  { id: "model_params", label: "Параметры модели LLM", group: "АССИСТЕНТ", profile: "assistant", roles: ["kb_admin", "auditor"] },
  { id: "prompts_assistant", label: "Промпты ассистента", group: "АССИСТЕНТ", roles: ["kb_admin", "auditor"] },
  { id: "capabilities", label: "Навыки и инструменты", group: "АССИСТЕНТ", roles: ["kb_admin", "auditor"] },
  { id: "kb_admin", label: "Базы знаний", group: "АССИСТЕНТ", roles: ["kb_admin", "auditor"] },
  { id: "qu_admin", label: "Понимание запросов", group: "АССИСТЕНТ", roles: ["kb_admin", "auditor"] },
  { id: "data_sources", label: "Источники данных", group: "АССИСТЕНТ", roles: ["kb_admin", "auditor"] },
  { id: "assistant_tools", label: "Инструменты ассистента", group: "АССИСТЕНТ", roles: ["kb_admin", "auditor"] },
  { id: "monitoring", label: "Аналитика ассистента", group: "АССИСТЕНТ", roles: ["kb_admin", "auditor"] },
  { id: "llm_config_cc", label: "Конфигурация LLM КЦ", group: "СУФЛЁР / КЦ", star: true, roles: ["cc_admin", "kb_admin", "auditor"] },
  { id: "scenario_editor", label: "Редактор сценариев", group: "СУФЛЁР / КЦ", roles: ["cc_admin", "kb_admin", "auditor"] },
  { id: "scenario_test", label: "Тест сценария", group: "СУФЛЁР / КЦ", roles: ["cc_admin", "kb_admin", "auditor"] },
  { id: "scenario_bindings", label: "Сценарии суфлёра", group: "СУФЛЁР / КЦ", roles: ["cc_admin", "kb_admin", "auditor"] },
  { id: "sufler_policies", label: "Политики суфлёра", group: "СУФЛЁР / КЦ", roles: ["cc_admin", "kb_admin", "auditor"] },
  { id: "model_params", label: "Параметры модели (КЦ)", group: "СУФЛЁР / КЦ", profile: "cc", roles: ["cc_admin", "kb_admin", "auditor"] },
  { id: "doc_types", label: "Типы документов", group: "ДОКУМЕНТЫ", roles: ["doc_admin", "auditor"] },
  { id: "doc_export", label: "Экспорт документов", group: "ДОКУМЕНТЫ", roles: ["doc_admin", "auditor"] },
  { id: "external", label: "Внешние системы", group: "ССЫЛКИ", roles: ["kb_admin", "cc_admin", "doc_admin", "auditor"] },
];

type LayerDef = {
  n: number;
  name: string;
  status: "ok" | "warn" | "pending";
  link: Screen | null;
};

const LAYERS_ASSISTANT: LayerDef[] = [
  { n: 0, name: "Параметры модели", status: "ok", link: "model_params" },
  { n: 1, name: "Промпты", status: "ok", link: "prompts_assistant" },
  { n: 2, name: "Навыки", status: "warn", link: "capabilities" },
  { n: 3, name: "Базы знаний", status: "ok", link: "kb_admin" },
  { n: 4, name: "Понимание запросов", status: "ok", link: "qu_admin" },
  { n: 5, name: "Политики", status: "ok", link: "assistant_tools" },
  { n: 6, name: "Тест", status: "pending", link: null },
];

const LAYERS_CC: LayerDef[] = [
  { n: 0, name: "Параметры модели", status: "ok", link: "model_params" },
  { n: 1, name: "Промпты / сценарии", status: "ok", link: "scenario_editor" },
  { n: 2, name: "Flow «Услуга»", status: "ok", link: "scenario_editor" },
  { n: 3, name: "СУЗ / БЗ", status: "ok", link: "kb_admin" },
  { n: 4, name: "Модуль понимания", status: "ok", link: "qu_admin" },
  { n: 5, name: "Политики суфлёра", status: "ok", link: "sufler_policies" },
  { n: 6, name: "Тест сценария", status: "pending", link: "scenario_test" },
];

const CAPABILITIES = [
  { name: "Поиск по БЗ (RAG)", on: true, link: "Базы знаний" },
  { name: "Внешние источники", on: true, link: "Источники данных" },
  { name: "Генерация документов", on: true, link: "Шаблоны Word/PDF" },
  { name: "RPA", on: true, link: "Реестр RPA" },
  { name: "SQL / код", on: false, link: "Политика SQL" },
  { name: "Саммаризация файлов", on: true, link: "Лимиты файлов" },
  { name: "Перевод RU↔EN", on: true, link: "Промпты → task" },
  { name: "Уточняющие вопросы", on: true, link: "QU" },
  { name: "Контекст истории", on: true, link: "auto / manual" },
];

type TaskPromptDef = {
  id: string;
  name: string;
  status: "pub" | "draft";
  trigger: string;
  body: string;
};

const TASK_PROMPTS: TaskPromptDef[] = [
  {
    id: "session_context",
    name: "сессии пользователя",
    status: "pub",
    trigger: "Начало сессии",
    body: "Учитывай контекст текущей сессии {{session_id}} и роль пользователя {{dept}}.",
  },
  {
    id: "dialog_tone",
    name: "общение в диалоге",
    status: "pub",
    trigger: "Ответ в чате",
    body: "Отвечай профессионально и кратко. Сохраняй тон банка без канцелярита.",
  },
  {
    id: "clarify",
    name: "уточняющий вопрос",
    status: "draft",
    trigger: "Запрос уточнения (QU)",
    body: "Сформулируй один короткий уточняющий вопрос, чтобы сузить тему. Не задавай более двух уточнений подряд без попытки ответа.",
  },
  {
    id: "history_context",
    name: "контекст истории",
    status: "pub",
    trigger: "Контекст истории (auto/manual)",
    body: "Используй последние {{history_limit}} сообщений из истории диалога, если они релевантны запросу.",
  },
  {
    id: "translate_en_ru",
    name: "перевод en→ru",
    status: "pub",
    trigger: "Перевод EN→RU",
    body: "Переведи текст на русский язык, сохраняя терминологию банка и форматирование.",
  },
  {
    id: "translate_ru_en",
    name: "перевод ru→en",
    status: "pub",
    trigger: "Перевод RU→EN",
    body: "Translate the text to English, preserving banking terminology and formatting.",
  },
];

function shell(t: CanvasHostTheme, extra?: CSSProperties): CSSProperties {
  return {
    background: t.fill.secondary,
    border: `1px solid ${t.stroke.secondary}`,
    borderRadius: 8,
    ...extra,
  };
}

function statusPill(status: "ok" | "warn" | "pending"): JSX.Element {
  if (status === "ok") return <Pill tone="success">OK</Pill>;
  if (status === "warn") return <Pill tone="warning">Внимание</Pill>;
  return <Pill tone="neutral">Не настроено</Pill>;
}

function PageHeader({
  title,
  badge,
  subtitle,
}: {
  title: string;
  badge?: string;
  subtitle?: string;
}): JSX.Element {
  return (
    <Stack gap={4}>
      <Text variant="muted" style={{ fontSize: 12 }}>
        Центр настроек / {title}
      </Text>
      <Row gap={8} align="center">
        <H1>{title}</H1>
        {badge && <Pill tone="accent">{badge}</Pill>}
      </Row>
      {subtitle && <Text variant="muted">{subtitle}</Text>}
    </Stack>
  );
}

function PaletteDebug({ t, scheme }: { t: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
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
        <Row key={entry.key} gap={6} align="center" style={{ padding: "2px 6px", borderRadius: 6, border: `1px solid ${t.stroke.tertiary}` }}>
          <span
            aria-label={entry.key}
            style={{
              width: 12,
              height: 12,
              borderRadius: 3,
              background: entry.value,
              display: "inline-block",
              border: `1px solid ${t.stroke.tertiary}`,
            }}
          />
          <Text variant="muted" style={{ fontSize: 11 }}>
            {entry.key}
          </Text>
        </Row>
      ))}
    </Row>
  );
}

function LayerDashboard({
  t,
  layers,
  profile,
  onNavigate,
  onTest,
}: {
  t: CanvasHostTheme;
  layers: LayerDef[];
  profile: string;
  onNavigate: (s: Screen) => void;
  onTest?: () => void;
}): JSX.Element {
  return (
    <Stack gap={16}>
      <Grid columns={2} gap={10}>
        {layers.map((layer) => (
          <div key={layer.n} style={shell(t, { padding: 12 })}>
            <Row gap={8} align="center">
              <Text variant="label">
                {layer.n}. {layer.name}
              </Text>
              <Spacer />
              {statusPill(layer.status)}
            </Row>
            {layer.link && (
              <Button variant="ghost" size="sm" onClick={() => onNavigate(layer.link as Screen)}>
                Настроить →
              </Button>
            )}
          </div>
        ))}
      </Grid>
      {onTest ? (
        <Button variant="primary" onClick={onTest}>
          Проверить конфигурацию
        </Button>
      ) : (
        <Button variant="primary">Проверить конфигурацию</Button>
      )}
      <Text variant="muted" style={{ fontSize: 12 }}>
        Профиль: {profile}
      </Text>
    </Stack>
  );
}

function NavButton({
  item,
  active,
  allowed,
  onSelect,
  t,
  scheme,
}: {
  item: NavItem;
  active: boolean;
  allowed: boolean;
  onSelect: (item: NavItem) => void;
  t: CanvasHostTheme;
  scheme: SchemePalette;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={() => onSelect(item)}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        padding: "7px 12px",
        marginBottom: 2,
        border: "none",
        borderRadius: 6,
        cursor: "pointer",
        fontSize: 13,
        fontFamily: "inherit",
        background: active ? scheme.headerBg : "transparent",
        color: active ? t.text.primary : allowed ? t.text.secondary : t.text.muted,
        fontWeight: active ? 600 : 400,
        borderLeft: active ? `3px solid ${scheme.accent}` : "3px solid transparent",
        opacity: allowed ? 1 : 0.65,
      }}
    >
      {item.star ? "★ " : ""}
      {item.label}
      {!allowed && " (read)"}
    </button>
  );
}

function ModelParamsScreen({
  t,
  profile,
}: {
  t: CanvasHostTheme;
  profile: "assistant" | "cc";
}): JSX.Element {
  const isCc = profile === "cc";
  return (
    <Stack gap={16}>
      <PageHeader
        title="Параметры модели LLM"
        badge={isCc ? "sufler_cc" : "assistant_bank"}
        subtitle={isCc ? "Профиль sufler_cc · preset «строгий суфлёр»" : "Профиль assistant_bank"}
      />
      <Row gap={6}>
        <Pill tone={!isCc ? "accent" : "neutral"}>Ассистент</Pill>
        <Pill tone={isCc ? "accent" : "neutral"}>КЦ (sufler_cc)</Pill>
      </Row>
      <Row gap={24} align="stretch">
        <Stack gap={12} style={{ flex: 1 }}>
          <Text variant="label">Генерация</Text>
          <Row gap={8} align="center">
            <Text style={{ width: 148 }}>Температура</Text>
            <TextInput value={isCc ? "0.2" : "0.35"} onChange={() => {}} style={{ width: 72 }} />
          </Row>
          <Row gap={8} align="center">
            <Text style={{ width: 148 }}>Max ответа</Text>
            <TextInput value={isCc ? "500" : "1200"} onChange={() => {}} style={{ width: 72 }} />
          </Row>
          <Row gap={8} align="center">
            <Text style={{ width: 148 }}>Preset</Text>
            <Select
              value={isCc ? "short" : "standard"}
              onChange={() => {}}
              options={[
                { value: "short", label: "Краткий" },
                { value: "standard", label: "Стандарт" },
                { value: "long", label: "Развёрнутый" },
              ]}
            />
          </Row>
        </Stack>
        <Stack gap={12} style={{ flex: 1 }}>
          <Text variant="label">RAG / индексация</Text>
          <Row gap={8} align="center">
            <Text style={{ width: 148 }}>Chunk size</Text>
            <TextInput value="512" onChange={() => {}} style={{ width: 72 }} />
          </Row>
          <Row gap={8} align="center">
            <Text style={{ width: 148 }}>Overlap</Text>
            <TextInput value="64" onChange={() => {}} style={{ width: 72 }} />
          </Row>
          <Row gap={8} align="center">
            <Text style={{ width: 148 }}>Порог в контекст</Text>
            <TextInput value={isCc ? "78%" : "72%"} onChange={() => {}} style={{ width: 72 }} />
          </Row>
          <Row gap={8} align="center">
            <Text style={{ width: 148 }}>Детерм. из БЗ</Text>
            <TextInput value="95%" onChange={() => {}} style={{ width: 72 }} />
          </Row>
        </Stack>
        <Stack gap={8} style={{ flex: 0.6 }}>
          <Text variant="label">Read-only</Text>
          <Stat label="Контекстное окно" value="≥8200" tone="neutral" />
          <Stat label="Модель LLM" value={isCc ? "sufler-v1" : "assist-v2"} tone="neutral" />
        </Stack>
      </Row>
      <Callout variant="info">
        Порог понимания запросов настраивается в разделе «Понимание запросов».
      </Callout>
      <Row gap={8}>
        <Button variant="secondary">Сброс к дефолту платформы</Button>
        <Button variant="primary">Сохранить</Button>
        <Button variant="secondary">Тест с параметрами</Button>
      </Row>
    </Stack>
  );
}

function SkillTaskPromptsPanel({ t }: { t: CanvasHostTheme }): JSX.Element {
  const [selected, setSelected] = useCanvasState("task_prompt_sel", "clarify");
  const prompt = TASK_PROMPTS.find((p) => p.id === selected) ?? TASK_PROMPTS[0];

  const panelGrid: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "200px minmax(0, 1fr)",
    gap: 12,
    alignItems: "stretch",
    minHeight: 420,
    width: "100%",
  };

  const columnShell = (extra?: CSSProperties): CSSProperties => ({
    ...shell(t, { padding: 12, minWidth: 0, overflow: "hidden", ...extra }),
  });

  return (
    <div style={panelGrid}>
      <div style={{ ...columnShell(), display: "flex", flexDirection: "column" }}>
        <Button variant="secondary" size="sm">
          + Добавить
        </Button>
        <div style={{ marginTop: 12, flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
          {TASK_PROMPTS.map((p) => {
            const active = p.id === selected;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => setSelected(p.id)}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 10px",
                  border: active ? `1px solid ${t.stroke.secondary}` : "1px solid transparent",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontSize: 13,
                  fontFamily: "inherit",
                  background: active ? t.fill.tertiary : "transparent",
                  color: active ? t.text.primary : t.text.secondary,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 13, lineHeight: 1.35 }}>{p.name}</span>
                  <Pill tone={p.status === "pub" ? "success" : "warning"} size="sm">
                    {p.status === "pub" ? "опубликован" : "черновик"}
                  </Pill>
                </div>
              </button>
            );
          })}
        </div>
        <Button variant="secondary" size="sm" disabled={prompt.status === "pub"} style={{ marginTop: 12 }}>
          Удалить
        </Button>
      </div>

      <div style={{ ...columnShell(), display: "flex", flexDirection: "column", gap: 12 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
            paddingBottom: 12,
            borderBottom: `1px solid ${t.stroke.secondary}`,
          }}
        >
          <Pill tone={prompt.status === "pub" ? "success" : "neutral"}>
            {prompt.status === "pub" ? "Опубликован" : "Черновик"}
          </Pill>
          <div style={{ flex: 1, minWidth: 12 }} />
          <Button size="sm">Сохранить черновик</Button>
          <Button variant="primary" size="sm">
            Опубликовать
          </Button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
          <Stack gap={4}>
            <Text variant="label">Тип промпта</Text>
            <Select
              value="task"
              onChange={() => {}}
              options={[{ value: "task", label: "Task — задание" }]}
            />
          </Stack>
          <Stack gap={4}>
            <Text variant="label">Событие (триггер)</Text>
            <Select
              value={prompt.id}
              onChange={() => {}}
              options={TASK_PROMPTS.map((p) => ({ value: p.id, label: p.trigger }))}
            />
          </Stack>
        </div>

        <TextArea
          value={prompt.body}
          onChange={() => {}}
          rows={7}
          style={{ width: "100%", boxSizing: "border-box", resize: "vertical", minHeight: 140 }}
        />

        <div style={{ ...shell(t, { padding: 12 }), display: "flex", flexDirection: "column", gap: 10 }}>
          <Text variant="label">Preview · тест</Text>
          <div style={{ ...shell(t, { padding: 10, fontSize: 13, lineHeight: 1.5 }) }}>
            <Text>{prompt.body}</Text>
          </div>
          <Button variant="primary" size="sm" style={{ alignSelf: "flex-start" }}>
            Запустить тест на событии
          </Button>
          <Callout variant="info">
            Переменные {"{{kb}}"}, {"{{user}}"}, {"{{dept}}"} подставляются при test-run на выбранном событии.
          </Callout>
        </div>
      </div>
    </div>
  );
}

function CapabilitiesScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  return (
    <Stack gap={16}>
      <PageHeader
        title="Навыки и инструменты"
        badge="assistant_bank"
        subtitle="Навыки и инструменты ассистента · отдельно от skill-групп чата"
      />
      <Grid columns={2} gap={10}>
        {CAPABILITIES.map((c) => (
          <div key={c.name} style={shell(t, { padding: 12 })}>
            <Row gap={8} align="center">
              <Toggle checked={c.on} onChange={() => {}} label={c.name} />
              <Spacer />
              <Pill tone={c.on ? "success" : "neutral"}>{c.on ? "Вкл" : "Выкл"}</Pill>
            </Row>
            <Text variant="muted" style={{ fontSize: 12, marginTop: 6 }}>
              → {c.link}
            </Text>
          </div>
        ))}
      </Grid>
      <Divider />
      <Stack gap={4}>
        <H2 style={{ fontSize: 16, margin: 0 }}>Навыки · промпты типа Task</H2>
        <Text variant="muted" style={{ fontSize: 13 }}>
          Capabilities с текстовыми инструкциями. Остальные — deep link на детальные экраны.
        </Text>
      </Stack>
      <SkillTaskPromptsPanel t={t} />
    </Stack>
  );
}

function PromptsAssistantScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  const columnShell = (extra?: CSSProperties): CSSProperties => ({
    ...shell(t, { padding: 12, minWidth: 0, overflow: "hidden", ...extra }),
  });

  return (
    <Stack gap={12}>
      <PageHeader title="Промпты ассистента" badge="assistant_bank" subtitle="Редактор промптов · embed Studio" />
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "180px minmax(0, 1fr)",
          gap: 12,
          alignItems: "stretch",
          minHeight: 300,
          width: "100%",
        }}
      >
        <div style={columnShell()}>
          <Button variant="secondary" size="sm">
            + Промпт
          </Button>
          <Divider />
          <Stack gap={8}>
            <Stack gap={2}>
              <Text variant="label">System</Text>
              <Text>default</Text>
            </Stack>
            <Stack gap={2}>
              <Text variant="label">Task</Text>
              <Text>summary_doc</Text>
            </Stack>
            <Stack gap={2}>
              <Text variant="label">Scope</Text>
              <Text>HR policies</Text>
            </Stack>
          </Stack>
        </div>

        <div style={{ ...columnShell(), display: "flex", flexDirection: "column", gap: 12 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexWrap: "wrap",
              paddingBottom: 8,
              borderBottom: `1px solid ${t.stroke.secondary}`,
            }}
          >
            <Pill tone="neutral">Черновик v3</Pill>
            <div style={{ flex: 1, minWidth: 12 }} />
            <Button size="sm">Черновик</Button>
            <Button variant="primary" size="sm">
              Опубликовать
            </Button>
          </div>
          <TextArea
            value="Ты внутренний ассистент банка. Используй {{kb}}. Не выдумывай факты."
            onChange={() => {}}
            rows={8}
            style={{ width: "100%", boxSizing: "border-box", resize: "vertical" }}
          />
          <div style={{ ...shell(t, { padding: 12 }), display: "flex", flexDirection: "column", gap: 10 }}>
            <Text variant="label">Preview</Text>
            <Select
              value="hr"
              onChange={() => {}}
              options={[{ value: "hr", label: "БЗ: HR policies" }]}
            />
            <TextInput value="Как оформить отпуск?" onChange={() => {}} />
            <Callout variant="success">Ответ 87% · 2 источника</Callout>
            <Button variant="primary" size="sm" style={{ alignSelf: "flex-start" }}>
              Отправить тест
            </Button>
          </div>
        </div>
      </div>
    </Stack>
  );
}

function KbAdminScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  return (
    <Stack gap={12}>
      <PageHeader title="Базы знаний" subtitle="CRUD · scope AD · индексация и webhook СУЗ" />
      <Row gap={12} align="stretch" style={{ width: "100%" }}>
        <div style={{ ...shell(t, { width: 220, padding: 12 }), flexShrink: 0 }}>
          <Button variant="secondary" size="sm">
            + Создать БЗ
          </Button>
          <Stack gap={6} style={{ marginTop: 12 }}>
            {[
              ["HR policies", "Ручная загрузка"],
              ["IT runbooks", "Ручная загрузка"],
              ["СУЗ Битрикс", "СУЗ Битрикс"],
            ].map(([kb, source]) => (
              <Stack key={kb} gap={2}>
                <Text>{kb}</Text>
                <Text style={{ opacity: 0.7, fontSize: 12 }}>{source}</Text>
              </Stack>
            ))}
          </Stack>
        </div>
        <div style={{ ...shell(t, { flex: 1, minWidth: 0, padding: 12 }) }}>
          <Row gap={8}>
            <Stat label="Индекс" value="98%" tone="success" />
            <Stat label="Документов" value="1 240" tone="neutral" />
            <Stat label="Webhook СУЗ" value="OK" tone="success" />
          </Row>
          <Divider />
          <Table
            headers={["Документ", "Источник", "%"]}
            rows={[
              ["Положение об отпусках.pdf", "СУЗ Битрикс", "100"],
              ["Регламент ДБО.docx", "Ручная загрузка", "96"],
            ]}
          />
        </div>
      </Row>
    </Stack>
  );
}

function QuAdminScreen({ t, profile }: { t: CanvasHostTheme; profile: "assistant" | "cc" }): JSX.Element {
  const isCc = profile === "cc";
  return (
    <Stack gap={16}>
      <PageHeader
        title={isCc ? "Модуль понимания" : "Понимание запросов"}
        badge={isCc ? "UND-T-01" : undefined}
        subtitle={
          isCc
            ? "Пороги релевантности · QU · профиль sufler_cc"
            : "Семантический поиск · пороги релевантности"
        }
      />
      <Row gap={12}>
        <Stack gap={8} style={{ flex: 1 }}>
          <Text variant="label">Тестовый запрос</Text>
          <TextInput value="оформление отпуска сотруднику" onChange={() => {}} />
          <Button variant="primary" size="sm">
            Preview
          </Button>
        </Stack>
        <div style={{ ...shell(t, { flex: 1, minWidth: 0, padding: 12 }) }}>
          <Text variant="label">Найденные документы</Text>
          <Text>Положение об отпусках — 92%</Text>
          <Text>FAQ HR — 78%</Text>
        </div>
      </Row>
      <Row gap={8} align="center">
        <Text style={{ width: 200 }}>Мин. порог релевантности</Text>
        <TextInput value="65%" onChange={() => {}} style={{ width: 80 }} />
      </Row>
      <Callout variant="info">
        Семантические пороги RAG настраиваются в «Параметры модели LLM».
      </Callout>
    </Stack>
  );
}

type AssistantToolsTab = "rpa" | "templates" | "sql";

const RPA_ROWS: string[][] = [
  ["RPA-001", "Создать заявку в SD", "BB_IT", "✓"],
  ["RPA-002", "Справка 2-НДФЛ", "BB_HR", "✓"],
  ["RPA-003", "Статус заявки по кредиту", "BB_CC_Retail", "✓"],
  ["RPA-004", "Блокировка карты (экстренная)", "BB_CC_Retail", "✓"],
  ["RPA-005", "Заказ справки об остатке", "BB_CC_Premium", "—"],
];

const TEMPLATE_ROWS: string[][] = [
  ["TPL-001", "Ответ по вкладу «Стройсбережения»", "Продукты", "26.06.2026", "✓"],
  ["TPL-002", "Инструкция: смена PIN в мобильном банке", "ДБО", "24.06.2026", "✓"],
  ["TPL-003", "Отказ в кредите — вежливая формулировка", "Кредиты", "22.06.2026", "✓"],
  ["TPL-004", "Эскалация на супервайзера", "КЦ", "20.06.2026", "✓"],
  ["TPL-005", "Приветствие VIP-клиента", "Премиум", "18.06.2026", "—"],
  ["TPL-006", "Запрос недостающих документов по ипотеке", "Ипотека", "15.06.2026", "✓"],
];

const SQL_ROWS: string[][] = [
  ["SQL-001", "Справочник отделений (read-only)", "SQL", "BB_ALL", "✓"],
  ["SQL-002", "Статус заявки по номеру договора", "SQL", "BB_CC_Retail", "✓"],
  ["SQL-003", "Остаток по счёту клиента", "SQL", "BB_CC_Premium", "✓"],
  ["PY-001", "Расчёт лимита перевода по карте", "Python", "BB_CC_Retail", "✓"],
  ["PY-002", "Проверка eligibility автокредита", "Python", "BB_Mortgage", "—"],
  ["JS-001", "Форматирование номера счёта IBAN", "JavaScript", "BB_IT", "✓"],
];

function AssistantToolsScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  const [tab, setTab] = useCanvasState<AssistantToolsTab>("assistant_tools_tab", "rpa");

  const tabs: { id: AssistantToolsTab; label: string }[] = [
    { id: "rpa", label: "RPA" },
    { id: "templates", label: "Шаблоны" },
    { id: "sql", label: "SQL / код" },
  ];

  const tableByTab: Record<AssistantToolsTab, { headers: string[]; rows: string[][] }> = {
    rpa: { headers: ["ID", "Название", "AD-группы", "Активен"], rows: RPA_ROWS },
    templates: { headers: ["ID", "Название", "Категория", "Изменён", "Активен"], rows: TEMPLATE_ROWS },
    sql: { headers: ["ID", "Описание", "Язык", "AD-группы", "Активен"], rows: SQL_ROWS },
  };

  const addLabel =
    tab === "rpa" ? "+ Сценарий RPA" : tab === "templates" ? "+ Шаблон" : "+ Запрос / скрипт";

  const calloutByTab: Record<AssistantToolsTab, string> = {
    rpa: "RPA-сценарии выполняются через whitelist: только перечисленные ID доступны ассистенту в рантайме.",
    templates: "Шаблоны ответов подставляются оператором или ассистентом. Категория определяет область видимости в ARM.",
    sql: "SQL и скрипты выполняются в sandbox с read-only доступом к разрешённым источникам. Публикация — через ревью.",
  };

  const { headers, rows } = tableByTab[tab];

  return (
    <Stack gap={12}>
      <PageHeader title="Инструменты ассистента" subtitle="RPA whitelist · шаблоны · SQL" />
      <Row gap={6}>
        {tabs.map((item) => (
          <Button
            key={item.id}
            variant={tab === item.id ? "primary" : "secondary"}
            size="sm"
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </Button>
        ))}
      </Row>
      <Table headers={headers} rows={rows} striped />
      <Callout variant="info">{calloutByTab[tab]}</Callout>
      <Button variant="secondary" size="sm">
        {addLabel}
      </Button>
    </Stack>
  );
}

const SCENARIO_TABS = [
  { id: "map" as const, label: "Карта" },
  { id: "prompts" as const, label: "Промпты" },
  { id: "settings" as const, label: "Настройки" },
];

const SCENARIO_REGISTRY = [
  { id: "CC-SCR-001", title: "14-летний хочет открыть счёт", status: "Опубликован" },
  { id: "CC-SCR-002", title: "Счёт внуку, 6 лет", status: "Черновик" },
  { id: "CC-SCR-003", title: "Оплата телефоном (NFC)", status: "Опубликован" },
  { id: "CC-SCR-004", title: "Автокредит", status: "Опубликован" },
  { id: "CC-SCR-005", title: "Досрочное закрытие вклада", status: "Опубликован" },
  { id: "CC-SCR-006", title: "Арест на счёте клиента", status: "Черновик" },
  { id: "CC-SCR-007", title: "Проблема с SMS-подтверждением", status: "Опубликован" },
  { id: "CC-SCR-008", title: "Лимиты перевода по карте", status: "Опубликован" },
  { id: "CC-SCR-009", title: "Статус заявки по кредиту", status: "Черновик" },
  { id: "CC-SCR-010", title: "Эскалация на супервайзера", status: "Опубликован" },
];

function ScenarioEditorScreen({
  t,
  readOnly,
  onTest,
}: {
  t: CanvasHostTheme;
  readOnly: boolean;
  onTest: () => void;
}): JSX.Element {
  const [tab, setTab] = useCanvasState<"map" | "prompts" | "settings">("scr_tab", "map");
  const [selected, setSelected] = useCanvasState("scr_sel", "CC-SCR-002");
  const activeScenario = SCENARIO_REGISTRY.find((s) => s.id === selected);
  return (
    <Stack gap={12}>
      <PageHeader
        title="Редактор сценариев"
        badge="sufler_cc"
        subtitle="Редактор сценариев · embed Studio · реестр сценариев"
      />
      {readOnly && (
        <Callout variant="warning">Роль «Админ БЗ» — просмотр. Редактирование: «Админ сценариев / КЦ».</Callout>
      )}
      <Text variant="label">Реестр сценариев</Text>
      <Table
        headers={["Сценарий", "Статус"]}
        rows={SCENARIO_REGISTRY.map((s) => [
          s.id === selected ? `→ ${s.title}` : s.title,
          s.status,
        ])}
        striped
      />
      <Row gap={6}>
        <Button variant="secondary" size="sm">
          + Сценарий
        </Button>
        <Button variant="secondary" size="sm">
          Импорт сценариев
        </Button>
      </Row>
      <Divider />
      <Row gap={8} align="center">
        <H2 style={{ fontSize: 18, margin: 0 }}>
          {SCENARIO_REGISTRY.find((s) => s.id === selected)?.title}
        </H2>
        <Pill tone={activeScenario?.status === "Опубликован" ? "success" : "neutral"}>
          {activeScenario?.status ?? "Черновик"}
        </Pill>
      </Row>
      <Row gap={6}>
        {SCENARIO_TABS.map(({ id, label }) => (
          <Button
            key={id}
            variant={tab === id ? "primary" : "secondary"}
            size="sm"
            onClick={() => setTab(id)}
          >
            {label}
          </Button>
        ))}
        <Spacer />
        <Button variant="secondary" size="sm" onClick={onTest}>
          Тест →
        </Button>
        <Button variant="primary" size="sm" disabled={readOnly}>
          Опубликовать
        </Button>
      </Row>
      <div style={shell(t, { padding: 16, minHeight: 220 })}>
        {tab === "prompts" ? (
          <Stack gap={8}>
            <Text variant="label">System prompt сценария</Text>
            <TextArea value="Ты суфлёр КЦ. Веди диалог по карте сценария…" onChange={() => {}} rows={3} />
            <Text variant="label">Snippets</Text>
            <Text>Эскалация оператору · Низкая релевантность</Text>
          </Stack>
        ) : tab === "settings" ? (
          <Row gap={8}>
            <Pill tone="success">Телефония</Pill>
            <Pill tone="success">Чат</Pill>
            <Pill tone="neutral">Черновик</Pill>
          </Row>
        ) : (
          <Stack gap={8}>
            <Text variant="label">Визуальная карта сценария</Text>
            <Row gap={8}>
              {["Возраст?", "Документ?", "Тип счёта", "Отделение"].map((n) => (
                <div key={n} style={shell(t, { padding: 8, fontSize: 12 })}>
                  {n}
                </div>
              ))}
            </Row>
          </Stack>
        )}
      </div>
    </Stack>
  );
}

function ScenarioTestScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  return (
    <Stack gap={12}>
      <PageHeader title="Тест сценария" subtitle="Sandbox · тестовый прогон диалога" />
      <Row gap={12} align="stretch">
        <div style={{ ...shell(t, { flex: 1, minWidth: 0, padding: 12 }) }}>
          <Text variant="label">Sandbox диалог</Text>
          <Stack gap={6} style={{ marginTop: 8 }}>
            <Text>Клиент: Хочу открыть счёт внуку, ему 6 лет</Text>
            <Text variant="muted">Бот: Уточните, вы законный представитель?</Text>
            <TextInput value="Нет, я бабушка" onChange={() => {}} />
          </Stack>
        </div>
        <div style={{ ...shell(t, { flex: 1, minWidth: 0, padding: 12 }) }}>
          <Text variant="label">Отчёт test-run</Text>
          <Callout variant="success">10 шагов OK</Callout>
          <Callout variant="warning">Узел 7: ошибка ветвления</Callout>
          <Callout variant="error">Узел 4: формулировка промпта</Callout>
          <Button variant="secondary" size="sm" style={{ marginTop: 8 }}>
            Экспорт PDF
          </Button>
        </div>
      </Row>
    </Stack>
  );
}

function SuflerPoliciesScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  return (
    <Stack gap={16}>
      <PageHeader title="Политики суфлёра" subtitle="Пороги тел/чат · max карточек подсказок" />
      <Grid columns={2} gap={12}>
        <Stack gap={8}>
          <Text variant="label">Порог % подсказки · телефония</Text>
          <TextInput value="72%" onChange={() => {}} />
          <Text variant="label">Порог % · чат</Text>
          <TextInput value="68%" onChange={() => {}} />
        </Stack>
        <Stack gap={8}>
          <Text variant="label">Max карточек</Text>
          <TextInput value="2" onChange={() => {}} />
          <Text variant="label">Режим «Услуга» по умолчанию</Text>
          <Toggle checked onChange={() => {}} label="Включён" />
        </Stack>
      </Grid>
      <Callout variant="info">
        Шаблоны ответов оператора → Online Chat admin (read-only ссылка)
      </Callout>
    </Stack>
  );
}

type AssistantAnalyticsMainTab = "monitoring" | "reporting";
type AssistantAnalyticsPanel = "reports" | "builder";
type AssistantReportViewMode = "table" | "pie" | "bar";

type AssistantReportId = "relevance" | "usefulness" | "errors" | "topics" | "hallucinations";

const ASSISTANT_REPORT_TYPES: {
  id: AssistantReportId;
  label: string;
  defaultView: AssistantReportViewMode;
  group: string;
}[] = [
  { id: "relevance", label: "Релевантность по типам запросов", defaultView: "bar", group: "Качество ответов" },
  { id: "usefulness", label: "Полезность: воспользовался / нет / неполный", defaultView: "pie", group: "Качество ответов" },
  { id: "errors", label: "Ошибочные ответы", defaultView: "table", group: "Качество ответов" },
  { id: "topics", label: "Тематики обращений", defaultView: "bar", group: "Тематики" },
  { id: "hallucinations", label: "Галлюцинации (доступ ИБ)", defaultView: "table", group: "ИБ" },
];

const ASSISTANT_FILTER_FIELD_CATALOG = [
  { value: "period", label: "Период" },
  { value: "department", label: "Подразделение" },
  { value: "request_type", label: "Тип запроса" },
  { value: "kb_scope", label: "База знаний" },
  { value: "feedback", label: "Оценка ответа" },
  { value: "user_role", label: "Роль пользователя" },
  { value: "prompt_type", label: "Тип промпта" },
];

const ASSISTANT_METRIC_FIELD_CATALOG = [
  { value: "requests_total", label: "Запросов всего" },
  { value: "avg_relevance", label: "Ср. релевантность" },
  { value: "feedback_used_pct", label: "% «воспользовался»" },
  { value: "p95_latency", label: "p95 ответа (сек)" },
  { value: "error_rate", label: "% ошибочных ответов" },
  { value: "hallucination_rate", label: "% галлюцинаций" },
  { value: "kb_hit_rate", label: "% попаданий в KB" },
  { value: "qu_clarify_rate", label: "% уточняющих вопросов" },
];

type AssistantBuilderFilterRow = { id: string; field: string; operator: string; value: string };
type AssistantBuilderMetricRow = { id: string; metric: string; aggregate: string };

function assistantNextRowId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
}

function getAssistantReportPreview(
  reportId: AssistantReportId,
  view: AssistantReportViewMode,
): {
  title: string;
  caption: string;
  table?: { headers: string[]; rows: string[][] };
  pie?: { label: string; value: number; tone?: "success" | "warning" | "danger" | "info" | "neutral" }[];
  bar?: { categories: string[]; series: { name: string; data: number[]; tone?: "success" | "warning" | "danger" | "info" | "neutral" }[]; valueSuffix?: string };
} {
  const meta = ASSISTANT_REPORT_TYPES.find((item) => item.id === reportId);

  if (reportId === "usefulness" || (view === "pie" && reportId !== "errors" && reportId !== "hallucinations")) {
    const pieData =
      reportId === "topics"
        ? [
            { label: "Отпуск и HR", value: 428 },
            { label: "Вклады и счета", value: 386 },
            { label: "ДБО / моб. банк", value: 294 },
            { label: "Кредиты", value: 218 },
            { label: "IT / доступы", value: 142 },
          ]
        : [
            { label: "Воспользовался", value: 412, tone: "success" as const },
            { label: "Не воспользовался", value: 118, tone: "warning" as const },
            { label: "Неполный ответ", value: 54, tone: "warning" as const },
            { label: "Без оценки", value: 28, tone: "neutral" as const },
          ];
    return {
      title: meta?.label ?? "Распределение",
      caption: "",
      pie: view === "pie" ? pieData : undefined,
      bar:
        view === "bar"
          ? {
              categories: pieData.map((item) => item.label),
              series: [{ name: "Количество", data: pieData.map((item) => item.value) }],
            }
          : undefined,
      table:
        view === "table"
          ? {
              headers: ["Категория", "Кол-во", "Доля"],
              rows: pieData.map((item) => {
                const total = pieData.reduce((sum, row) => sum + row.value, 0);
                return [item.label, String(item.value), `${Math.round((item.value / total) * 100)}%`];
              }),
            }
          : undefined,
    };
  }

  if (view === "bar" || reportId === "relevance" || reportId === "topics") {
    const categories =
      reportId === "topics"
        ? ["Отпуск и HR", "Вклады", "ДБО", "Кредиты", "IT"]
        : ["KB lookup", "RPA", "QU", "Перевод", "Summary"];
    const bar =
      reportId === "relevance"
        ? {
            categories,
            valueSuffix: "%",
            series: [
              { name: "Ср. релевантность", data: [87, 79, 72, 91, 84] },
              { name: "p95", data: [94, 88, 81, 96, 90] },
            ],
          }
        : {
            categories,
            series: [{ name: "Запросов", data: [428, 386, 294, 218, 142] }],
          };
    return {
      title: meta?.label ?? "Динамика",
      caption: "",
      bar,
      table: {
        headers: ["Категория", ...bar.series.map((s) => s.name)],
        rows: categories.map((cat, index) => [cat, ...bar.series.map((s) => String(s.data[index]))]),
      },
    };
  }

  const tableByReport: Record<AssistantReportId, { headers: string[]; rows: string[][] }> = {
    relevance: {
      headers: ["Тип запроса", "Запросов", "Ср. релевантность", "p95"],
      rows: [
        ["Справочный (KB)", "1 842", "87%", "94%"],
        ["RPA / инструмент", "312", "79%", "88%"],
        ["Уточняющий (QU)", "156", "72%", "81%"],
        ["Перевод", "98", "91%", "96%"],
        ["Summary документа", "64", "84%", "90%"],
      ],
    },
    usefulness: {
      headers: ["Оценка", "Доля", "За период", "Δ к прошл. мес."],
      rows: [
        ["Воспользовался", "68%", "+412", "+4 п.п."],
        ["Не воспользовался", "19%", "+118", "−2 п.п."],
        ["Неполный ответ", "9%", "+54", "+1 п.п."],
        ["Без оценки", "4%", "+28", "—"],
      ],
    },
    errors: {
      headers: ["Дата", "Запрос", "Причина", "KB / источник"],
      rows: [
        ["27.06", "Лимит перевода за границу", "Нет документа в KB", "HR policies"],
        ["26.06", "Ставка по вкладу «Премия»", "Устаревший фрагмент", "Продукты"],
        ["25.06", "Срок рассмотрения ипотеки", "Низкая релевантность (<65%)", "Ипотека"],
        ["24.06", "Формат SWIFT-реквизитов", "Галлюцинация · отклонено", "—"],
      ],
    },
    topics: {
      headers: ["Тема", "Запросов", "Ср. релевантность", "Тренд"],
      rows: [
        ["Отпуск и HR", "428", "89%", "↑"],
        ["Вклады и счета", "386", "86%", "→"],
        ["ДБО / моб. банк", "294", "82%", "↑"],
        ["Кредиты", "218", "78%", "↓"],
        ["IT / доступы", "142", "91%", "→"],
      ],
    },
    hallucinations: {
      headers: ["Дата", "Запрос", "Фрагмент ответа", "Статус"],
      rows: [
        ["28.06", "Комиссия за SWIFT", "«0.3% от суммы…»", "Заблокировано guardrail"],
        ["26.06", "Срок вклада 18 мес.", "«до 2027 года»", "Исправлено оператором"],
        ["22.06", "Льгота по НДФЛ", "Выдуманная ставка", "Отклонено · аудит"],
      ],
    },
  };

  const table = tableByReport[reportId];
  return {
    title: meta?.label ?? "Отчёт",
    caption: "",
    table,
  };
}

function AssistantAnalyticsScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  const [mainTab, setMainTab] = useCanvasState<AssistantAnalyticsMainTab>("assistant_analytics_main", "reporting");
  const [panel, setPanel] = useCanvasState<AssistantAnalyticsPanel>("assistant_analytics_panel", "reports");
  const [reportId, setReportId] = useCanvasState<AssistantReportId>("assistant_report_id", "relevance");
  const [viewMode, setViewMode] = useCanvasState<AssistantReportViewMode>("assistant_report_view", "bar");
  const [period, setPeriod] = useCanvasState("assistant_report_period", "2026-06-01 — 2026-06-30");
  const [department, setDepartment] = useCanvasState("assistant_report_dept", "all");
  const [requestType, setRequestType] = useCanvasState("assistant_report_req_type", "all");
  const [kbScope, setKbScope] = useCanvasState("assistant_report_kb", "all");
  const [feedbackFilter, setFeedbackFilter] = useCanvasState("assistant_report_feedback", "all");
  const [templateName, setTemplateName] = useCanvasState("assistant_report_template", "Сводка ассистента — месяц");
  const [builderFilters, setBuilderFilters] = useCanvasState<AssistantBuilderFilterRow[]>("assistant_builder_filters", [
    { id: "f1", field: "period", operator: "between", value: "2026-06-01 — 2026-06-30" },
    { id: "f2", field: "department", operator: "in", value: "HR, IT" },
  ]);
  const [builderMetrics, setBuilderMetrics] = useCanvasState<AssistantBuilderMetricRow[]>("assistant_builder_metrics", [
    { id: "m1", metric: "requests_total", aggregate: "count" },
    { id: "m2", metric: "avg_relevance", aggregate: "avg" },
    { id: "m3", metric: "feedback_used_pct", aggregate: "avg" },
  ]);
  const [scheduleEnabled, setScheduleEnabled] = useCanvasState("assistant_report_schedule", true);
  const [filtersOpen, setFiltersOpen] = useCanvasState("assistant_report_filters_open", false);
  const [builderFiltersOpen, setBuilderFiltersOpen] = useCanvasState("assistant_builder_filters_open", false);

  const deptLabels: Record<string, string> = {
    all: "все подразделения",
    hr: "HR",
    it: "IT",
    cc: "Контакт-центр",
    legal: "Юридический",
  };
  const reqTypeLabels: Record<string, string> = {
    all: "все типы",
    kb: "KB lookup",
    rpa: "RPA",
    qu: "QU",
    translate: "Перевод",
  };
  const filtersSummary = `${period} · ${deptLabels[department] ?? department} · ${reqTypeLabels[requestType] ?? requestType}`;

  const selectedReport = ASSISTANT_REPORT_TYPES.find((r) => r.id === reportId) ?? ASSISTANT_REPORT_TYPES[0];
  const preview = getAssistantReportPreview(reportId, viewMode);

  const addFilter = () => {
    setBuilderFilters([
      ...builderFilters,
      { id: assistantNextRowId("filter"), field: "request_type", operator: "eq", value: "" },
    ]);
  };
  const removeFilter = (id: string) => {
    setBuilderFilters(builderFilters.filter((row) => row.id !== id));
  };
  const updateFilter = (id: string, patch: Partial<AssistantBuilderFilterRow>) => {
    setBuilderFilters(builderFilters.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };
  const addMetric = () => {
    setBuilderMetrics([
      ...builderMetrics,
      { id: assistantNextRowId("metric"), metric: "error_rate", aggregate: "avg" },
    ]);
  };
  const removeMetric = (id: string) => {
    setBuilderMetrics(builderMetrics.filter((row) => row.id !== id));
  };
  const updateMetric = (id: string, patch: Partial<AssistantBuilderMetricRow>) => {
    setBuilderMetrics(builderMetrics.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };

  return (
    <Stack gap={16}>
      <PageHeader
        title="Аналитика ассистента"
        subtitle="Релевантность, полезность, тематики · для аналитика ИИ-ассистента"
      />

      <Row gap={8} style={{ flexWrap: "wrap" }}>
        <Pill active={mainTab === "monitoring"} onClick={() => setMainTab("monitoring")}>
          Мониторинг
        </Pill>
        <Pill active={mainTab === "reporting"} onClick={() => setMainTab("reporting")}>
          Отчётность
        </Pill>
      </Row>

      {mainTab === "monitoring" ? (
        <>
          <Row gap={12}>
            <Stat label="Запросов / ч" value="342" tone="neutral" />
            <Stat label="p95 ответа" value="1.8 сек" tone="success" />
            <Stat label="Ср. релевантность" value="84%" tone="success" />
            <Stat label="Ошибки LLM" value="0.4%" tone="warning" />
            <Stat label="Галлюцинации" value="1.2%" tone="success" />
          </Row>
          <Callout variant="info">
            Доля галлюцинаций в норме (порог 3%). Данные обновляются в реальном времени.
          </Callout>
          <Card>
            <CardHeader>Последние запросы</CardHeader>
            <CardBody>
              <Table
                headers={["Время", "Пользователь", "Запрос", "Релевантность", "Оценка"]}
                rows={[
                  ["09:14", "Иванова М.", "Как оформить отпуск?", "92%", "✓"],
                  ["09:12", "Петров С.", "Лимит перевода SWIFT", "68%", "неполный"],
                  ["09:08", "Козлова А.", "Регламент командировок", "88%", "✓"],
                  ["09:05", "Сидоров К.", "Справка 2-НДФЛ через RPA", "81%", "✓"],
                  ["09:01", "Новикова Е.", "Ставка вклада «Премия»", "61%", "—"],
                ]}
                striped
              />
            </CardBody>
          </Card>
          <Card>
            <CardHeader>Отклонения за последний час</CardHeader>
            <CardBody>
              <Table
                headers={["Время", "Тип", "Описание", "Действие"]}
                rows={[
                  ["08:55", "Низкая релевантность", "Запрос «Ставка вклада Премия» — 61%", "→ Отчёт ошибок"],
                  ["08:41", "p95 > порога", "Пик нагрузки · p95 2.4 сек", "Авто-алерт отправлен"],
                ]}
                striped
              />
            </CardBody>
          </Card>
        </>
      ) : (
        <Stack gap={16}>
          <Row style={{ gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
            <Pill active={panel === "reports"} onClick={() => setPanel("reports")}>
              Готовые отчёты
            </Pill>
            <Pill active={panel === "builder"} onClick={() => setPanel("builder")}>
              Конструктор
            </Pill>
          </Row>

          {panel === "reports" ? (
            <>
              <Card collapsible open={filtersOpen} onOpenChange={setFiltersOpen}>
                <CardHeader
                  trailing={
                    <Row gap={8} align="center">
                      {!filtersOpen ? (
                        <Text style={{ fontSize: 11, color: t.text.secondary, maxWidth: 280 }}>{filtersSummary}</Text>
                      ) : null}
                    </Row>
                  }
                >
                  Фильтры отчёта
                </CardHeader>
                <CardBody>
                  <Grid columns={2} gap={12}>
                    <Stack gap={4}>
                      <Text style={{ fontSize: 12 }}>Тип отчёта</Text>
                      <Select
                        value={reportId}
                        onChange={(value) => {
                          const next = value as AssistantReportId;
                          setReportId(next);
                          const meta = ASSISTANT_REPORT_TYPES.find((item) => item.id === next);
                          if (meta) setViewMode(meta.defaultView);
                        }}
                        options={ASSISTANT_REPORT_TYPES.map((item) => ({
                          value: item.id,
                          label: item.label,
                        }))}
                      />
                    </Stack>
                    <Stack gap={4}>
                      <Text style={{ fontSize: 12 }}>Период</Text>
                      <TextInput value={period} onChange={setPeriod} />
                    </Stack>
                    <Stack gap={4}>
                      <Text style={{ fontSize: 12 }}>Подразделение</Text>
                      <Select
                        value={department}
                        onChange={setDepartment}
                        options={[
                          { value: "all", label: "Все подразделения" },
                          { value: "hr", label: "HR" },
                          { value: "it", label: "IT" },
                          { value: "cc", label: "Контакт-центр" },
                          { value: "legal", label: "Юридический" },
                        ]}
                      />
                    </Stack>
                    <Stack gap={4}>
                      <Text style={{ fontSize: 12 }}>Тип запроса</Text>
                      <Select
                        value={requestType}
                        onChange={setRequestType}
                        options={[
                          { value: "all", label: "Все типы" },
                          { value: "kb", label: "KB lookup" },
                          { value: "rpa", label: "RPA / инструмент" },
                          { value: "qu", label: "Уточняющий (QU)" },
                          { value: "translate", label: "Перевод" },
                        ]}
                      />
                    </Stack>
                    <Stack gap={4}>
                      <Text style={{ fontSize: 12 }}>База знаний</Text>
                      <Select
                        value={kbScope}
                        onChange={setKbScope}
                        options={[
                          { value: "all", label: "Все БЗ" },
                          { value: "hr", label: "HR policies" },
                          { value: "it", label: "IT runbooks" },
                          { value: "products", label: "Корп. регламенты" },
                        ]}
                      />
                    </Stack>
                    <Stack gap={4}>
                      <Text style={{ fontSize: 12 }}>Оценка ответа</Text>
                      <Select
                        value={feedbackFilter}
                        onChange={setFeedbackFilter}
                        options={[
                          { value: "all", label: "Все оценки" },
                          { value: "used", label: "Воспользовался" },
                          { value: "not_used", label: "Не воспользовался" },
                          { value: "partial", label: "Неполный ответ" },
                          { value: "none", label: "Без оценки" },
                        ]}
                      />
                    </Stack>
                  </Grid>
                </CardBody>
              </Card>

              <Row style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <Text style={{ fontSize: 12, color: t.text.secondary }}>Представление:</Text>
                <Pill active={viewMode === "table"} onClick={() => setViewMode("table")}>
                  Таблица
                </Pill>
                <Pill active={viewMode === "pie"} onClick={() => setViewMode("pie")}>
                  Круговая
                </Pill>
                <Pill active={viewMode === "bar"} onClick={() => setViewMode("bar")}>
                  Столбчатая
                </Pill>
              </Row>

              <Row style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                {!filtersOpen ? (
                  <Text style={{ fontSize: 12, color: t.text.secondary }}>
                    {selectedReport.label} · {filtersSummary}
                  </Text>
                ) : null}
                <Spacer />
                {!filtersOpen ? (
                  <Button variant="secondary" onClick={() => setFiltersOpen(true)}>
                    Настроить фильтры
                  </Button>
                ) : null}
                <Button variant="secondary">Сформировать</Button>
                <Button variant="primary">Экспорт xlsx</Button>
                <Button variant="secondary">Экспорт pdf</Button>
              </Row>

              <Card>
                <CardHeader trailing={<Pill size="sm">{selectedReport.group}</Pill>}>{preview.title}</CardHeader>
                <CardBody>
                  {viewMode === "table" && preview.table ? (
                    <Table headers={preview.table.headers} rows={preview.table.rows} striped columnAlign={["left", "right", "right", "left"]} />
                  ) : null}
                  {viewMode === "pie" && preview.pie ? (
                    <Row style={{ justifyContent: "center", padding: "8px 0" }}>
                      <PieChart data={preview.pie} size={240} donut />
                    </Row>
                  ) : null}
                  {viewMode === "bar" && preview.bar ? (
                    <BarChart
                      categories={preview.bar.categories}
                      series={preview.bar.series}
                      height={260}
                      valueSuffix={preview.bar.valueSuffix}
                    />
                  ) : null}
                  {preview.caption ? (
                    <Text style={{ fontSize: 11, color: t.text.tertiary, marginTop: 12 }}>{preview.caption}</Text>
                  ) : null}
                </CardBody>
              </Card>
            </>
          ) : (
            <Grid columns={2} gap={16} style={{ alignItems: "start" }}>
              <Stack gap={16}>
                <Card collapsible open={builderFiltersOpen} onOpenChange={setBuilderFiltersOpen}>
                  <CardHeader
                    trailing={
                      !builderFiltersOpen ? (
                        <Text style={{ fontSize: 11, color: t.text.secondary }}>
                          {builderFilters.length} фильтр(ов)
                        </Text>
                      ) : null
                    }
                  >
                    Динамические фильтры
                  </CardHeader>
                  <CardBody>
                    <Stack gap={10}>
                      {builderFilters.map((row) => (
                        <Row key={row.id} style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                          <Select
                            value={row.field}
                            onChange={(value) => updateFilter(row.id, { field: value })}
                            options={ASSISTANT_FILTER_FIELD_CATALOG.map((item) => ({ value: item.value, label: item.label }))}
                          />
                          <Select
                            value={row.operator}
                            onChange={(value) => updateFilter(row.id, { operator: value })}
                            options={[
                              { value: "eq", label: "=" },
                              { value: "neq", label: "≠" },
                              { value: "in", label: "в списке" },
                              { value: "between", label: "между" },
                              { value: "gt", label: ">" },
                            ]}
                          />
                          <TextInput
                            value={row.value}
                            onChange={(value) => updateFilter(row.id, { value })}
                            placeholder="Значение…"
                            style={{ flex: "1 1 140px", minWidth: 140 }}
                          />
                          <Button variant="ghost" size="sm" onClick={() => removeFilter(row.id)}>
                            Удалить
                          </Button>
                        </Row>
                      ))}
                      <Button variant="ghost" size="sm" onClick={addFilter} style={{ alignSelf: "flex-start" }}>
                        + Фильтр
                      </Button>
                    </Stack>
                  </CardBody>
                </Card>

                <Card>
                  <CardHeader trailing={<Button variant="ghost" size="sm" onClick={addMetric}>+ Поле</Button>}>
                    Динамические показатели
                  </CardHeader>
                  <CardBody>
                    <Stack gap={10}>
                      {builderMetrics.map((row) => (
                        <Row key={row.id} style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                          <Select
                            value={row.metric}
                            onChange={(value) => updateMetric(row.id, { metric: value })}
                            options={ASSISTANT_METRIC_FIELD_CATALOG.map((item) => ({ value: item.value, label: item.label }))}
                          />
                          <Select
                            value={row.aggregate}
                            onChange={(value) => updateMetric(row.id, { aggregate: value })}
                            options={[
                              { value: "count", label: "COUNT" },
                              { value: "sum", label: "SUM" },
                              { value: "avg", label: "AVG" },
                              { value: "p95", label: "P95" },
                              { value: "min", label: "MIN" },
                              { value: "max", label: "MAX" },
                            ]}
                          />
                          <Button variant="ghost" size="sm" onClick={() => removeMetric(row.id)}>
                            Удалить
                          </Button>
                        </Row>
                      ))}
                    </Stack>
                  </CardBody>
                </Card>

                <Card>
                  <CardHeader>Сохранение шаблона</CardHeader>
                  <CardBody>
                    <Stack gap={10}>
                      <TextInput value={templateName} onChange={setTemplateName} placeholder="Название шаблона…" />
                      <Row style={{ gap: 8, alignItems: "center" }}>
                        <Toggle checked={scheduleEnabled} onChange={setScheduleEnabled} />
                        <Text style={{ fontSize: 13 }}>Периодическая рассылка (день / неделя / месяц)</Text>
                      </Row>
                      {scheduleEnabled ? (
                        <Select
                          value="monthly"
                          onChange={() => undefined}
                          options={[
                            { value: "daily", label: "Ежедневно — 08:00" },
                            { value: "weekly", label: "Еженедельно — пн 09:00" },
                            { value: "monthly", label: "Ежемесячно — 1-е число" },
                          ]}
                        />
                      ) : null}
                      <Row gap={8}>
                        <Button variant="primary">Сохранить шаблон</Button>
                        <Button variant="secondary">Предпросмотр</Button>
                      </Row>
                    </Stack>
                  </CardBody>
                </Card>
              </Stack>

              <Card style={{ borderColor: t.stroke.secondary }}>
                <CardHeader>Предпросмотр конструктора</CardHeader>
                <CardBody>
                  <Stack gap={12}>
                    <Row style={{ gap: 8, flexWrap: "wrap" }}>
                      {builderMetrics.slice(0, 4).map((row, idx) => {
                        const label =
                          ASSISTANT_METRIC_FIELD_CATALOG.find((item) => item.value === row.metric)?.label ?? row.metric;
                        const demoValues = ["2 472", "84%", "68%", "1.8 сек"];
                        return (
                          <Stat
                            key={row.id}
                            label={label}
                            value={demoValues[idx] ?? "—"}
                            tone={idx === 1 ? "success" : "info"}
                          />
                        );
                      })}
                    </Row>
                    <BarChart
                      categories={["KB lookup", "RPA", "QU", "Перевод", "Summary"]}
                      series={[
                        { name: "Запросов", data: [1842, 312, 156, 98, 64] },
                        { name: "Ср. релевантность %", data: [87, 79, 72, 91, 84], tone: "success" },
                      ]}
                      height={220}
                      valueSuffix={undefined}
                    />
                    <PieChart
                      data={[
                        { label: "Воспользовался", value: 68, tone: "success" },
                        { label: "Не воспользовался", value: 19, tone: "warning" },
                        { label: "Неполный", value: 9, tone: "warning" },
                        { label: "Без оценки", value: 4, tone: "neutral" },
                      ]}
                      size={180}
                      donut
                    />
                    <Table
                      headers={["Фильтр", "Условие", "Значение"]}
                      rows={builderFilters.map((row) => [
                        ASSISTANT_FILTER_FIELD_CATALOG.find((item) => item.value === row.field)?.label ?? row.field,
                        row.operator,
                        row.value || "—",
                      ])}
                      striped
                    />
                    <Row style={{ gap: 8 }}>
                      <Button variant="primary">Экспорт xlsx</Button>
                      <Button variant="secondary">Экспорт pdf</Button>
                    </Row>
                  </Stack>
                </CardBody>
              </Card>
            </Grid>
          )}
        </Stack>
      )}
    </Stack>
  );
}

type ExternalSystemId = "bitrix" | "chat" | "oktell";
type ChatAdminTab = "queues" | "bots" | "skills";

const EXTERNAL_SYSTEMS: { id: ExternalSystemId; title: string; status: string }[] = [
  { id: "bitrix", title: "1С-Битрикс · СУЗ", status: "Webhook OK · 2 мин назад" },
  { id: "chat", title: "Online Chat admin", status: "Очереди · боты · skill-группы" },
  { id: "oktell", title: "Oktell / ПТК", status: "WS подключён · read-only" },
];

function ExternalBackBar({ t, onBack }: { t: CanvasHostTheme; onBack: () => void }): JSX.Element {
  return (
    <Button variant="ghost" size="sm" onClick={onBack} style={{ alignSelf: "flex-start", marginBottom: 4 }}>
      ← Внешние системы
    </Button>
  );
}

function BitrixSuzDetail({ t, onBack }: { t: CanvasHostTheme; onBack: () => void }): JSX.Element {
  return (
    <Stack gap={16}>
      <ExternalBackBar t={t} onBack={onBack} />
      <PageHeader title="1С-Битрикс · СУЗ" subtitle="Интеграция базы знаний · webhook и индексация" />
      <Row gap={12}>
        <Stat label="Webhook" value="OK" tone="success" />
        <Stat label="Последняя синхронизация" value="2 мин" tone="neutral" />
        <Stat label="Документов в индексе" value="1 240" tone="neutral" />
        <Stat label="Ошибок за 24 ч" value="0" tone="success" />
      </Row>
      <Card>
        <CardHeader>Подключение</CardHeader>
        <CardBody>
          <Stack gap={8}>
            <Row gap={8} align="center">
              <Text style={{ width: 160 }}>Endpoint</Text>
              <TextInput value="https://suz.belarusbank.by/api/kb/webhook" onChange={() => {}} style={{ flex: 1 }} />
              <Pill tone="success">Активен</Pill>
            </Row>
            <Row gap={8} align="center">
              <Text style={{ width: 160 }}>Secret rotated</Text>
              <Text>15.06.2026 · Петрова А.</Text>
            </Row>
            <Row gap={8} align="center">
              <Text style={{ width: 160 }}>Scope AD</Text>
              <Text>BB_KB_*, BB_HR, BB_CC_*</Text>
            </Row>
          </Stack>
        </CardBody>
      </Card>
      <Card>
        <CardHeader>Последние события webhook</CardHeader>
        <CardBody>
          <Table
            headers={["Время", "Событие", "Документ", "Статус"]}
            rows={[
              ["28.06 09:12", "document.updated", "Положение об отпусках.pdf", "OK"],
              ["28.06 08:45", "document.created", "Регламент ДБО v3.docx", "OK"],
              ["27.06 17:30", "document.deleted", "Устаревший FAQ HR.pdf", "OK"],
              ["27.06 14:02", "index.rebuild", "—", "OK"],
              ["27.06 11:18", "document.updated", "Тарифы вкладов Q3.xlsx", "Retry → OK"],
            ]}
            striped
          />
        </CardBody>
      </Card>
      <Row gap={8}>
        <Button variant="primary" size="sm">
          Проверить webhook
        </Button>
        <Button variant="secondary" size="sm">
          Переиндексировать
        </Button>
      </Row>
    </Stack>
  );
}

function OnlineChatAdminDetail({ t, onBack }: { t: CanvasHostTheme; onBack: () => void }): JSX.Element {
  const [tab, setTab] = useCanvasState<ChatAdminTab>("external_chat_tab", "queues");

  const tabs: { id: ChatAdminTab; label: string }[] = [
    { id: "queues", label: "Очереди" },
    { id: "bots", label: "Боты" },
    { id: "skills", label: "Skill-группы" },
  ];

  const tableByTab: Record<ChatAdminTab, { headers: string[]; rows: string[][] }> = {
    queues: {
      headers: ["Очередь", "Канал", "Операторов", "SLA (с)", "Статус"],
      rows: [
        ["Общая · розница", "Виджет сайта", "24", "120", "Активна"],
        ["Премиум", "Виджет + моб. банк", "6", "60", "Активна"],
        ["Ипотека", "Виджет сайта", "8", "180", "Активна"],
        ["Офлайн-форма", "Форма без оператора", "—", "—", "Приём заявок"],
      ],
    },
    bots: {
      headers: ["Бот", "Сценарий", "Очередь", "Передача оператору", "Статус"],
      rows: [
        ["Приветствие", "Greeting v2", "Общая · розница", "После 2 сообщений", "Вкл"],
        ["FAQ-автоответ", "KB lookup", "Общая · розница", "При confidence < 65%", "Вкл"],
        ["Сбор контактов", "Lead capture", "Офлайн-форма", "—", "Вкл"],
        ["Ипотека · квалификация", "Mortgage pre-screen", "Ипотека", "После анкеты", "Черновик"],
      ],
    },
    skills: {
      headers: ["Skill-группа", "Операторов", "Очереди", "Тематики", "Статус"],
      rows: [
        ["Вклады и счета", "12", "Общая · розница", "Вклады, карты, переводы", "Активна"],
        ["Кредиты", "9", "Общая · розница, Ипотека", "Кредиты, ипотека", "Активна"],
        ["Премиум", "6", "Премиум", "VIP, private banking", "Активна"],
        ["Тех. поддержка ДБО", "7", "Общая · розница", "Моб. банк, SMS, NFC", "Активна"],
      ],
    },
  };

  const { headers, rows } = tableByTab[tab];

  return (
    <Stack gap={16}>
      <ExternalBackBar t={t} onBack={onBack} />
      <PageHeader title="Online Chat admin" subtitle="Очереди, боты и skill-группы · read-only просмотр" />
      <Row gap={12}>
        <Stat label="Активных очередей" value="4" tone="neutral" />
        <Stat label="Операторов онлайн" value="38" tone="success" />
        <Stat label="Диалогов в работе" value="17" tone="neutral" />
        <Stat label="Ботов" value="3" tone="success" />
      </Row>
      <Row gap={6}>
        {tabs.map((item) => (
          <Button
            key={item.id}
            variant={tab === item.id ? "primary" : "secondary"}
            size="sm"
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </Button>
        ))}
      </Row>
      <Table headers={headers} rows={rows} striped />
      <Callout variant="info">
        Редактирование очередей и skill-групп выполняется в отдельном модуле Online Chat admin. Здесь — только статус и
        ссылки для AI Hub.
      </Callout>
      <Button variant="secondary" size="sm">
        Открыть Online Chat admin →
      </Button>
    </Stack>
  );
}

function OktellPtkDetail({ t, onBack }: { t: CanvasHostTheme; onBack: () => void }): JSX.Element {
  return (
    <Stack gap={16}>
      <ExternalBackBar t={t} onBack={onBack} />
      <PageHeader title="Oktell / ПТК" subtitle="Телефония · WebSocket · read-only" />
      <Row gap={12}>
        <Stat label="WebSocket" value="Подключён" tone="success" />
        <Stat label="Heartbeat" value="12 с назад" tone="success" />
        <Stat label="Активных каналов" value="142" tone="neutral" />
        <Stat label="Операторов на линии" value="89" tone="neutral" />
      </Row>
      <Card>
        <CardHeader>Параметры подключения</CardHeader>
        <CardBody>
          <Stack gap={8}>
            <Row gap={8} align="center">
              <Text style={{ width: 160 }}>WS endpoint</Text>
              <TextInput value="wss://ptk-cc.belarusbank.local/oktell/events" onChange={() => {}} style={{ flex: 1 }} />
              <Pill tone="success">Live</Pill>
            </Row>
            <Row gap={8} align="center">
              <Text style={{ width: 160 }}>Режим</Text>
              <Text>read-only · события звонков и статусы операторов</Text>
            </Row>
            <Row gap={8} align="center">
              <Text style={{ width: 160 }}>Версия протокола</Text>
              <Text>Oktell WS v2.4</Text>
            </Row>
          </Stack>
        </CardBody>
      </Card>
      <Card>
        <CardHeader>Каналы и операторы</CardHeader>
        <CardBody>
          <Table
            headers={["Канал / группа", "Операторов", "На линии", "Сред. ожидание", "Статус"]}
            rows={[
              ["Розничный КЦ", "98", "62", "0:42", "OK"],
              ["Премиум-линия", "18", "11", "0:18", "OK"],
              ["Ипотечная линия", "26", "16", "1:05", "Нагрузка"],
              ["Ночная смена", "12", "—", "—", "Off-hours"],
            ]}
            striped
          />
        </CardBody>
      </Card>
      <Card>
        <CardHeader>Последние события WS</CardHeader>
        <CardBody>
          <Table
            headers={["Время", "Событие", "Оператор", "Детали"]}
            rows={[
              ["09:14:02", "call.started", "Иванова М.", "Входящий · +375 ** *** 42"],
              ["09:13:58", "operator.ready", "Петров С.", "Группа: Розничный КЦ"],
              ["09:13:41", "call.ended", "Козлова А.", "Длительность 4:12 · тема: вклад"],
              ["09:13:22", "asr.chunk", "Иванова М.", "Partial transcript · 128 симв."],
              ["09:12:55", "operator.busy", "Сидоров К.", "После перевода на супервайзера"],
            ]}
            striped
          />
        </CardBody>
      </Card>
      <Callout variant="info">
        Управление телефонией и сценариями суфлёра — в модуле «Суфлёр · телефония». Здесь только мониторинг
        подключения для AI Hub.
      </Callout>
    </Stack>
  );
}

function ExternalScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  const [detail, setDetail] = useCanvasState<ExternalSystemId | "">("external_detail", "");

  if (detail === "bitrix") {
    return <BitrixSuzDetail t={t} onBack={() => setDetail("")} />;
  }
  if (detail === "chat") {
    return <OnlineChatAdminDetail t={t} onBack={() => setDetail("")} />;
  }
  if (detail === "oktell") {
    return <OktellPtkDetail t={t} onBack={() => setDetail("")} />;
  }

  return (
    <Stack gap={12}>
      <PageHeader title="Внешние системы" subtitle="Без Studio — только ссылки и статусы" />
      <Grid columns={3} gap={10}>
        {EXTERNAL_SYSTEMS.map((c) => (
          <Card key={c.id}>
            <CardHeader title={c.title} />
            <CardBody>
              <Text variant="muted" style={{ fontSize: 12 }}>
                {c.status}
              </Text>
              <Button variant="secondary" size="sm" style={{ marginTop: 8 }} onClick={() => setDetail(c.id)}>
                Открыть →
              </Button>
            </CardBody>
          </Card>
        ))}
      </Grid>
    </Stack>
  );
}

function AuditScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  const departments: string[][] = [
    ["Контакт-центр · розница", "BB_CC_Retail", "Включён", "Включён", "142"],
    ["Премиум-линия", "BB_CC_Premium", "Включён", "Включён", "28"],
    ["HR · кадровые вопросы", "BB_HR", "Включён", "—", "56"],
    ["IT · внутренняя поддержка", "BB_IT", "Включён", "—", "19"],
    ["Ипотечный центр", "BB_Mortgage", "Включён", "Включён", "34"],
    ["Юридический отдел", "BB_Legal", "Только чтение", "—", "12"],
  ];

  const auditLog: string[][] = [
    ["28.06 09:14", "Петрова А.И.", "Промпты", "Опубликован промпт «Ответы по вкладам»"],
    ["27.06 16:42", "Сидоров К.В.", "Политики суфлёра", "Порог подсказки (чат): 72% → 68%"],
    ["27.06 11:05", "Козлова М.П.", "Базы знаний", "Добавлен документ «Положение об отпусках»"],
    ["26.06 15:30", "Иванов Д.С.", "Сценарии", "Сценарий «Досрочное закрытие вклада» → отдел «Розничный КЦ»"],
    ["26.06 10:18", "Петрова А.И.", "Подразделения", "Включён доступ к ассистенту для «Ипотечный центр»"],
    ["25.06 14:55", "Новикова Е.А.", "Параметры LLM", "Temperature: 0.3 → 0.2 (профиль КЦ)"],
    ["25.06 09:02", "Сидоров К.В.", "Типы документов", "Обновлена разметка полей для «passport_rf»"],
    ["24.06 17:40", "Козлова М.П.", "Инструменты", "Активирован сценарий RPA «Справка 2-НДФЛ»"],
  ];

  return (
    <Stack gap={16}>
      <PageHeader title="Подразделения и журнал" subtitle="Подразделения банка и журнал изменений настроек" />

      <Row gap={12}>
        <Stat label="Подразделений" value="6" tone="neutral" />
        <Stat label="С ассистентом" value="5" tone="success" />
        <Stat label="С суфлёром" value="3" tone="success" />
        <Stat label="Записей в журнале" value="248" tone="neutral" />
      </Row>

      <Card>
        <CardHeader>Подразделения</CardHeader>
        <CardBody>
          <Row gap={8} style={{ marginBottom: 12 }}>
            <TextInput placeholder="Поиск по названию или AD-группе…" style={{ flex: 1 }} />
            <Select
              value="all"
              onChange={() => {}}
              options={[
                { value: "all", label: "Все подразделения" },
                { value: "cc", label: "Контакт-центр" },
                { value: "back", label: "Бэк-офис" },
              ]}
            />
            <Button variant="secondary" size="sm">
              Экспорт
            </Button>
          </Row>
          <Table
            headers={["Подразделение", "AD-группа", "Ассистент", "Суфлёр", "Пользователей"]}
            rows={departments}
            striped
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>Журнал изменений</CardHeader>
        <CardBody>
          <Row gap={8} style={{ marginBottom: 12 }}>
            <Select
              value="7d"
              onChange={() => {}}
              options={[
                { value: "7d", label: "Последние 7 дней" },
                { value: "30d", label: "Последние 30 дней" },
                { value: "all", label: "Весь период" },
              ]}
            />
            <Select
              value="all"
              onChange={() => {}}
              options={[
                { value: "all", label: "Все разделы" },
                { value: "prompts", label: "Промпты" },
                { value: "kb", label: "Базы знаний" },
                { value: "scenarios", label: "Сценарии" },
              ]}
            />
            <Spacer />
            <Button variant="secondary" size="sm">
              Скачать журнал
            </Button>
          </Row>
          <Table
            headers={["Время", "Пользователь", "Раздел", "Действие"]}
            rows={auditLog}
            striped
          />
        </CardBody>
      </Card>
    </Stack>
  );
}

function DocTypesScreen({ t }: { t: CanvasHostTheme }): JSX.Element {
  return (
    <Stack gap={12}>
      <PageHeader title="Типы документов" subtitle="doc_type · разметка полей (bbox)" />
      <Table
        headers={["Тип документа", "Полей", "Auto-approve"]}
        rows={[
          ["Паспорт РФ", "12", "85%"],
          ["Счёт-фактура", "8", "90%"],
          ["Заявление на кредит", "15", "72%"],
        ]}
        striped
      />
    </Stack>
  );
}

function ScreenContent({
  screen,
  t,
  profile,
  role,
  onNavigate,
}: {
  screen: Screen;
  t: CanvasHostTheme;
  profile: "assistant" | "cc";
  role: AdminRole;
  onNavigate: (s: Screen, p?: "assistant" | "cc") => void;
}): JSX.Element {
  const ccEdit = role === "cc_admin";
  const ccReadOnly = !ccEdit && (role === "kb_admin" || role === "auditor");

  switch (screen) {
    case "audit":
      return <AuditScreen t={t} />;
    case "llm_config_assistant":
      return (
        <Stack gap={16}>
          <PageHeader title="Конфигурация LLM" badge="assistant_bank" subtitle="Landing dashboard · профиль ассистента" />
          <LayerDashboard t={t} layers={LAYERS_ASSISTANT} profile="assistant_bank" onNavigate={(s) => onNavigate(s)} />
        </Stack>
      );
    case "llm_config_cc":
      return (
        <Stack gap={16}>
          <PageHeader title="Конфигурация LLM КЦ" badge="sufler_cc" subtitle="Preset «строгий суфлёр»" />
          <LayerDashboard
            t={t}
            layers={LAYERS_CC}
            profile="sufler_cc"
            onNavigate={(s) => onNavigate(s, s === "model_params" ? "cc" : undefined)}
            onTest={() => onNavigate("scenario_test")}
          />
        </Stack>
      );
    case "model_params":
      return <ModelParamsScreen t={t} profile={profile} />;
    case "capabilities":
      return <CapabilitiesScreen t={t} />;
    case "prompts_assistant":
      return <PromptsAssistantScreen t={t} />;
    case "kb_admin":
      return <KbAdminScreen t={t} />;
    case "qu_admin":
      return <QuAdminScreen t={t} profile={profile} />;
    case "data_sources":
      return (
        <Stack gap={12}>
          <PageHeader title="Источники данных" subtitle="External Data Adapters · подключения к внешним системам" />
          <Table
            headers={["Источник", "Синхронизация", "Статус"]}
            rows={[
              ["CRM (read-only)", "Ежедневно", "OK"],
              ["СУЗ · база знаний", "По webhook", "OK"],
              ["HRIS · справочник сотрудников", "Каждые 4 ч", "OK"],
            ]}
            striped
          />
        </Stack>
      );
    case "assistant_tools":
      return <AssistantToolsScreen t={t} />;
    case "monitoring":
      return <AssistantAnalyticsScreen t={t} />;
    case "scenario_editor":
      return (
        <ScenarioEditorScreen t={t} readOnly={ccReadOnly} onTest={() => onNavigate("scenario_test")} />
      );
    case "scenario_test":
      return (
        <Stack gap={12}>
          {ccReadOnly && (
            <Callout variant="warning">Тест-run доступен для просмотра; публикация — только Админ сценариев.</Callout>
          )}
          <ScenarioTestScreen t={t} />
        </Stack>
      );
    case "scenario_bindings":
      return (
        <Stack gap={12}>
          <PageHeader title="Сценарии суфлёра" subtitle="Привязка отделов к сценариям · read-only список" />
          <Table
            headers={["Отдел", "Сценарий", "Статус"]}
            rows={[
              ["Розничный КЦ", "Счёт внуку, 6 лет", "Активен"],
              ["Премиум-линия", "Автокредит", "Активен"],
              ["Розничный КЦ", "Досрочное закрытие вклада", "Активен"],
              ["Ипотечный центр", "Статус заявки по кредиту", "Черновик"],
            ]}
            striped
          />
        </Stack>
      );
    case "sufler_policies":
      return <SuflerPoliciesScreen t={t} />;
    case "doc_types":
      return <DocTypesScreen t={t} />;
    case "doc_export":
      return (
        <Stack gap={12}>
          <PageHeader title="Экспорт документов" subtitle="JSON / XML / CSV · TTL хранения" />
          <Table
            headers={["Маршрут", "Формат", "TTL"]}
            rows={[
              ["ЭДО", "JSON", "30 дней"],
              ["Архив OCR", "XML", "90 дней"],
              ["Отчёты руководству", "CSV", "14 дней"],
            ]}
            striped
          />
        </Stack>
      );
    default:
      return <ExternalScreen t={t} />;
  }
}

export default function AiHubSettingsMockup(): JSX.Element {
  const t = useHostTheme();
  const [colorScheme, setColorScheme] = useCanvasState<ColorScheme>("aiHubSettingsColorScheme", "default");
  const [role, setRole] = useCanvasState<AdminRole>("adm_role", "kb_admin");
  const [screen, setScreen] = useCanvasState<Screen>("screen", "llm_config_assistant");
  const [profile, setProfile] = useCanvasState<"assistant" | "cc">("mdl_prof", "assistant");
  const [panelWidth, setPanelWidth] = useCanvasState("aiHubSettingsWidth", 1120);
  const [panelHeight, setPanelHeight] = useCanvasState("aiHubSettingsHeight", 560);
  const [settingsWindowOpen, setSettingsWindowOpen] = useCanvasState("aiHubSettingsWindowOpen", true);
  const [settingsMaximized, setSettingsMaximized] = useCanvasState("aiHubSettingsMaximized", false);
  const scheme = getSchemePalette(t, colorScheme);
  const schemeBorder = scheme.accentWeak;
  const boundedWidth = Math.max(900, Math.min(1400, settingsMaximized ? 1400 : panelWidth));
  const boundedHeight = Math.max(520, Math.min(900, settingsMaximized ? 900 : panelHeight));

  const visibleNav = NAV;
  const groups = [...new Set(visibleNav.map((n) => n.group))];
  const canAccess = (item: NavItem) => item.roles.includes(role);

  const handleNav = (item: NavItem) => {
    setScreen(item.id);
    if (item.profile) setProfile(item.profile);
  };

  const handleNavigate = (s: Screen, p?: "assistant" | "cc") => {
    setScreen(s);
    if (p) setProfile(p);
    else if (s === "model_params" && screen !== "llm_config_cc") setProfile("assistant");
  };

  const activeNavKey = (n: NavItem) =>
    n.id === screen && (n.profile === undefined || n.profile === profile);

  const setPanelSize = (nextWidth: number, nextHeight: number) => {
    setPanelWidth(Math.max(900, Math.min(1400, Math.round(nextWidth))));
    setPanelHeight(Math.max(520, Math.min(900, Math.round(nextHeight))));
  };
  const cycleColorScheme = () => {
    const currentIndex = COLOR_SCHEME_ORDER.indexOf(colorScheme);
    const nextIndex = (currentIndex + 1) % COLOR_SCHEME_ORDER.length;
    setColorScheme(COLOR_SCHEME_ORDER[nextIndex]);
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

  return (
    <Stack
      gap={12}
      style={{
        fontFamily: "system-ui, sans-serif",
        maxWidth: 1280,
        padding: 12,
        borderRadius: 10,
        border: `1px solid ${schemeBorder}`,
        background: scheme.panelBg,
      }}
    >
      <Row gap={12} align="center">
        <H2 style={{ color: scheme.accentControl }}>Центр настроек AI Hub</H2>
        <Pill tone="neutral">/ai-hub/admin</Pill>
        <Spacer />
        <Text variant="muted">Схема:</Text>
        <Row gap={6}>
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
        </Row>
        <Button variant="ghost" size="sm" onClick={cycleColorScheme} title="Сменить цветовую схему">
          ◐
        </Button>
        <Text variant="muted">Демо роль:</Text>
        <Select
          value={role}
          onChange={(v) => setRole(v as AdminRole)}
          options={(Object.keys(ROLES) as AdminRole[]).map((id) => ({ value: id, label: ROLES[id] }))}
        />
      </Row>
      <Callout variant="info" style={{ background: scheme.headerBg, borderColor: scheme.accent }}>
        Диалоговые сценарии КЦ — группа sidebar <strong>«СУФЛЁР / КЦ»</strong>: «Редактор сценариев», «Тест
        сценария», «Сценарии суфлёра». Не путать с RPA в «Инструменты ассистента» и skill-группами в Online Chat.
      </Callout>
      {!settingsWindowOpen ? (
        <Button variant="primary" onClick={() => setSettingsWindowOpen(true)}>
          Открыть окно «Центр настроек»
        </Button>
      ) : (
      <div
        style={{
          width: boundedWidth,
          maxWidth: "100%",
          height: boundedHeight,
          minHeight: 0,
          position: "relative",
          transition: "width 160ms ease, height 160ms ease",
          borderRadius: 8,
          overflow: "hidden",
          border: `1px solid ${schemeBorder}`,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            position: "relative",
            flexShrink: 0,
            padding: "10px 14px",
            paddingRight: WINDOW_CONTROLS_WIDTH,
            borderBottom: `1px solid ${t.stroke.tertiary}`,
            background: scheme.headerBg,
          }}
        >
          <Text weight="semibold">Центр настроек AI Hub</Text>
          <Text variant="muted" style={{ fontSize: 12 }}>
            /ai-hub/admin
          </Text>
          <WindowTitleBarControls
            theme={t}
            onMinimize={() => setSettingsWindowOpen(false)}
            onMaximize={() => setSettingsMaximized(!settingsMaximized)}
            onClose={() => setSettingsWindowOpen(false)}
            maximized={settingsMaximized}
          />
        </div>
        <Row gap={0} align="stretch" style={{ flex: 1, minHeight: 0 }}>
          <nav
            style={{
              width: 248,
              flexShrink: 0,
              padding: "10px 6px",
              overflowY: "auto",
              ...shell(t, {
                borderTopRightRadius: 0,
                borderBottomRightRadius: 0,
                background: scheme.headerBg,
                borderColor: schemeBorder,
              }),
            }}
          >
            <Stack gap={14}>
              {groups.map((group) => (
                <Stack key={group} gap={2}>
                  <Text variant="muted" style={{ fontSize: 10, fontWeight: 700, paddingLeft: 10, letterSpacing: 0.5 }}>
                    {group}
                  </Text>
                  {visibleNav
                    .filter((n) => n.group === group)
                    .map((item, idx) => (
                      <NavButton
                        key={`${item.id}-${item.profile ?? idx}`}
                        item={item}
                        active={activeNavKey(item)}
                        allowed={canAccess(item)}
                        onSelect={handleNav}
                        t={t}
                        scheme={scheme}
                      />
                    ))}
                </Stack>
              ))}
            </Stack>
          </nav>
          <main
            style={{
              flex: 1,
              minWidth: 0,
              padding: 20,
              overflowY: "auto",
              overflowX: "hidden",
              ...shell(t, {
                borderTopLeftRadius: 0,
                borderBottomLeftRadius: 0,
                borderColor: schemeBorder,
              }),
            }}
          >
            <ScreenContent screen={screen} t={t} profile={profile} role={role} onNavigate={handleNavigate} />
          </main>
        </Row>
        <div
          role="separator"
          aria-label="Resize settings window"
          onMouseDown={startResize}
          style={{
            position: "absolute",
            right: 0,
            bottom: 0,
            width: 18,
            height: 18,
            cursor: "nwse-resize",
            background: t.stroke.secondary,
            borderTop: `1px solid ${t.stroke.tertiary}`,
            borderLeft: `1px solid ${t.stroke.tertiary}`,
          }}
        />
      </div>
      )}
    </Stack>
  );
}
