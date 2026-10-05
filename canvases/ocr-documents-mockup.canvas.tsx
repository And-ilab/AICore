import {
  Button,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H2,
  Pill,
  Row,
  Select,
  Stack,
  Stat,
  Table,
  Text,
  TextInput,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";
import type { CanvasHostTheme } from "cursor/canvas";
import type { CSSProperties, JSX, ReactNode } from "react";

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

function MockupWindowFrame({
  t,
  scheme,
  title,
  subtitle,
  stateKey,
  children,
  minHeight = 480,
}: {
  t: CanvasHostTheme;
  scheme: SchemePalette;
  title: string;
  subtitle?: string;
  stateKey: string;
  children: ReactNode;
  minHeight?: number;
}): JSX.Element {
  const [maximized, setMaximized] = useCanvasState(`${stateKey}Maximized`, false);
  const [open, setOpen] = useCanvasState(`${stateKey}Open`, true);

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Открыть окно · {title}
      </Button>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: maximized ? minHeight + 80 : minHeight,
        ...panel(t, scheme, { overflow: "hidden", padding: 0 }),
      }}
    >
      <div
        style={{
          position: "relative",
          padding: "10px 16px",
          paddingRight: WINDOW_CONTROLS_WIDTH,
          borderBottom: `1px solid ${t.stroke.secondary}`,
          background: scheme.headerBg,
        }}
      >
        <Text weight="semibold">{title}</Text>
        {subtitle ? (
          <Text style={{ fontSize: 11, color: t.text.secondary, marginTop: 2 }}>{subtitle}</Text>
        ) : null}
        <WindowTitleBarControls
          theme={t}
          onMinimize={() => setOpen(false)}
          onMaximize={() => setMaximized(!maximized)}
          onClose={() => setOpen(false)}
          maximized={maximized}
        />
      </div>
      <div style={{ padding: 16, flex: 1 }}>{children}</div>
    </div>
  );
}

type Screen = "queue" | "upload" | "review";
type ColorScheme =
  | "default"
  | "belarusbank_classic"
  | "belarusbank_soft"
  | "belarusbank_emerald"
  | "belarusbank_night";
type SchemePalette = {
  accent: string;
  accentWeak: string;
  headerBg: string;
  panelBg: string;
};

const RADIUS = 8;

function getSchemePalette(scheme: ColorScheme): SchemePalette {
  if (scheme === "belarusbank_classic") {
    return {
      accent: "#0C4DA2",
      accentWeak: "#BFD3F3",
      headerBg: "linear-gradient(135deg, #EAF2FF 0%, #DCEAFF 55%, #F4F8FF 100%)",
      panelBg: "linear-gradient(180deg, #F7FAFF 0%, #EDF4FF 100%)",
    };
  }
  if (scheme === "belarusbank_soft") {
    return {
      accent: "#2E5AAC",
      accentWeak: "#C8D6EF",
      headerBg: "linear-gradient(135deg, #F3F7FF 0%, #EAF1FF 58%, #FDFEFF 100%)",
      panelBg: "linear-gradient(180deg, #FAFCFF 0%, #F1F6FF 100%)",
    };
  }
  if (scheme === "belarusbank_emerald") {
    return {
      accent: "#007A43",
      accentWeak: "#BEE8D5",
      headerBg: "linear-gradient(135deg, #EAF8F1 0%, #DCF3E8 58%, #F2FBF6 100%)",
      panelBg: "linear-gradient(180deg, #F5FCF8 0%, #EAF7F1 100%)",
    };
  }
  if (scheme === "belarusbank_night") {
    return {
      accent: "#0D5C86",
      accentWeak: "#C5D9E6",
      headerBg: "linear-gradient(135deg, #E8F1F8 0%, #D8E8F4 60%, #EFF6FB 100%)",
      panelBg: "linear-gradient(180deg, #F3F8FC 0%, #E6F1F8 100%)",
    };
  }
  return {
    accent: "#2E5AAC",
    accentWeak: "#D2D8E3",
    headerBg: "linear-gradient(135deg, #F1F3F6 0%, #E9EDF3 100%)",
    panelBg: "linear-gradient(180deg, #FAFBFC 0%, #F2F4F7 100%)",
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

const QUEUE_ROWS = [
  { file: "passport_ivanov.pdf", type: "passport", status: "На проверке", progress: 100, conf: "92%" },
  { file: "contract_2026-014.pdf", type: "contract", status: "OCR", progress: 64, conf: "—" },
  { file: "statement_mar.zip", type: "statement", status: "Очередь", progress: 0, conf: "—" },
  { file: "invoice_scan.tiff", type: "invoice", status: "Ошибка валидации", progress: 100, conf: "41%" },
];

const FIELDS = [
  { field: "ФИО", value: "Иванов Иван Иванович", conf: 0.96, tone: "success" as const },
  { field: "Серия паспорта", value: "MP", conf: 0.88, tone: "success" as const },
  { field: "Номер", value: "4123456", conf: 0.72, tone: "warning" as const },
  { field: "Дата выдачи", value: "12.03.2019", conf: 0.54, tone: "warning" as const },
];

function QueueScreen({ t, scheme }: { t: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
  return (
    <Stack style={{ gap: 12 }}>
      <Row style={{ gap: 8, flexWrap: "wrap" }}>
        <Select
          value="all"
          options={[
            { value: "all", label: "Все статусы" },
            { value: "queue", label: "Очередь" },
            { value: "ocr", label: "OCR" },
            { value: "review", label: "На проверке" },
          ]}
        />
        <Select
          value="any"
          options={[
            { value: "any", label: "Любой тип" },
            { value: "passport", label: "passport" },
            { value: "contract", label: "contract" },
          ]}
        />
        <TextInput placeholder="Поиск по файлу…" style={{ minWidth: 220 }} />
        <Button variant="secondary" size="sm">
          Обновить
        </Button>
      </Row>
      <Table
        columns={[
          { key: "file", header: "Файл" },
          { key: "type", header: "doc_type" },
          { key: "status", header: "Статус" },
          { key: "progress", header: "Прогресс" },
          { key: "conf", header: "Confidence" },
          { key: "act", header: "" },
        ]}
        rows={QUEUE_ROWS.map((r) => ({
          ...r,
          progress: `${r.progress}%`,
          act: (
            <Button variant="ghost" size="sm">
              Открыть
            </Button>
          ),
        }))}
      />
      <Row style={{ gap: 16 }}>
        <Stat label="В очереди" value="12" />
        <Stat label="OCR сейчас" value="3" />
        <Stat label="HITL" value="5" />
        <Stat label="Ошибки" value="1" />
      </Row>
    </Stack>
  );
}

function UploadScreen({ t, scheme }: { t: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
  return (
    <Grid columns={2} gap={16}>
      <Card>
        <CardHeader title="Загрузка документов" />
        <CardBody>
          <div
            style={{
              ...panel(t, scheme, {
                padding: 32,
                textAlign: "center",
                borderStyle: "dashed",
                marginBottom: 16,
              }),
            }}
          >
            <Text weight="semibold">Перетащите файлы или выберите с диска</Text>
            <Text style={{ fontSize: 12, color: t.text.secondary, marginTop: 8 }}>
              PDF, JPEG, PNG, TIFF · пакет ZIP
            </Text>
            <Button style={{ marginTop: 16 }}>Выбрать файлы</Button>
          </div>
          <Row style={{ gap: 8, alignItems: "center", marginBottom: 12 }}>
            <Text style={{ fontSize: 13, minWidth: 120 }}>Тип документа</Text>
            <Select
              value="auto"
              options={[
                { value: "auto", label: "Автоопределение (ML)" },
                { value: "passport", label: "passport" },
                { value: "contract", label: "contract" },
              ]}
            />
          </Row>
          <Callout tone="info">Антивирусная проверка и постановка в очередь OCR</Callout>
          <Button variant="primary" style={{ marginTop: 12 }}>
            Начать распознавание
          </Button>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Пакет · contract_batch.zip" />
        <CardBody>
          <Table
            columns={[
              { key: "n", header: "#" },
              { key: "file", header: "Файл" },
              { key: "st", header: "Статус" },
            ]}
            rows={[
              { n: "1", file: "c_001.pdf", st: "Готово" },
              { n: "2", file: "c_002.pdf", st: "OCR 78%" },
              { n: "3", file: "c_003.pdf", st: "Ожидание" },
            ]}
          />
        </CardBody>
      </Card>
    </Grid>
  );
}

function ReviewScreen({ t, scheme }: { t: CanvasHostTheme; scheme: SchemePalette }): JSX.Element {
  return (
    <div style={{ display: "flex", gap: 12, minHeight: 520 }}>
      <div style={{ flex: 1.2, ...panel(t, scheme, { padding: 12 }) }}>
        <Row style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <Text weight="semibold">passport_ivanov.pdf</Text>
          <Pill tone="warning" size="sm">
            HITL
          </Pill>
        </Row>
        <div
          style={{
            position: "relative",
            height: 420,
            background: t.bg.editor,
            borderRadius: 6,
            overflow: "hidden",
          }}
        >
          <Text style={{ padding: 16, fontSize: 12, color: t.text.tertiary }}>Скан документа (viewer)</Text>
          <div
            style={{
              position: "absolute",
              left: 48,
              top: 120,
              width: 200,
              height: 28,
              border: `2px solid ${t.palette.diffStripAdded}`,
              background: "rgba(46, 125, 50, 0.12)",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: 48,
              top: 168,
              width: 120,
              height: 28,
              border: `2px solid ${t.palette.diffStripRemoved}`,
              background: "rgba(198, 40, 40, 0.1)",
            }}
          />
          <Text
            style={{
              position: "absolute",
              left: 52,
              top: 124,
              fontSize: 11,
              color: t.text.primary,
            }}
          >
            Иванов И.И.
          </Text>
        </div>
        <Row style={{ gap: 8, marginTop: 10 }}>
          <Button variant="ghost" size="sm">
            −
          </Button>
          <Text style={{ fontSize: 12 }}>100%</Text>
          <Button variant="ghost" size="sm">
            +
          </Button>
          <Pill tone="neutral" size="sm">
            Разметка полей
          </Pill>
        </Row>
      </div>
      <div style={{ flex: 1, ...panel(t, scheme, { padding: 12, display: "flex", flexDirection: "column" }) }}>
        <H2 style={{ fontSize: 15, marginBottom: 8 }}>Извлечённые поля</H2>
        <Stack style={{ gap: 10, flex: 1 }}>
          {FIELDS.map((f) => (
            <div key={f.field} style={panel(t, scheme, { padding: 10 })}>
              <Row style={{ justifyContent: "space-between", marginBottom: 4 }}>
                <Text style={{ fontSize: 12, color: t.text.secondary }}>{f.field}</Text>
                <Pill tone={f.tone} size="sm">
                  {(f.conf * 100).toFixed(0)}%
                </Pill>
              </Row>
              <TextInput defaultValue={f.value} />
            </div>
          ))}
        </Stack>
        <Divider />
        <Callout tone="info" style={{ marginTop: 8 }}>
          LLM-предложение: «Дата выдачи → 12.03.2019» · Принять / Отклонить
        </Callout>
        <Row style={{ gap: 8, marginTop: 12 }}>
          <Select
            value="passport"
            options={[
              { value: "passport", label: "passport" },
              { value: "id_card", label: "id_card" },
            ]}
          />
          <Button variant="primary">Утвердить и экспорт</Button>
        </Row>
      </div>
    </div>
  );
}

const SCREEN_OPTIONS = [
  { value: "queue", label: "Очередь" },
  { value: "upload", label: "Загрузить" },
  { value: "review", label: "Проверка (HITL)" },
];

const SCREEN_SUBTITLES: Record<Screen, string> = {
  queue: "Очередь задач OCR",
  upload: "Загрузка и пакетная обработка",
  review: "Проверка извлечённых полей (HITL)",
};

export default function OcrDocumentsMockup(): JSX.Element {
  const t = useHostTheme();
  const [colorScheme, setColorScheme] = useCanvasState<ColorScheme>("ocrDocColorScheme", "default");
  const [screen, setScreen] = useCanvasState<Screen>("ocrDocScreen", "review");
  const scheme = getSchemePalette(colorScheme);
  const activeScreen = SCREEN_OPTIONS.find((opt) => opt.value === screen);

  return (
    <Stack style={{ padding: 20, maxWidth: 1200, margin: "0 auto" }}>
      <Row style={{ gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
        <Text style={{ color: t.text.tertiary, fontSize: 11 }}>Превью ·</Text>
        <Text style={{ color: t.text.secondary, fontSize: 12 }}>Схема:</Text>
        <Pill active={colorScheme === "default"} onClick={() => setColorScheme("default")} size="sm">
          Текущая
        </Pill>
        <Pill active={colorScheme === "belarusbank_classic"} onClick={() => setColorScheme("belarusbank_classic")} size="sm">
          Classic
        </Pill>
        <Pill active={colorScheme === "belarusbank_soft"} onClick={() => setColorScheme("belarusbank_soft")} size="sm">
          Soft
        </Pill>
        <Pill active={colorScheme === "belarusbank_emerald"} onClick={() => setColorScheme("belarusbank_emerald")} size="sm">
          Emerald
        </Pill>
        <Pill active={colorScheme === "belarusbank_night"} onClick={() => setColorScheme("belarusbank_night")} size="sm">
          Night
        </Pill>
      </Row>
      <Row style={{ gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <Text style={{ color: t.text.tertiary, fontSize: 11 }}>Слайд ·</Text>
        <Select value={screen} onChange={(v) => setScreen(v as Screen)} options={SCREEN_OPTIONS} />
        {SCREEN_OPTIONS.map((opt) => (
          <Pill
            key={opt.value}
            active={screen === opt.value}
            tone={screen === opt.value ? "info" : "neutral"}
            size="sm"
            onClick={() => setScreen(opt.value as Screen)}
          >
            {opt.label}
          </Pill>
        ))}
      </Row>
      <MockupWindowFrame
        t={t}
        scheme={scheme}
        title={`AI Hub · Документы · ${activeScreen?.label ?? ""}`}
        subtitle={SCREEN_SUBTITLES[screen]}
        stateKey="ocrDocHub"
        minHeight={screen === "review" ? 580 : 480}
      >
        {screen === "queue" && <QueueScreen t={t} scheme={scheme} />}
        {screen === "upload" && <UploadScreen t={t} scheme={scheme} />}
        {screen === "review" && <ReviewScreen t={t} scheme={scheme} />}
      </MockupWindowFrame>
    </Stack>
  );
}
