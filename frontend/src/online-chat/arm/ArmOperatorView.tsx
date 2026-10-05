import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type JSX, type ReactNode } from 'react'
import type { ArmTheme } from './theme'
import {
  acceptDialog,
  blockDialogRemote,
  canDownloadAttachment,
  closeDialogRemote,
  deleteMessageRemote,
  dialogRefCode,
  downloadAttachment,
  editMessageRemote,
  fetchDialogTopics,
  fetchClientHistory,
  formatWaitMmSs,
  getDialog,
  liftClientBlock,
  listClientBlocks,
  listDialogs,
  markDialogRead,
  maskPhone,
  onlineChatArmWsUrl,
  reportSuflerOutage,
  sendOperatorMessage,
  slaToneFromSeconds,
  suggestDialogTopic,
  submitSuflerHintFeedback,
  transferDialogRemote,
  uploadOperatorAttachment,
  type OnlineChatDialog,
  type DialogTopicNode,
  type OnlineChatMessage,
  type ReceiptStatus,
  type SlaTone,
} from '../api/onlineChatApi'
import {
  enterSuflerScenario,
  exitSuflerScenario,
  requestSuflerSuggest,
  type SuflerHint,
  type SuggestResponse,
} from '../../sufler/api/suggest'
import { KbPicker } from '../../sufler/KbPicker'
import { useKnowledgeBaseSelection } from '../../sufler/hooks/useKnowledgeBaseSelection'
import {
  getInternalUnreadCount,
  operatorsApi,
  getWorkScheduleStatus,
  type ChatOperator,
} from '../api/managementApi'
import {
  Button,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H3,
  IconButton,
  Link,
  Pill,
  Row,
  Select,
  Spacer,
  Stack,
  Text,
  TextArea,
} from './primitives'
import { ArmModulesHost, isArmWorkspaceModule, loadReplyTemplates } from './modules'
import type { ArmModuleId } from './modules'
import {
  ClientSummaryCard,
  EMPTY_SUMMARY_HISTORY,
  historyToSummary,
  type SummaryHistoryData,
} from './ClientSummaryCard'
import { TopicSelect } from './TopicSelect'
import { VoiceInputButton } from './components/VoiceInputButton'
const CANVAS_MOCKUP_VERSION = 'v1.4.74'

export type OperatorPresence =
  | "online"
  | "invisible"
  | "break"
  | "lunch"
  | "tech_break"
  | "training"
  | "meeting"
  | "offline_queue"
  | "offline";
type OperatorStatusShadeKey =
  | "available"
  | "invisible"
  | "break"
  | "lunch"
  | "tech_break"
  | "training"
  | "meeting"
  | "offline_queue"
  | "offline";

type StatusShadeStyle = {
  background: string;
  color: string;
  border: string;
  borderLeft: string;
};

const OPERATOR_STATUSES: {
  id: OperatorPresence;
  label: string;
  shadeKey: OperatorStatusShadeKey;
  tone: "success" | "warning" | "neutral" | "info";
}[] = [
  { id: "online", label: "в сети", shadeKey: "available", tone: "success" },
  { id: "invisible", label: "невидимка", shadeKey: "invisible", tone: "neutral" },
  { id: "break", label: "перерыв", shadeKey: "break", tone: "warning" },
  { id: "lunch", label: "обед", shadeKey: "lunch", tone: "warning" },
  { id: "tech_break", label: "техперерыв", shadeKey: "tech_break", tone: "warning" },
  { id: "training", label: "обучение", shadeKey: "training", tone: "info" },
  { id: "meeting", label: "встреча", shadeKey: "meeting", tone: "info" },
  { id: "offline_queue", label: "офлайн-обращения", shadeKey: "offline_queue", tone: "info" },
  { id: "offline", label: "не в сети", shadeKey: "offline", tone: "neutral" },
];

/** Per-status tint: inactive = light bg + colored text/left border; active = stronger fill + border on same hue. */
function operatorStatusShade(
  t: ArmTheme,
  key: OperatorStatusShadeKey,
): { inactive: StatusShadeStyle; active: StatusShadeStyle } {
  const light = t.kind === "light";
  // Muted chips: low-saturation fills, soft active state (no neon solids).
  const map: Record<OperatorStatusShadeKey, { inactive: StatusShadeStyle; active: StatusShadeStyle }> = light
    ? {
        available: {
          inactive: { background: "#eef3f0", color: "#4a6354", border: "#c5d4cb", borderLeft: "#7a9a86" },
          active: { background: "#1B8F4A", color: "#FFFFFF", border: "#146C38", borderLeft: "#0F5A2E" },
        },
        invisible: {
          inactive: { background: "#f1f0f3", color: "#5c5666", border: "#d0ccd6", borderLeft: "#8a8396" },
          active: { background: "#6B7280", color: "#FFFFFF", border: "#4B5563", borderLeft: "#374151" },
        },
        break: {
          inactive: { background: "#f5f2eb", color: "#6b5f45", border: "#ddd4c2", borderLeft: "#a8946e" },
          active: { background: "#D97706", color: "#FFFFFF", border: "#B45309", borderLeft: "#92400E" },
        },
        tech_break: {
          inactive: { background: "#f4efec", color: "#6b564c", border: "#dccfc7", borderLeft: "#a88878" },
          active: { background: "#C2410C", color: "#FFFFFF", border: "#9A3412", borderLeft: "#7C2D12" },
        },
        lunch: {
          inactive: { background: "#f5f3e9", color: "#6a6348", border: "#ddd7c0", borderLeft: "#a89c6e" },
          active: { background: "#CA8A04", color: "#FFFFFF", border: "#A16207", borderLeft: "#854D0E" },
        },
        training: {
          inactive: { background: "#eef2f2", color: "#4d5f5e", border: "#c8d2d1", borderLeft: "#7a9290" },
          active: { background: "#0F766E", color: "#FFFFFF", border: "#0D5C56", borderLeft: "#115E59" },
        },
        meeting: {
          inactive: { background: "#eef0f4", color: "#4f5666", border: "#c9ced8", borderLeft: "#7d8699" },
          active: { background: "#4F46E5", color: "#FFFFFF", border: "#4338CA", borderLeft: "#3730A3" },
        },
        offline_queue: {
          inactive: { background: "#eef2f5", color: "#4d5a66", border: "#c8d2da", borderLeft: "#7a8c9a" },
          active: { background: "#2563EB", color: "#FFFFFF", border: "#1D4ED8", borderLeft: "#1E40AF" },
        },
        offline: {
          inactive: { background: "#f1f2f3", color: "#5a6066", border: "#d0d3d6", borderLeft: "#8a9096" },
          active: { background: "#4B5563", color: "#FFFFFF", border: "#374151", borderLeft: "#1F2937" },
        },
      }
    : {
        available: {
          inactive: { background: "#2a3530", color: "#9aafa3", border: "#3d4a43", borderLeft: "#6a8074" },
          active: { background: "#2E9E68", color: "#FFFFFF", border: "#52B896", borderLeft: "#6FD4A0" },
        },
        invisible: {
          inactive: { background: "#302e34", color: "#a39eab", border: "#45424c", borderLeft: "#7a7484" },
          active: { background: "#6B7280", color: "#FFFFFF", border: "#9CA3AF", borderLeft: "#D1D5DB" },
        },
        break: {
          inactive: { background: "#342f28", color: "#b0a48e", border: "#4a4338", borderLeft: "#85765c" },
          active: { background: "#D97706", color: "#FFFFFF", border: "#FBBF24", borderLeft: "#FCD34D" },
        },
        tech_break: {
          inactive: { background: "#342c28", color: "#b09a8e", border: "#4a3e38", borderLeft: "#85705c" },
          active: { background: "#EA580C", color: "#FFFFFF", border: "#FB923C", borderLeft: "#FDBA74" },
        },
        lunch: {
          inactive: { background: "#343228", color: "#b0aa8e", border: "#4a4738", borderLeft: "#857f5c" },
          active: { background: "#CA8A04", color: "#1A1A1A", border: "#FBBF24", borderLeft: "#FDE68A" },
        },
        training: {
          inactive: { background: "#2a3232", color: "#9aabaa", border: "#3d4848", borderLeft: "#6a807e" },
          active: { background: "#0D9488", color: "#FFFFFF", border: "#2DD4BF", borderLeft: "#5EEAD4" },
        },
        meeting: {
          inactive: { background: "#2c2f36", color: "#9aa0ab", border: "#40444c", borderLeft: "#6e7484" },
          active: { background: "#6366F1", color: "#FFFFFF", border: "#818CF8", borderLeft: "#A5B4FC" },
        },
        offline_queue: {
          inactive: { background: "#2a3036", color: "#9aa4ab", border: "#3d464c", borderLeft: "#6a7884" },
          active: { background: "#3B82F6", color: "#FFFFFF", border: "#60A5FA", borderLeft: "#93C5FD" },
        },
        offline: {
          inactive: { background: "#2e3032", color: "#9aa0a3", border: "#434648", borderLeft: "#72787a" },
          active: { background: "#6B7280", color: "#FFFFFF", border: "#9CA3AF", borderLeft: "#D1D5DB" },
        },
      };
  return map[key];
}

function OperatorStatusPill({
  t,
  status,
  active = false,
  size = "sm",
  onClick,
}: {
  t: ArmTheme;
  status: (typeof OPERATOR_STATUSES)[number];
  active?: boolean;
  size?: "sm" | "md";
  onClick?: () => void;
}): JSX.Element {
  const [hovered, setHovered] = useState(false);
  const shade = operatorStatusShade(t, status.shadeKey)[active ? "active" : "inactive"];
  return (
    <button
      type="button"
      className="arm-status-pill"
      aria-pressed={active}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        fontFamily: "inherit",
        fontSize: size === "sm" ? 11 : 13,
        lineHeight: 1.3,
        padding: size === "sm" ? "3px 9px 3px 7px" : "5px 12px 5px 10px",
        borderRadius: 9999,
        cursor: onClick ? "pointer" : "default",
        border: `1px solid ${shade.border}`,
        borderLeft: size === "sm" ? `2px solid ${shade.borderLeft}` : `3px solid ${shade.borderLeft}`,
        background: shade.background,
        color: shade.color,
        fontWeight: active ? 700 : hovered ? 600 : 500,
        whiteSpace: "nowrap",
        flexShrink: 0,
        boxShadow: active ? "0 1px 4px rgba(0,0,0,0.18)" : undefined,
      }}
    >
      {status.label}
    </button>
  );
}
type ArmView = "active" | "colleague";
export type ArmStatsTab =
  | "dialogs"
  | "history"
  | "stats"
  | "colleagues"
  | "internal"
  | "templates"
  | "employees"
  | "settings"
  | "help";
type ArmRole = "operator" | "supervisor" | "admin";
/** Context for ARM side-menu RBAC: picker vs observation vs live operate. */
export type ArmMenuContext = "picker" | "view" | "operate";

/**
 * Side-menu modules by role + context.
 * Admin gets dialogs/history only while observing an operator ARM (view).
 */
const ARM_MENU_ITEMS: {
  id: ArmStatsTab;
  label: string;
  hint: string;
  roles: ArmRole[];
  contexts: ArmMenuContext[];
}[] = [
  {
    id: "dialogs",
    label: "Диалоги",
    hint: "Очереди и активная переписка",
    roles: ["operator", "supervisor", "admin"],
    contexts: ["operate", "view"],
  },
  {
    id: "history",
    label: "История обращений",
    hint: "Единая история клиента",
    roles: ["operator", "supervisor", "admin"],
    contexts: ["operate", "view"],
  },
  {
    id: "stats",
    label: "Статистика смены",
    hint: "Показатели оператора / смены",
    roles: ["operator", "supervisor"],
    contexts: ["operate", "view"],
  },
  {
    id: "colleagues",
    label: "Диалоги коллег",
    hint: "Просмотр без ответа",
    roles: ["supervisor"],
    contexts: ["operate", "view"],
  },
  {
    id: "internal",
    label: "Внутренний чат",
    hint: "Переписка между операторами",
    roles: ["operator", "supervisor"],
    contexts: ["operate", "view"],
  },
  {
    id: "templates",
    label: "Шаблоны ответов",
    hint: "Быстрые заготовки",
    roles: ["operator", "supervisor"],
    contexts: ["operate"],
  },
  {
    id: "employees",
    label: "Сотрудники",
    hint: "Список операторов для просмотра",
    roles: ["supervisor", "admin"],
    contexts: ["picker", "view"],
  },
  {
    id: "settings",
    label: "Настройки АРМ",
    hint: "Тема, уведомления, звук",
    roles: ["operator", "supervisor", "admin"],
    contexts: ["picker", "operate", "view"],
  },
  {
    id: "help",
    label: "Справка",
    hint: "Краткая инструкция по АРМ",
    roles: ["operator", "supervisor", "admin"],
    contexts: ["picker", "operate", "view"],
  },
];

function armMenuItemsForRole(role: ArmRole, context: ArmMenuContext = "operate") {
  return ARM_MENU_ITEMS.filter(
    (item) => item.roles.includes(role) && item.contexts.includes(context),
  );
}

function firstArmStatsTabForRole(role: ArmRole, context: ArmMenuContext = "operate"): ArmStatsTab {
  return armMenuItemsForRole(role, context)[0]?.id ?? "dialogs";
}

export type ColorScheme =
  | "default"
  | "belarusbank_classic"
  | "belarusbank_soft"
  | "belarusbank_emerald"
  | "belarusbank_night";
export const COLOR_SCHEME_ORDER: ColorScheme[] = [
  "default",
  "belarusbank_classic",
  "belarusbank_soft",
  "belarusbank_emerald",
  "belarusbank_night",
];
const ARM_LEFT_WIDTH_MIN = 180;
const ARM_LEFT_WIDTH_MAX = 380;
const ARM_LEFT_WIDTH_DEFAULT = 220;
const ARM_RIGHT_WIDTH_MIN = 220;
const ARM_RIGHT_WIDTH_MAX = 420;
const ARM_RIGHT_WIDTH_DEFAULT = 260;

/** Fallback roster if operators API is unavailable. */
export const TRANSFER_OPERATORS = [
  "Петрова А.С.",
  "Сидоров М.В.",
  "Козлов Д.А.",
  "Морозова Е.И.",
  "Васильев Н.П.",
];

function flattenTopicLeaves(nodes: DialogTopicNode[]): Array<{ id: string; path: string }> {
  const rows: Array<{ id: string; path: string }> = []
  const walk = (items: DialogTopicNode[]) => {
    for (const item of items) {
      if (item.is_selectable) rows.push({ id: item.id, path: item.full_path || item.label })
      if (Array.isArray(item.children) && item.children.length > 0) walk(item.children)
    }
  }
  walk(nodes)
  return rows
}

function topicPathById(nodes: DialogTopicNode[], topicId: string): string {
  if (!topicId) return ""
  const leaf = flattenTopicLeaves(nodes).find((item) => item.id === topicId)
  return leaf?.path || ""
}

export type SchemePalette = {
  label: string;
  accent: string;
  accentWeak: string;
  accentControl: string;
  headerBg: string;
  panelBg: string;
  badge: string;
};

export function getSchemePalette(theme: ArmTheme, scheme: ColorScheme): SchemePalette {
  const isLight = theme.kind === "light";

  if (scheme === "belarusbank_classic") {
    return isLight
      ? {
          label: "Беларусбанк Classic",
          accent: "#0C4DA2",
          accentWeak: "#BFD3F3",
          accentControl: "#0A3F87",
          headerBg: "linear-gradient(135deg, #EAF2FF 0%, #DCEAFF 55%, #F4F8FF 100%)",
          panelBg: "linear-gradient(180deg, #F7FAFF 0%, #EDF4FF 100%)",
          badge: "#C62828",
        }
      : {
          label: "Беларусбанк Classic",
          accent: "#6AA8F0",
          accentWeak: "#2A4570",
          accentControl: "#8BBCF5",
          headerBg: "linear-gradient(135deg, #15253D 0%, #1A2F4A 55%, #182433 100%)",
          panelBg: "linear-gradient(180deg, #121A28 0%, #152235 100%)",
          badge: "#EF5350",
        };
  }
  if (scheme === "belarusbank_soft") {
    return isLight
      ? {
          label: "Беларусбанк Soft",
          accent: "#2E5AAC",
          accentWeak: "#C8D6EF",
          accentControl: "#2A4F93",
          headerBg: "linear-gradient(135deg, #F3F7FF 0%, #EAF1FF 58%, #FDFEFF 100%)",
          panelBg: "linear-gradient(180deg, #FAFCFF 0%, #F1F6FF 100%)",
          badge: "#D46A6A",
        }
      : {
          label: "Беларусбанк Soft",
          accent: "#8AA8E0",
          accentWeak: "#2C3A58",
          accentControl: "#A4BAE8",
          headerBg: "linear-gradient(135deg, #1A2233 0%, #1F2A40 58%, #181F2C 100%)",
          panelBg: "linear-gradient(180deg, #141A26 0%, #1A2434 100%)",
          badge: "#E08080",
        };
  }
  if (scheme === "belarusbank_emerald") {
    return isLight
      ? {
          label: "Беларусбанк Emerald",
          accent: "#007A43",
          accentWeak: "#BEE8D5",
          accentControl: "#00663A",
          headerBg: "linear-gradient(135deg, #EAF8F1 0%, #DCF3E8 58%, #F2FBF6 100%)",
          panelBg: "linear-gradient(180deg, #F5FCF8 0%, #EAF7F1 100%)",
          badge: "#0B9E5E",
        }
      : {
          label: "Беларусбанк Emerald",
          accent: "#6FD4A0",
          accentWeak: "#244A38",
          accentControl: "#8EE0B4",
          headerBg: "linear-gradient(135deg, #1A3428 0%, #214835 58%, #1C3A2C 100%)",
          panelBg: "linear-gradient(180deg, #173028 0%, #1E3C30 100%)",
          badge: "#52B896",
        };
  }
  if (scheme === "belarusbank_night") {
    return isLight
      ? {
          label: "Беларусбанк Night",
          accent: "#0D5C86",
          accentWeak: "#C5D9E6",
          accentControl: "#0A4D70",
          headerBg: "linear-gradient(135deg, #E8F1F8 0%, #D8E8F4 60%, #EFF6FB 100%)",
          panelBg: "linear-gradient(180deg, #F3F8FC 0%, #E6F1F8 100%)",
          badge: "#2D7FB8",
        }
      : {
          label: "Беларусбанк Night",
          accent: "#5BA4D4",
          accentWeak: "#1A3344",
          accentControl: "#7AB8DE",
          headerBg: "linear-gradient(135deg, #122430 0%, #173040 60%, #142028 100%)",
          panelBg: "linear-gradient(180deg, #0F1C24 0%, #152A36 100%)",
          badge: "#4A9AD0",
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
const RADIUS_SM = 6;
const RADIUS_MD = 8;
type QueueItem = {
  id: string;
  name: string;
  channel: string;
  dept: string;
  preview: string;
  wait: string;
  /** Seconds at fetch time; used with waitFetchedAt for 1s SLA ticks. */
  waitBaseSeconds?: number;
  waitFetchedAt?: number;
  /** Absolute ISO anchor from backend — preferred for smooth SLA ticks. */
  waitAnchorAt?: string;
  urgent: boolean;
  active?: boolean;
  result?: "offline" | "closed" | "declined";
  operatorName?: string;
  readOnly?: boolean;
  /** True when item comes from Django online_chat API (not canvas mock). */
  live?: boolean;
  phone?: string;
  firstName?: string;
  lastName?: string;
  slaTone?: SlaTone;
  clientOnline?: boolean;
  initiatedBy?: string;
  refCode?: string;
  needsReply?: boolean;
  isTestClient?: boolean;
  entryUrl?: string;
  unreadCount?: number;
  clientFields?: { label: string; value: string }[];
  outcome?: string;
  routingReason?: string;
};

function liveWaitSeconds(item: QueueItem, nowMs: number): number | null {
  if (item.waitAnchorAt) {
    const anchorMs = Date.parse(item.waitAnchorAt);
    if (!Number.isNaN(anchorMs)) {
      return Math.max(0, Math.floor((nowMs - anchorMs) / 1000));
    }
  }
  if (item.waitBaseSeconds == null || item.waitFetchedAt == null) return null;
  const elapsed = Math.max(0, Math.floor((nowMs - item.waitFetchedAt) / 1000));
  return item.waitBaseSeconds + elapsed;
}

function resolveQueueWait(item: QueueItem, nowMs: number): { wait: string; slaTone?: SlaTone; urgent: boolean } {
  const seconds = liveWaitSeconds(item, nowMs);
  if (seconds == null) {
    return { wait: item.wait, slaTone: item.slaTone, urgent: item.urgent };
  }
  const slaTone = slaToneFromSeconds(seconds);
  return {
    wait: formatWaitMmSs(seconds),
    slaTone,
    urgent: slaTone === "critical",
  };
}

function slaToneColor(tone?: SlaTone): string {
  if (tone === "critical") return "#E53935";
  if (tone === "warn") return "#F9A825";
  return "#2E7D32";
}

function SlaWaitPill({
  wait,
  slaTone,
  label = "",
}: {
  wait: string;
  slaTone?: SlaTone;
  label?: string;
}): JSX.Element {
  const color = slaToneColor(slaTone);
  return (
    <span
      title="SLA ожидания ответа"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        padding: "3px 8px",
        borderRadius: 999,
        background: `linear-gradient(180deg, ${color}22 0%, ${color}14 100%)`,
        color,
        border: `1px solid ${color}55`,
        fontWeight: 700,
        lineHeight: 1.2,
        flexShrink: 0,
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "0.02em",
        boxShadow: `inset 0 0 0 1px ${color}10`,
        transition: "color 160ms ease, border-color 160ms ease, background 160ms ease",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: color,
          boxShadow: `0 0 0 2px ${color}33`,
          flexShrink: 0,
        }}
      />
      <span style={{ opacity: 0.85, fontWeight: 600 }}>{label || "SLA"}</span>
      <span style={{ minWidth: "3.2em", textAlign: "right" }}>{wait}</span>
    </span>
  );
}

function dialogToQueueItem(
  dialog: OnlineChatDialog,
  options?: { active?: boolean },
): QueueItem {
  const needsReply = dialog.needs_reply ?? false;
  const inSharedQueue = dialog.status === "waiting";
  const trackWait = needsReply || inSharedQueue;
  const waitSeconds = trackWait ? dialog.wait_seconds : 0;
  const slaTone = trackWait ? slaToneFromSeconds(waitSeconds) : "ok";
  const fetchedAt = Date.now();
  return {
    id: dialog.id,
    name: dialog.client_name || "Клиент",
    channel: dialog.channel === "widget" ? "Сайт" : dialog.channel,
    dept: dialog.department_name?.trim() || "",
    preview: dialog.preview || "—",
    wait: trackWait ? formatWaitMmSs(waitSeconds) : "—",
    waitBaseSeconds: trackWait ? waitSeconds : undefined,
    waitFetchedAt: trackWait ? fetchedAt : undefined,
    waitAnchorAt: trackWait ? dialog.wait_anchor_at || undefined : undefined,
    urgent: trackWait && slaTone === "critical",
    slaTone: trackWait ? slaTone : undefined,
    active: options?.active,
    live: true,
    isTestClient: !!dialog.is_test_client,
    phone: dialog.client_phone,
    firstName: dialog.client_first_name,
    lastName: dialog.client_last_name,
    operatorName: dialog.operator_name || undefined,
    clientOnline: dialog.client_online,
    initiatedBy: dialog.initiated_by,
    refCode: dialogRefCode(dialog),
    needsReply,
    entryUrl: dialog.entry_url || undefined,
    clientFields: dialog.client_fields || [],
    outcome: dialog.outcome || undefined,
    routingReason: dialog.routing_reason || undefined,
  };
}

function messageTimeLabel(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function initialsFromDisplayName(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

const MY_DIALOGUES: QueueItem[] = [
  {
    id: "m1",
    name: "Светлана Р.",
    channel: "Viber",
    dept: "Розничные продукты",
    preview: "Когда будет готов перевод SWIFT?",
    wait: "04:32",
    urgent: false,
    active: true,
  },
  {
    id: "m2",
    name: "Дмитрий В.",
    channel: "Сайт",
    dept: "Ипотека",
    preview: "Уточните ставку по ипотеке «Моя квартира»",
    wait: "01:08",
    urgent: false,
  },
];

const OFFLINE_QUEUE: QueueItem[] = [
  {
    id: "o1",
    name: "Пётр Мельников",
    channel: "Telegram",
    dept: "Розничные продукты",
    preview: "Не приходит SMS для подтверждения операции",
    wait: "—",
    urgent: false,
    result: "offline",
  },
];

const CLOSED_QUEUE: QueueItem[] = [
  {
    id: "l1",
    name: "ООО «Вектор»",
    channel: "Сайт",
    dept: "Юрлица",
    preview: "Тарифы на РКО для ИП",
    wait: "—",
    urgent: false,
    result: "closed",
  },
];

const INITIATED_QUEUE: QueueItem[] = [
  {
    id: "i1",
    name: "Елена С.",
    channel: "Сайт",
    dept: "Розничные продукты",
    preview: "Исходящее: напоминание о платеже",
    wait: "00:05",
    urgent: false,
  },
];

const SHARED_QUEUE: QueueItem[] = [
  {
    id: "s1",
    name: "Марина Т.",
    channel: "Сайт",
    dept: "Розничные продукты",
    preview: "Как подключить SMS-информирование?",
    wait: "03:55",
    urgent: true,
  },
  {
    id: "s2",
    name: "ИП Ковалёв",
    channel: "Telegram",
    dept: "Юрлица",
    preview: "Запрос выписки по расчётному счёту",
    wait: "02:40",
    urgent: false,
  },
];

const COLLEAGUE_DIALOGUES: QueueItem[] = [
  {
    id: "c1",
    name: "Анна Козлова",
    channel: "Сайт",
    dept: "Розничные продукты",
    preview: "Подскажите лимит снятия наличных в банкомате?",
    wait: "02:14",
    urgent: true,
    operatorName: "Петрова А.С.",
    readOnly: true,
  },
  {
    id: "c2",
    name: "Дмитрий В.",
    channel: "Viber",
    dept: "Ипотека",
    preview: "Уточните ставку по ипотеке «Моя квартира»",
    wait: "01:08",
    urgent: false,
    operatorName: "Сидоров М.В.",
    readOnly: true,
  },
  {
    id: "c3",
    name: "Марина Т.",
    channel: "Telegram",
    dept: "Розничные продукты",
    preview: "Как подключить SMS-информирование?",
    wait: "03:55",
    urgent: false,
    operatorName: "Петрова А.С.",
    readOnly: true,
  },
];

type QueueSectionId =
  | "waiting"
  | "mine"
  | "colleagues"
  | "offline"
  | "closed"
  | "shared"
  | "initiated";

type QueueSectionDef = {
  id: QueueSectionId;
  title: string;
  count: number;
  items: QueueItem[];
  defaultExpanded: boolean;
};

const QUEUE_SECTIONS: QueueSectionDef[] = [
  // «Ожидают ответа» объединены с «В диалоге со мной» — непрочитанные показываем бейджем.
  { id: "mine", title: "В диалоге со мной", count: 2, items: MY_DIALOGUES, defaultExpanded: true },
  { id: "initiated", title: "Инициированные мной", count: 1, items: INITIATED_QUEUE, defaultExpanded: false },
  { id: "offline", title: "Офлайн", count: 1, items: OFFLINE_QUEUE, defaultExpanded: false },
  { id: "closed", title: "Недавно закрытые", count: 1, items: CLOSED_QUEUE, defaultExpanded: false },
  { id: "shared", title: "Общая очередь", count: 5, items: SHARED_QUEUE, defaultExpanded: false },
];

const COLLEAGUES_SECTION: QueueSectionDef = {
  id: "colleagues",
  title: "Диалоги коллег",
  count: COLLEAGUE_DIALOGUES.length,
  items: COLLEAGUE_DIALOGUES,
  defaultExpanded: false,
};

function queueSectionsForRole(role: ArmRole): QueueSectionDef[] {
  // «Общая очередь» всегда первая; «Диалоги коллег» — только супервизор.
  const withoutShared = QUEUE_SECTIONS.filter((section) => section.id !== "shared");
  const shared = QUEUE_SECTIONS.find((section) => section.id === "shared")!;
  if (role === "supervisor") {
    return [
      shared,
      withoutShared[0],
      COLLEAGUES_SECTION,
      ...withoutShared.slice(1),
    ];
  }
  return [shared, ...withoutShared];
}

function findSectionForQueueItem(queueId: string, sections: QueueSectionDef[]): QueueSectionDef | undefined {
  return sections.find((section) => section.items.some((item) => item.id === queueId));
}

function defaultExpandedSections(): Record<QueueSectionId, boolean> {
  const allSections = [...QUEUE_SECTIONS, COLLEAGUES_SECTION];
  return allSections.reduce(
    (acc, section) => {
      acc[section.id] = section.defaultExpanded;
      return acc;
    },
    {} as Record<QueueSectionId, boolean>,
  );
}

function allSectionsExpandedState(sections: QueueSectionDef[]): Record<QueueSectionId, boolean> {
  return sections.reduce(
    (acc, section) => {
      acc[section.id] = true;
      return acc;
    },
    {} as Record<QueueSectionId, boolean>,
  );
}

function allSectionsCollapsedState(sections: QueueSectionDef[]): Record<QueueSectionId, boolean> {
  return sections.reduce(
    (acc, section) => {
      acc[section.id] = false;
      return acc;
    },
    {} as Record<QueueSectionId, boolean>,
  );
}

function isSectionExpanded(
  expandedSections: Record<QueueSectionId, boolean>,
  section: QueueSectionDef,
): boolean {
  return expandedSections[section.id] ?? section.defaultExpanded;
}

function areAllSectionsCollapsed(
  expandedSections: Record<QueueSectionId, boolean>,
  sections: QueueSectionDef[],
): boolean {
  return sections.every((section) => !isSectionExpanded(expandedSections, section));
}

function panelStyle(t: ArmTheme, extra?: CSSProperties): CSSProperties {
  return {
    background: t.fill.secondary,
    border: `1px solid ${t.stroke.secondary}`,
    borderRadius: RADIUS_MD,
    ...extra,
  };
}

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

/** Разноцветные чипы оценки (как в суфлёре): зелёный / сине-серый / янтарный. */
function feedbackChipPalette(t: ArmTheme, choice: SuflerFeedbackChoice): FeedbackChipPalette {
  const isLight = t.kind === "light";
  if (choice === "used") {
    return {
      idleBg: t.diff.insertedLine,
      idleBorder: isLight ? "#1F8A6533" : "#3FA26640",
      activeBg: isLight ? "#1F8A6533" : "#3FA2664D",
      activeBorder: t.palette.diffStripAdded,
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

function feedbackChipStyle(
  t: ArmTheme,
  choice: SuflerFeedbackChoice,
  selected: boolean,
  hovered: boolean,
  disabled: boolean,
): CSSProperties {
  const palette = feedbackChipPalette(t, choice);
  const emphasized = selected || hovered;
  return {
    display: "inline-flex",
    alignItems: "center",
    fontSize: 12,
    fontWeight: emphasized ? 600 : 500,
    padding: "5px 10px",
    borderRadius: 6,
    border: `1px solid ${emphasized ? palette.activeBorder : palette.idleBorder}`,
    background: emphasized ? palette.activeBg : palette.idleBg,
    color: emphasized ? palette.activeColor : t.text.secondary,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.55 : 1,
    lineHeight: 1.25,
    whiteSpace: "nowrap",
    flexShrink: 0,
    appearance: "none",
    fontFamily: "inherit",
    outline: "none",
  };
}

function SuflerFeedbackChip({
  t,
  option,
  selected,
  disabled,
  onSelect,
}: {
  t: ArmTheme;
  option: (typeof SUFLER_FEEDBACK_OPTIONS)[number];
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}): JSX.Element {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      className="arm-feedback-chip"
      disabled={disabled}
      title={option.label}
      style={feedbackChipStyle(t, option.id, selected, hovered && !disabled, !!disabled)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => {
        if (disabled) return;
        onSelect();
      }}
    >
      {option.label}{selected ? ' ✓' : ''}
    </button>
  );
}

function SuflerFeedbackRow({
  t,
  scheme: _scheme,
  cardId: _cardId,
  disabled,
  onFeedback,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  cardId: string;
  disabled?: boolean;
  onFeedback?: (choice: SuflerFeedbackChoice) => void;
}): JSX.Element {
  const [selected, setSelected] = useState<SuflerFeedbackChoice | null>(null);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row",
        flexWrap: "wrap",
        gap: 6,
        marginTop: 8,
        alignItems: "center",
      }}
    >
      {SUFLER_FEEDBACK_OPTIONS.map((option) => (
        <SuflerFeedbackChip
          key={option.id}
          t={t}
          option={option}
          selected={selected === option.id}
          disabled={disabled || !!selected}
          onSelect={() => {
            if (selected) return;
            setSelected(option.id);
            onFeedback?.(option.id);
          }}
        />
      ))}
    </div>
  );
}

function AutoFadeNotice({
  message,
  onDone,
  tone = "success",
  style,
}: {
  message: string;
  onDone?: () => void;
  tone?: "success" | "info" | "warning" | "danger";
  style?: CSSProperties;
}): JSX.Element {
  const [hiding, setHiding] = useState(false);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    setHiding(false);
    const fadeTimer = window.setTimeout(() => setHiding(true), 4200);
    const clearTimer = window.setTimeout(() => onDoneRef.current?.(), 5000);
    return () => {
      window.clearTimeout(fadeTimer);
      window.clearTimeout(clearTimer);
    };
  }, [message]);

  return (
    <Callout
      tone={tone}
      className={`arm-fade-notice${hiding ? " arm-fade-notice--hiding" : ""}`}
      style={{
        margin: 0,
        fontSize: 12,
        boxShadow: "0 8px 22px rgba(16, 40, 28, 0.14)",
        pointerEvents: "auto",
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        ...style,
      }}
    >
      <span style={{ flex: 1, minWidth: 0, lineHeight: 1.45 }}>{message}</span>
      <button
        type="button"
        aria-label="Закрыть уведомление"
        title="Закрыть"
        onClick={(event) => {
          event.stopPropagation();
          onDoneRef.current?.();
        }}
        style={{
          flexShrink: 0,
          width: 22,
          height: 22,
          border: "none",
          borderRadius: 6,
          background: "transparent",
          cursor: "pointer",
          color: "inherit",
          opacity: 0.7,
          fontSize: 14,
          lineHeight: 1,
          padding: 0,
          fontFamily: "inherit",
        }}
      >
        ✕
      </button>
    </Callout>
  );
}

/** Status toasts that float and never shift the composer / empty-state layout. */
function ComposerOverlayNotices({
  notices,
  placement = "above",
}: {
  notices: Array<{ id: string; message: string; tone?: "success" | "info" | "warning" | "danger"; onDone?: () => void }>;
  placement?: "above" | "bottom";
}): JSX.Element | null {
  if (notices.length === 0) return null;
  return (
    <div
      aria-live="polite"
      style={{
        position: "absolute",
        left: 12,
        right: 12,
        ...(placement === "above"
          ? { bottom: "100%", marginBottom: 8 }
          : { bottom: 16 }),
        zIndex: 30,
        display: "flex",
        flexDirection: "column",
        gap: 6,
        pointerEvents: "none",
        maxWidth: 480,
        marginLeft: "auto",
        marginRight: "auto",
      }}
    >
      {notices.map((notice) => (
        <AutoFadeNotice
          key={`${notice.id}:${notice.message}`}
          message={notice.message}
          tone={notice.tone}
          onDone={notice.onDone}
        />
      ))}
    </div>
  );
}
type RelevanceTier = "high" | "mediumStrong" | "mediumLight" | "low";

function parseRelevancePercent(relevance: number | string): number {
  if (typeof relevance === "number") return relevance;
  const match = relevance.match(/(\d+(?:\.\d+)?)/);
  return match ? Number(match[1]) : 0;
}

function relevanceTierFromPercent(pct: number): RelevanceTier {
  // High = green, mediumStrong = orange, mediumLight = amber, low = red-ish.
  if (pct >= 75) return "high";
  if (pct >= 50) return "mediumStrong";
  if (pct >= 35) return "mediumLight";
  return "low";
}

type RelevanceShadeStyle = {
  tier: RelevanceTier;
  tone: "success" | "warning" | "neutral";
  background: string;
  border: string;
  borderLeft: string;
};

/** Relevance palette: high green · mid orange · mid-low amber · low red. */
const RELEVANCE_SHADE_COLORS = {
  high: {
    borderLight: "#2E7D3270",
    borderDark: "#3FA26688",
  },
  mediumStrong: {
    bgLight: "#F5A62328",
    bgDark: "#F5A62340",
    borderLight: "#E67E2288",
    borderDark: "#F39C1288",
    borderLeftLight: "#E67E22EE",
    borderLeftDark: "#F39C12EE",
  },
  mediumLight: {
    bgLight: "#FFB30022",
    bgDark: "#FFB30035",
    borderLight: "#FB8C0080",
    borderDark: "#FFA72680",
    borderLeftLight: "#FB8C00CC",
    borderLeftDark: "#FFA726CC",
  },
  low: {
    bgLight: "#E5393520",
    bgDark: "#E5393535",
    borderLight: "#C6282888",
    borderDark: "#EF535088",
    borderLeftLight: "#C62828EE",
    borderLeftDark: "#EF5350EE",
  },
} as const;

function relevanceShade(t: ArmTheme, relevance: number | string): RelevanceShadeStyle {
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
    tone: "warning",
    background: isLight ? c.bgLight : c.bgDark,
    border: isLight ? c.borderLight : c.borderDark,
    borderLeft: isLight ? c.borderLeftLight : c.borderLeftDark,
  };
}

/** Neutral right-panel cards: border is a more saturated tone of the field background. */
function neutralCardSurface(t: ArmTheme, isExpanded: boolean): { background: string; border: string } {
  const background = isExpanded ? t.bg.elevated : t.fill.tertiary;
  return {
    background,
    border: t.stroke.secondary,
  };
}

/** Демо-полировка текста (нормализация пробелов, заглавная буква). */
function polishTextDemo(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length === 0) return text;
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

type AiImproveModalState = {
  original: string;
  improved: string;
};

function AiImprovePopover({
  t,
  scheme,
  state,
  onAccept,
  onDismiss,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  state: AiImproveModalState;
  onAccept: () => void;
  onDismiss: () => void;
}): JSX.Element {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="ai-improve-title"
      style={{
        position: "absolute",
        bottom: "calc(100% + 8px)",
        left: 0,
        right: 0,
        zIndex: 100,
        background: t.bg.elevated,
        border: `1px solid ${scheme.accent}`,
        borderRadius: RADIUS_MD,
        padding: 12,
        boxSizing: "border-box",
      }}
    >
      <Row style={{ alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <Text id="ai-improve-title" weight="semibold">
          Улучшение текста
        </Text>
        <IconButton title="Закрыть" aria-label="Закрыть" onClick={onDismiss}>
          ×
        </IconButton>
      </Row>
      <div
        style={{
          marginTop: 10,
          maxHeight: 100,
          padding: "10px 12px",
          borderRadius: RADIUS_SM,
          background: t.fill.quaternary,
          border: `1px solid ${t.stroke.tertiary}`,
          overflowY: "auto",
        }}
      >
        <Text style={{ fontSize: 13, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{state.improved}</Text>
      </div>
      <Row style={{ marginTop: 12, justifyContent: "flex-end", alignItems: "center", gap: 8 }}>
        <Button variant="ghost" onClick={onDismiss}>
          Закрыть
        </Button>
        <Button variant="primary" onClick={onAccept}>
          Применить
        </Button>
      </Row>
      <Text tone="secondary" style={{ fontSize: 11, lineHeight: 1.4, textAlign: "center", marginTop: 8 }}>
        Всегда проверяйте сгенерированные сообщения перед отправкой
      </Text>
    </div>
  );
}

type SuflerHintData = {
  id: string;
  title: string;
  preview: string;
  answerText: string;
  detailText?: string;
  operatorTip?: string;
  relevance: string;
  relevanceTone: "success" | "neutral" | "warning";
  suzTitle: string;
  permalink?: string;
  highlighted?: boolean;
  isScenario?: boolean;
};

/** Sufler found nothing usable in the knowledge base (non-bank chit-chat or no source). */
const SUFLER_NO_KNOWLEDGE_MESSAGE =
  "Информации для ответа на данный вопрос нет в базе знаний.";
/** Sufler itself is down (exception / timeout / empty index) — offer to report. */
const SUFLER_UNAVAILABLE_MESSAGE = "Ошибка, суфлёр недоступен.";

/** Demo-only: which simulator test client should showcase the outage + report flow. */
const DEMO_SUFLER_OUTAGE_CLIENT_NUMBER = 2;

/**
 * Wait this long after the last client message before asking the sufler. Lets a
 * question typed as several single-word messages get batched into one query
 * without noticeably delaying the hint for normal single-message questions.
 */
const SUFLER_FRAGMENT_DEBOUNCE_MS = 1400;

function testClientNumber(item: { lastName?: string; name?: string } | null | undefined): number | null {
  if (!item) return null;
  const fromLast = (item.lastName || "").trim();
  if (/^\d+$/.test(fromLast)) return Number(fromLast);
  const match = (item.name || "").match(/(\d+)/);
  return match ? Number(match[1]) : null;
}

function isSuflerChitChat(text: string): boolean {
  const cleaned = text.trim().toLowerCase().replace(/[.!?…,]/g, "");
  if (!cleaned) return true;
  const tokens = cleaned.split(/\s+/).filter(Boolean);
  if (tokens.length > 4) return false;
  const chitChat = new Set([
    "спасибо",
    "спасибо большое",
    "благодарю",
    "ок",
    "окей",
    "хорошо",
    "понял",
    "поняла",
    "ясно",
    "ага",
    "угу",
    "да",
    "нет",
    "все",
    "всё",
    "все спасибо",
    "всё спасибо",
    "хорошо спасибо",
    "спасибо большое",
  ]);
  return chitChat.has(cleaned) || tokens.every((token) => chitChat.has(token));
}

function mapApiHintToCard(hint: SuflerHint, index: number): SuflerHintData {
  const citation = hint.citations?.[0];
  const title = hint.source_type === "scenario"
    ? "Ответ по активному сценарию"
    : citation?.title?.trim() || `Подсказка ${hint.rank || index + 1}`;
  const answerText = (hint.text || "").trim();
  const preview = answerText.length > 120 ? `${answerText.slice(0, 117)}…` : answerText;
  const percent = Math.round(hint.relevance_percent ?? hint.relevance_score * 100);
  const tone: SuflerHintData["relevanceTone"] =
    percent >= 75 ? "success" : percent >= 50 ? "neutral" : "warning";
  const tip = (hint.operator_tip || "").trim();
  const detailText = (hint.detail_text || answerText).trim();
  return {
    id: `hint-${hint.rank}-${index}`,
    title,
    preview,
    answerText,
    detailText: detailText || undefined,
    operatorTip: tip || undefined,
    relevance: `${percent}%`,
    relevanceTone: tone,
    suzTitle: title,
    permalink: citation?.permalink?.trim() || undefined,
    highlighted: index === 0,
    isScenario: hint.source_type === "scenario",
  };
}

type ClientInfoData = {
  name: string;
  phoneMasked: string;
  phoneFull: string;
  dialogNo: string;
  visitorId: string;
  visitTime: string;
  entryPath: string;
  entryChannel: string;
  browser: string;
  device: string;
  email: string;
  channel: string;
  fields?: { label: string; value: string }[];
};

const ACTIVE_CLIENT: ClientInfoData = {
  name: "Анна Козлова",
  phoneMasked: "+375 ** ***-**-45",
  phoneFull: "+375 29 123-45-45",
  dialogNo: "№ 18 944",
  visitorId: "vis-7f3a2b1c",
  visitTime: "09.07.2026, 08:42",
  entryPath: "/fizicheskim_licam/cards/",
  entryChannel: "Виджет сайта",
  browser: "Chrome 125",
  device: "Windows 11",
  email: "anna.k@example.com",
  channel: "Сайт",
};

function ClientInfoField({
  t,
  label,
  value,
  children,
}: {
  t: ArmTheme;
  label: string;
  value?: string;
  children?: ReactNode;
}): JSX.Element {
  return (
    <div>
      <Text style={{ fontSize: 11, color: t.text.tertiary }}>{label}</Text>
      {children ?? <Text style={{ fontSize: 12, marginTop: 2, lineHeight: 1.35 }}>{value}</Text>}
    </div>
  );
}

function EntryPointValue({
  t,
  scheme,
  entryPath,
  entryChannel,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  entryPath: string;
  entryChannel: string;
}): JSX.Element {
  const [hovered, setHovered] = useState(false);
  const href = entryPath.startsWith("http") ? entryPath : `https://belarusbank.by${entryPath}`;

  return (
    <Text style={{ fontSize: 12, marginTop: 2, lineHeight: 1.35 }}>
      <span
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{ display: "inline" }}
      >
        <Link
          href={href}
          style={{
            color: scheme.accentControl,
            textDecoration: hovered ? "underline" : "none",
          }}
        >
          {entryPath}
        </Link>
      </span>
      <span style={{ color: t.text.secondary }}> · {entryChannel}</span>
    </Text>
  );
}

function ClientInfoCard({
  t,
  scheme,
  client,
  isExpanded,
  onToggle,
  disabled,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  client: ClientInfoData;
  isExpanded: boolean;
  onToggle: () => void;
  disabled?: boolean;
}): JSX.Element {
  const [phoneRevealed, setPhoneRevealed] = useState(false);
  const surface = neutralCardSurface(t, isExpanded);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Клиент: ${client.name}`}
      aria-expanded={isExpanded}
      style={{ marginTop: 8, outline: "none", cursor: "pointer" }}
      onClick={() => onToggle()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onToggle();
        }
      }}
    >
      <Card
        style={{
          background: surface.background,
          border: `1px solid ${surface.border}`,
        }}
      >
        <CardBody>
          {isExpanded ? (
            <Stack gap={10}>
              <Text weight="semibold">{client.name}</Text>
              <Grid columns={2} style={{ gap: 10 }}>
                <ClientInfoField t={t} label="№ диалога" value={client.dialogNo} />
                <ClientInfoField t={t} label="ID посетителя" value={client.visitorId} />
              </Grid>
              <ClientInfoField t={t} label="Время визита" value={client.visitTime} />
              <ClientInfoField t={t} label="Точка входа">
                <EntryPointValue t={t} scheme={scheme} entryPath={client.entryPath} entryChannel={client.entryChannel} />
              </ClientInfoField>
              <ClientInfoField t={t} label="Браузер / устройство" value={`${client.browser} · ${client.device}`} />
              <ClientInfoField t={t} label="Канал" value={client.channel} />
              <ClientInfoField t={t} label="E-mail" value={client.email} />
              {client.fields && client.fields.length > 0
                ? client.fields
                    .filter((item) => !/e-?mail|почт/i.test(item.label))
                    .map((item, index) => (
                      <ClientInfoField
                        key={`${item.label}-${index}`}
                        t={t}
                        label={item.label}
                        value={item.value}
                      />
                    ))
                : null}
              <ClientInfoField t={t} label="Телефон">
                <Row style={{ gap: 6, alignItems: "center", marginTop: 2, flexWrap: "wrap" }}>
                  <Text style={{ fontSize: 12 }}>{phoneRevealed ? client.phoneFull : client.phoneMasked}</Text>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      setPhoneRevealed((prev) => !prev);
                    }}
                  >
                    {phoneRevealed ? "Скрыть" : "Показать"}
                  </Button>
                </Row>
              </ClientInfoField>
              <Button
                variant="ghost"
                size="sm"
                disabled={disabled}
                onClick={(e) => e.stopPropagation()}
              >
                Изменить
              </Button>
            </Stack>
          ) : (
            <div>
              <Text weight="semibold">{client.name}</Text>
              <Text style={{ fontSize: 12, color: t.text.secondary, marginTop: 4 }}>
                {client.phoneMasked}
              </Text>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function SuflerHintCard({
  t,
  scheme,
  hint,
  isExpanded,
  onToggle,
  onInsert,
  disabled,
  onFeedback,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  hint: SuflerHintData;
  isExpanded: boolean;
  onToggle: () => void;
  onInsert: (answerText: string) => void;
  disabled?: boolean;
  onFeedback?: (choice: SuflerFeedbackChoice) => void;
}): JSX.Element {
  const shade = relevanceShade(t, hint.relevance);
  const [detailOpen, setDetailOpen] = useState(false);
  const detailText = (hint.detailText || hint.answerText).trim();

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Подсказка: ${hint.title}`}
      aria-expanded={isExpanded}
      style={{ marginTop: 8, outline: "none", cursor: "pointer" }}
      onClick={() => onToggle()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onToggle();
        }
      }}
    >
      <Card
        style={{
          background: shade.background,
          border: `1px solid ${shade.border}`,
          borderLeft: `3px solid ${shade.borderLeft}`,
        }}
      >
        <CardHeader trailing={<Pill tone={shade.tone}>{hint.relevance}</Pill>}>
          {hint.title}
        </CardHeader>
        <CardBody>
          {isExpanded ? (
            <Text style={{ fontSize: 12, lineHeight: 1.5, color: t.text.primary, marginBottom: 12 }}>
              {hint.answerText}
            </Text>
          ) : null}
          {!hint.isScenario ? (
            <button
              type="button"
              aria-expanded={detailOpen}
              aria-label={detailOpen ? "Скрыть подробности из базы знаний" : "Подробнее из базы знаний"}
              data-testid={`hint-kb-more-${hint.id}`}
              onClick={(event) => {
                event.stopPropagation();
                setDetailOpen((current) => !current);
              }}
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 28,
                minHeight: 22,
                marginBottom: 10,
                padding: "0 0 2px",
                color: detailOpen ? t.text.primary : t.text.tertiary,
                fontSize: 16,
                fontWeight: 800,
                lineHeight: 1,
                letterSpacing: "0.04em",
                border: `1px solid ${detailOpen ? shade.borderLeft : t.stroke.tertiary}`,
                borderRadius: 999,
                background: detailOpen ? shade.background : t.fill.secondary,
                cursor: "pointer",
              }}
            >
              ⋯
            </button>
          ) : null}
          {detailOpen && detailText ? (
            <div
              onClick={(event) => event.stopPropagation()}
              style={{
                marginBottom: 12,
                padding: "8px 10px",
                fontSize: 12,
                lineHeight: 1.5,
                color: t.text.primary,
                whiteSpace: "pre-wrap",
                border: `1px solid ${t.stroke.tertiary}`,
                borderRadius: 8,
                background: t.fill.secondary,
              }}
            >
              {detailText}
            </div>
          ) : null}
          <Row gap={6} wrap>
            <Button
              variant="primary"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onInsert(hint.answerText);
              }}
              disabled={disabled}
            >
              Вставить в ответ
            </Button>
            {hint.permalink ? (
              <a
                href={hint.permalink}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  fontSize: 12,
                  color: scheme.accent,
                  textDecoration: "none",
                  padding: "4px 8px",
                }}
              >
                {hint.suzTitle} ↗
              </a>
            ) : (
              <Button variant="ghost" size="sm" onClick={(e) => e.stopPropagation()} disabled>
                {hint.suzTitle}
              </Button>
            )}
          </Row>
          {isExpanded && hint.operatorTip ? (
            <div
              style={{ marginTop: 18, marginBottom: 16 }}
              onClick={(e) => e.stopPropagation()}
            >
              <Callout tone="info" title="Совет оператору">
                <Text style={{ fontSize: 12, lineHeight: 1.45 }}>{hint.operatorTip}</Text>
                <Text style={{ fontSize: 10, color: t.text.tertiary, marginTop: 4 }}>
                  Не вставляется в ответ клиенту
                </Text>
              </Callout>
            </div>
          ) : null}
          {isExpanded && !hint.isScenario ? (
            <div onClick={(e) => e.stopPropagation()}>
              <SuflerFeedbackRow
                t={t}
                scheme={scheme}
                cardId={hint.id}
                disabled={disabled}
                onFeedback={onFeedback}
              />
            </div>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

function ConfirmDialog({
  t,
  titleId,
  title,
  description,
  confirmLabel,
  onCancel,
  onConfirm,
}: {
  t: ArmTheme;
  titleId: string;
  title: string;
  description: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
}): JSX.Element {
  return (
    <div
      role="presentation"
      style={{
        position: "absolute",
        inset: 0,
        background: "rgba(15, 28, 22, 0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 40,
        padding: 24,
      }}
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        style={{
          width: "100%",
          maxWidth: 420,
          background: t.bg.elevated,
          border: `1px solid ${t.stroke.secondary}`,
          borderRadius: 12,
          padding: "20px 22px",
          boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <Text
          id={titleId}
          weight="semibold"
          style={{ fontSize: 16, marginBottom: 10, color: t.text.primary }}
        >
          {title}
        </Text>
        <Text style={{ fontSize: 13, color: t.text.secondary, lineHeight: 1.45, marginBottom: 18 }}>
          {description}
        </Text>
        <Row style={{ gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onCancel}>
            Отмена
          </Button>
          <Button variant="primary" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </Row>
      </div>
    </div>
  );
}

function PromptDialog({
  t,
  scheme,
  titleId,
  title,
  description,
  label,
  value,
  placeholder,
  confirmLabel,
  multiline = false,
  onChange,
  onCancel,
  onConfirm,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  titleId: string;
  title: string;
  description?: string;
  label: string;
  value: string;
  placeholder?: string;
  confirmLabel: string;
  multiline?: boolean;
  onChange: (next: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}): JSX.Element {
  const canSubmit = value.trim().length > 0;
  return (
    <div
      role="presentation"
      style={{
        position: "absolute",
        inset: 0,
        background: "rgba(15, 28, 22, 0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 40,
        padding: 24,
      }}
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        style={{
          width: "100%",
          maxWidth: 460,
          background: t.bg.elevated,
          border: `1px solid ${t.stroke.secondary}`,
          borderRadius: 12,
          padding: "20px 22px",
          boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <Text
          id={titleId}
          weight="semibold"
          style={{ fontSize: 16, marginBottom: 8, color: t.text.primary }}
        >
          {title}
        </Text>
        {description ? (
          <Text style={{ fontSize: 13, color: t.text.secondary, lineHeight: 1.45, marginBottom: 14 }}>
            {description}
          </Text>
        ) : null}
        <Text style={{ fontSize: 12, color: t.text.secondary, marginBottom: 6 }}>{label}</Text>
        {multiline ? (
          <TextArea
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            style={{
              minHeight: 110,
              marginBottom: 16,
              borderColor: scheme.accentWeak,
            }}
          />
        ) : (
          <input
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            autoFocus
            onKeyDown={(event) => {
              if (event.key === "Enter" && canSubmit) {
                event.preventDefault();
                onConfirm();
              }
            }}
            style={{
              width: "100%",
              boxSizing: "border-box",
              marginBottom: 16,
              padding: "10px 12px",
              borderRadius: 8,
              border: `1px solid ${t.stroke.secondary}`,
              background: t.bg.editor,
              color: t.text.primary,
              fontFamily: "inherit",
              fontSize: 13,
              outline: "none",
            }}
          />
        )}
        <Row style={{ gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onCancel}>
            Отмена
          </Button>
          <Button variant="primary" disabled={!canSubmit} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </Row>
      </div>
    </div>
  );
}
function clampWidth(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(value)));
}

function startColumnResize(
  event: { clientX: number; preventDefault: () => void },
  initialWidth: number,
  setWidth: (next: number) => void,
  min: number,
  max: number,
  invert = false,
): void {
  event.preventDefault();
  const startX = event.clientX;
  const handleMove = (moveEvent: MouseEvent) => {
    const delta = moveEvent.clientX - startX;
    setWidth(clampWidth(invert ? initialWidth - delta : initialWidth + delta, min, max));
  };
  const handleUp = () => {
    window.removeEventListener("mousemove", handleMove);
    window.removeEventListener("mouseup", handleUp);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  };
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  window.addEventListener("mousemove", handleMove);
  window.addEventListener("mouseup", handleUp);
}

function ColumnResizeHandle({
  t,
  label,
  onMouseDown,
}: {
  t: ArmTheme;
  label: string;
  onMouseDown: (event: { clientX: number; preventDefault: () => void }) => void;
}): JSX.Element {
  return (
    <div
      role="separator"
      aria-label={label}
      title="Перетащите для изменения ширины"
      onMouseDown={onMouseDown}
      style={{
        width: 12,
        flexShrink: 0,
        alignSelf: "stretch",
        cursor: "col-resize",
        position: "relative",
        zIndex: 5,
        touchAction: "none",
        background: t.fill.secondary,
        borderLeft: `1px solid ${t.stroke.secondary}`,
        borderRight: `1px solid ${t.stroke.secondary}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div aria-hidden style={{ display: "flex", gap: 2, alignItems: "center", height: 24 }}>
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            style={{
              width: 2,
              height: 16,
              borderRadius: 1,
              background: t.stroke.secondary,
            }}
          />
        ))}
      </div>
    </div>
  );
}
const QUEUE_CARD_COLLAPSE_SIZE = 22;
const QUEUE_CARD_COLLAPSE_INSET = 8;
const QUEUE_CARD_ACTION_GAP = 4;
const QUEUE_CARD_RIGHT_PAD = QUEUE_CARD_COLLAPSE_SIZE + QUEUE_CARD_COLLAPSE_INSET + 6;
const QUEUE_CARD_RIGHT_PAD_WITH_TAKE =
  QUEUE_CARD_COLLAPSE_INSET +
  QUEUE_CARD_COLLAPSE_SIZE +
  QUEUE_CARD_ACTION_GAP +
  QUEUE_CARD_COLLAPSE_SIZE +
  6;

/** «Взять диалог / на себя» — рука, не «скачать». */
function TakeDialogIcon({ size = 18 }: { size?: number }): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M7 11.5V7a1.5 1.5 0 0 1 3 0v4"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M10 10.5V5.75a1.5 1.5 0 0 1 3 0V11"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M13 10.75V7a1.5 1.5 0 0 1 3 0v5.5"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M16 12.5v1.25a1.25 1.25 0 0 0 2.5 0V12.5a1.5 1.5 0 0 1 3 0V15a6 6 0 0 1-6 6h-2.75A5.25 5.25 0 0 1 7.5 15.75V13a1.75 1.75 0 0 1 3.5 0v-.75"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function QueueCardCollapseButton({
  t,
  onCollapse,
}: {
  t: ArmTheme;
  onCollapse: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      title="Свернуть карточку"
      aria-label="Свернуть карточку"
      onClick={(event) => {
        event.stopPropagation();
        onCollapse();
      }}
      style={{
        position: "absolute",
        top: QUEUE_CARD_COLLAPSE_INSET,
        right: QUEUE_CARD_COLLAPSE_INSET,
        width: QUEUE_CARD_COLLAPSE_SIZE,
        height: QUEUE_CARD_COLLAPSE_SIZE,
        border: `1px solid ${t.stroke.secondary}`,
        borderRadius: RADIUS_SM,
        background: t.fill.secondary,
        color: t.text.secondary,
        fontSize: 13,
        lineHeight: 1,
        cursor: "pointer",
        padding: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "inherit",
        flexShrink: 0,
        zIndex: 1,
      }}
    >
      —
    </button>
  );
}

function QueueCardTakeButton({
  t,
  scheme,
  disabled,
  busy,
  onAccept,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  disabled?: boolean;
  busy?: boolean;
  onAccept: () => void;
}): JSX.Element {
  const inactive = disabled || busy;
  return (
    <button
      type="button"
      title={
        busy
          ? "Принимаем…"
          : disabled
            ? "Лимит активных диалогов достигнут"
            : "Взять диалог из общей очереди"
      }
      aria-label="Взять диалог"
      disabled={inactive}
      onClick={(event) => {
        event.stopPropagation();
        if (inactive) return;
        onAccept();
      }}
      style={{
        position: "absolute",
        top: QUEUE_CARD_COLLAPSE_INSET,
        right:
          QUEUE_CARD_COLLAPSE_INSET +
          QUEUE_CARD_COLLAPSE_SIZE +
          QUEUE_CARD_ACTION_GAP,
        width: QUEUE_CARD_COLLAPSE_SIZE,
        height: QUEUE_CARD_COLLAPSE_SIZE,
        border: `1px solid ${inactive ? t.stroke.secondary : scheme.accent}`,
        borderRadius: RADIUS_SM,
        background: inactive ? t.fill.secondary : scheme.accent,
        color: inactive ? t.text.tertiary : "#fff",
        lineHeight: 1,
        cursor: inactive ? "not-allowed" : "pointer",
        opacity: disabled && !busy ? 0.45 : 1,
        padding: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "inherit",
        flexShrink: 0,
        zIndex: 1,
      }}
    >
      {busy ? (
        <span style={{ fontSize: 11, fontWeight: 700 }}>…</span>
      ) : (
        <TakeDialogIcon size={14} />
      )}
    </button>
  );
}

function QueueSectionHeader({
  t,
  scheme: _scheme,
  title,
  count: _count,
  unreadTotal = 0,
  expanded,
  onToggle,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  title: string;
  count: number;
  unreadTotal?: number;
  expanded: boolean;
  onToggle: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        width: "100%",
        padding: "6px 4px",
        marginBottom: expanded ? 6 : 2,
        border: "none",
        background: "transparent",
        cursor: "pointer",
        fontFamily: "inherit",
        borderRadius: RADIUS_SM,
      }}
    >
      <Row style={{ gap: 6, alignItems: "center", minWidth: 0 }}>
        <Text
          aria-hidden
          style={{
            fontSize: 10,
            color: t.text.secondary,
            width: 14,
            textAlign: "center",
            flexShrink: 0,
            lineHeight: 1,
            fontWeight: 700,
          }}
        >
          {expanded ? "▼" : "▶"}
        </Text>
        <Text weight="semibold" style={{ fontSize: 12, color: t.text.primary, textAlign: "left" }}>
          {title}
        </Text>
        {unreadTotal > 0 ? (
          <span
            aria-label={`Непрочитанных: ${unreadTotal}`}
            style={{
              display: "inline-grid",
              placeItems: "center",
              minWidth: 18,
              height: 18,
              padding: "0 5px",
              borderRadius: 999,
              background: "#007A43",
              color: "#fff",
              fontSize: 11,
              fontWeight: 700,
              fontVariantNumeric: "tabular-nums",
              lineHeight: 1,
              boxShadow: "0 0 0 2px rgba(0,122,67,0.25)",
              animation: "oc-unread-pulse 1.6s ease-in-out infinite",
            }}
          >
            {unreadTotal > 99 ? "99+" : unreadTotal}
          </span>
        ) : null}
      </Row>
    </button>
  );
}

function QueueListRow({
  item,
  t,
  selected,
  onClick,
  nowMs = Date.now(),
}: {
  item: QueueItem;
  t: ArmTheme;
  selected: boolean;
  onClick: () => void;
  nowMs?: number;
}): JSX.Element {
  const resolved = resolveQueueWait(item, nowMs);
  const showTimer = resolved.wait && resolved.wait !== "—";

  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 8,
        padding: "5px 8px",
        borderBottom: `1px solid ${t.stroke.secondary}`,
        background: selected ? t.fill.tertiary : "transparent",
        cursor: "pointer",
        transition: "background 160ms ease",
      }}
    >
      <Row style={{ gap: 6, alignItems: "flex-start", minWidth: 0, flex: 1 }}>
            {resolved.urgent && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: slaToneColor(resolved.slaTone),
              display: "inline-block",
              flexShrink: 0,
              marginTop: 5,
            }}
          />
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <Text
            style={{
              fontSize: 12,
              color: selected ? t.text.primary : t.text.secondary,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {item.name}
          </Text>
          {item.readOnly ? (
            <Row style={{ gap: 4, marginTop: 2 }}>
              <Pill tone="info" size="sm">
                только просмотр
              </Pill>
            </Row>
          ) : null}
          {item.operatorName ? (
            <Text
              style={{
                fontSize: 10,
                color: t.text.tertiary,
                marginTop: 2,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {item.operatorName}
            </Text>
          ) : null}
        </div>
      </Row>
      {showTimer ? (
        resolved.slaTone ? (
          <SlaWaitPill wait={resolved.wait} slaTone={resolved.slaTone} />
        ) : (
          <Pill tone={resolved.urgent ? "warning" : "neutral"} size="sm">
            {resolved.wait}
          </Pill>
        )
      ) : null}
    </div>
  );
}

function QueueCard({
  item,
  t,
  scheme,
  selected,
  onSelect,
  onCollapse,
  nowMs = Date.now(),
  onAccept,
  acceptDisabled,
  acceptBusy,
}: {
  item: QueueItem;
  t: ArmTheme;
  scheme: SchemePalette;
  selected: boolean;
  onSelect: () => void;
  onCollapse: () => void;
  nowMs?: number;
  onAccept?: () => void;
  acceptDisabled?: boolean;
  acceptBusy?: boolean;
}): JSX.Element {
  const resolved = resolveQueueWait(item, nowMs);
  const showTimer = resolved.wait && resolved.wait !== "—";
  const hasMetaRow = showTimer || item.readOnly;
  const rightPad = onAccept ? QUEUE_CARD_RIGHT_PAD_WITH_TAKE : QUEUE_CARD_RIGHT_PAD;

  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      style={{
        position: "relative",
        padding: `10px ${rightPad}px 10px 12px`,
        borderRadius: RADIUS_SM,
        border: `1px solid ${selected ? scheme.accent : t.stroke.secondary}`,
        background: selected ? t.fill.tertiary : t.bg.editor,
        cursor: "pointer",
        transition: "background 160ms ease",
      }}
    >
      {onAccept ? (
        <QueueCardTakeButton
          t={t}
          scheme={scheme}
          disabled={acceptDisabled}
          busy={acceptBusy}
          onAccept={onAccept}
        />
      ) : null}
      <QueueCardCollapseButton t={t} onCollapse={onCollapse} />
      {hasMetaRow ? (
        <Row
          style={{
            alignItems: "center",
            gap: 6,
            marginBottom: 6,
            minHeight: QUEUE_CARD_COLLAPSE_SIZE,
            flexWrap: "wrap",
          }}
        >
          {showTimer ? (
            resolved.slaTone ? (
              <SlaWaitPill wait={resolved.wait} slaTone={resolved.slaTone} />
            ) : (
              <Pill tone={resolved.urgent ? "warning" : "neutral"} size="sm">
                {resolved.wait}
              </Pill>
            )
          ) : null}
          {item.readOnly ? (
            <Pill tone="info" size="sm">
              только просмотр
            </Pill>
          ) : null}
        </Row>
      ) : null}
      <Row style={{ gap: 8, alignItems: "flex-start", minWidth: 0 }}>
        {resolved.urgent && (
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: slaToneColor(resolved.slaTone),
              display: "inline-block",
              flexShrink: 0,
              marginTop: 4,
            }}
          />
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <Row style={{ gap: 6, alignItems: "center", minWidth: 0 }}>
            <Text
              weight="semibold"
              style={{
                fontSize: 13,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                minWidth: 0,
              }}
            >
              {item.name}
            </Text>
            {item.unreadCount && item.unreadCount > 0 && !selected ? (
              <span
                aria-label={`Непрочитанных: ${item.unreadCount}`}
                style={{
                  flexShrink: 0,
                  minWidth: 18,
                  height: 18,
                  padding: "0 5px",
                  borderRadius: 999,
                  background: scheme.badge,
                  color: "#fff",
                  fontSize: 11,
                  fontWeight: 700,
                  display: "inline-grid",
                  placeItems: "center",
                  lineHeight: 1,
                }}
              >
                {item.unreadCount > 99 ? "99+" : item.unreadCount}
              </span>
            ) : null}
          </Row>
          {item.operatorName ? (
            <Text style={{ fontSize: 11, color: t.text.secondary, marginTop: 2 }}>{item.operatorName}</Text>
          ) : null}
        </div>
      </Row>
      <div style={{ overflow: "hidden" }}>
        <Row style={{ gap: 6, marginTop: 6, flexWrap: "wrap" }}>
          <Pill tone="info" size="sm">
            {item.channel}
          </Pill>
          {item.result && (
            <Pill
              size="sm"
              tone={
                item.result === "offline" || item.result === "closed" ? "warning" : "neutral"
              }
            >
              {item.result === "offline"
                ? "offline"
                : item.result === "closed"
                  ? "закрыт"
                  : "отказ"}
            </Pill>
          )}
          {item.dept ? (
            <Text style={{ fontSize: 11, color: t.text.secondary }}>{item.dept}</Text>
          ) : null}
        </Row>
        <Text
          style={{
            fontSize: 12,
            color: t.text.secondary,
            marginTop: 6,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {item.preview}
        </Text>
      </div>
    </div>
  );
}

function AvatarCircle({
  initials,
  background,
  color = "#fff",
}: {
  initials: string;
  background: string;
  color?: string;
}): JSX.Element {
  return (
    <div
      style={{
        width: 28,
        height: 28,
        borderRadius: 14,
        background,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 10,
        fontWeight: 600,
        color,
        flexShrink: 0,
        marginTop: 2,
      }}
    >
      {initials}
    </div>
  );
}

function ReadReceiptMarks({
  color,
  status,
}: {
  color: string;
  status: ReceiptStatus;
}): JSX.Element {
  return (
    <span
      aria-label={status === "read" ? "Прочитано" : "Доставлено"}
      title={status === "read" ? "Прочитано" : "Доставлено"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        marginLeft: 3,
        color,
        fontSize: 11,
        lineHeight: 1,
        fontWeight: 700,
        gap: 0,
      }}
    >
      <span aria-hidden style={{ marginRight: status === "read" ? -6 : 0 }}>
        ✓
      </span>
      {status === "read" ? <span aria-hidden>✓</span> : null}
    </span>
  );
}

function messageCaption(text: string, attachmentName?: string): string {
  if (!attachmentName) return text;
  const fileLabel = `Файл: ${attachmentName}`;
  if (!text || text === fileLabel || text === `Файл: ${attachmentName}`) return "";
  return text;
}

function MessageBubble({
  t,
  scheme,
  side,
  text,
  time,
  label,
  avatarInitials,
  avatarColor,
  receiptStatus,
  quotedText,
  attachmentName,
  attachmentDownloadable,
  onDownloadAttachment,
  isDeleted,
  editedAt,
  onQuote,
  onEdit,
  onDelete,
  isHistory,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  side: "client" | "operator" | "system";
  text: string;
  time?: string;
  label?: string;
  avatarInitials?: string;
  avatarColor?: string;
  receiptStatus?: ReceiptStatus;
  quotedText?: string;
  attachmentName?: string;
  attachmentDownloadable?: boolean;
  onDownloadAttachment?: () => void;
  isDeleted?: boolean;
  editedAt?: string | null;
  onQuote?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  isHistory?: boolean;
}): JSX.Element {
  if (side === "system") {
    return (
      <Text
        style={{
          textAlign: "center",
          fontSize: 11,
          color: t.text.tertiary,
          padding: "8px 0",
          opacity: isHistory ? 0.85 : 1,
        }}
      >
        {text}
      </Text>
    );
  }
  const isOp = side === "operator";
  const avatarBg = avatarColor ?? (isOp ? scheme.accentControl : scheme.accentWeak);
  const avatarFg = isOp ? "#fff" : scheme.accentControl;
  const caption = isDeleted ? "Сообщение удалено" : messageCaption(text, attachmentName);
  const displayText = caption || (attachmentName && !isDeleted ? "" : text);
  const hasActions = !!(onQuote || onEdit || onDelete);
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isOp ? "flex-end" : "flex-start",
        gap: 8,
        alignItems: "flex-start",
      }}
    >
      {!isOp && avatarInitials ? (
        <AvatarCircle initials={avatarInitials} background={avatarBg} color={avatarFg} />
      ) : null}
      <div
        style={{
          maxWidth: "78%",
          padding: "10px 14px 8px",
          borderRadius: 12,
          borderBottomRightRadius: isOp ? 4 : 12,
          borderBottomLeftRadius: isOp ? 12 : 4,
          background: isOp ? scheme.headerBg : t.bg.editor,
          border: `1px solid ${isOp ? scheme.accent : t.stroke.secondary}`,
          display: "flex",
          flexDirection: "column",
          gap: 0,
          opacity: isDeleted || isHistory ? 0.65 : 1,
        }}
      >
        {label ? (
          <Text
            style={{
              fontSize: 11,
              lineHeight: 1.3,
              color: t.text.tertiary,
              marginBottom: 6,
            }}
          >
            {label}
          </Text>
        ) : null}
        {quotedText ? (
          <div
            style={{
              fontSize: 11,
              lineHeight: 1.35,
              color: t.text.secondary,
              borderLeft: `3px solid ${scheme.accentWeak}`,
              paddingLeft: 8,
              marginBottom: 8,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {quotedText}
          </div>
        ) : null}
        {displayText ? (
          <Text
            style={{
              fontSize: 13,
              lineHeight: 1.45,
              color: t.text.primary,
              fontWeight: 600,
              fontStyle: isDeleted ? "italic" : "normal",
            }}
          >
            {displayText}
          </Text>
        ) : null}
        {attachmentName && !isDeleted ? (
          attachmentDownloadable && onDownloadAttachment ? (
            <button
              type="button"
              onClick={onDownloadAttachment}
              style={{
                alignSelf: "flex-start",
                marginTop: 6,
                padding: "4px 8px",
                borderRadius: 6,
                border: `1px solid ${scheme.accentWeak}`,
                background: t.fill.secondary,
                color: scheme.accentControl,
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              📎 Скачать: {attachmentName}
            </button>
          ) : (
            <Text style={{ fontSize: 11, color: t.text.secondary, marginTop: 6 }}>
              📎 {attachmentName} (недоступно для скачивания)
            </Text>
          )
        ) : null}
        {time || hasActions ? (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              alignItems: "center",
              marginTop: 8,
              fontSize: 10,
              lineHeight: 1,
              color: t.text.tertiary,
              gap: 6,
              flexWrap: "wrap",
            }}
          >
            {hasActions ? (
              <Row style={{ gap: 4, marginRight: "auto" }}>
                {onQuote && !isDeleted ? (
                  <Button variant="ghost" size="sm" style={{ fontSize: 10, padding: "0 4px" }} onClick={onQuote}>
                    Ответить
                  </Button>
                ) : null}
                {onEdit && !isDeleted ? (
                  <Button variant="ghost" size="sm" style={{ fontSize: 10, padding: "0 4px" }} onClick={onEdit}>
                    ✎
                  </Button>
                ) : null}
                {onDelete && !isDeleted ? (
                  <Button variant="ghost" size="sm" style={{ fontSize: 10, padding: "0 4px" }} onClick={onDelete}>
                    ✕
                  </Button>
                ) : null}
              </Row>
            ) : null}
            {editedAt && !isDeleted ? (
              <span style={{ fontStyle: "italic", marginRight: 2 }}>изм.</span>
            ) : null}
            {time ? <span>{time}</span> : null}
            {receiptStatus && isOp && !isDeleted ? (
              <ReadReceiptMarks color={scheme.accentControl} status={receiptStatus} />
            ) : null}
          </div>
        ) : null}
      </div>
      {isOp && avatarInitials ? (
        <AvatarCircle initials={avatarInitials} background={avatarBg} color={avatarFg} />
      ) : null}
    </div>
  );
}

export function ArmOverlayMenu({
  t,
  scheme,
  open,
  armRole,
  menuContext = "operate",
  activeId,
  onSelect,
  onClose,
  badges,
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  open: boolean;
  armRole: ArmRole;
  menuContext?: ArmMenuContext;
  activeId: ArmStatsTab;
  onSelect: (id: ArmStatsTab) => void;
  onClose: () => void;
  badges?: Partial<Record<ArmStatsTab, number>>;
}): JSX.Element {
  const items = armMenuItemsForRole(armRole, menuContext);
  return (
    <div
      aria-hidden={!open}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 80,
        pointerEvents: open ? "auto" : "none",
      }}
    >
      <button
        type="button"
        aria-label="Закрыть меню"
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          border: "none",
          margin: 0,
          padding: 0,
          background: open ? "rgba(20, 40, 30, 0.28)" : "transparent",
          opacity: open ? 1 : 0,
          transition: "opacity 0.22s ease",
          cursor: "pointer",
        }}
      />
      <aside
        id="arm-stats-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Меню АРМ"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          bottom: 0,
          width: "min(300px, 86vw)",
          display: "flex",
          flexDirection: "column",
          background: t.bg.elevated,
          borderRight: `1px solid ${scheme.accentWeak}`,
          boxShadow: open ? "8px 0 28px rgba(0,0,0,0.16)" : "none",
          transform: open ? "translateX(0)" : "translateX(-105%)",
          transition: "transform 0.26s cubic-bezier(0.22, 1, 0.36, 1)",
          overflow: "hidden",
          zIndex: 1,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            padding: "16px 18px 14px",
            background: scheme.headerBg,
            borderBottom: `1px solid ${scheme.accentWeak}`,
          }}
        >
          <Text
            weight="semibold"
            style={{
              fontSize: 17,
              letterSpacing: "-0.03em",
              color: t.text.primary,
              lineHeight: 1.2,
            }}
          >
            Меню АРМ
          </Text>
          <button
            type="button"
            aria-label="Закрыть"
            onClick={onClose}
            style={{
              width: 28,
              height: 28,
              border: "none",
              borderRadius: 8,
              background: "transparent",
              color: t.text.tertiary,
              cursor: "pointer",
              fontSize: 22,
              lineHeight: 1,
              fontFamily: "inherit",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "background 120ms ease, color 120ms ease",
            }}
            onMouseEnter={(event) => {
              event.currentTarget.style.background = t.fill.tertiary;
              event.currentTarget.style.color = t.text.primary;
            }}
            onMouseLeave={(event) => {
              event.currentTarget.style.background = "transparent";
              event.currentTarget.style.color = t.text.tertiary;
            }}
          >
            ×
          </button>
        </div>
        <nav
          aria-label="Разделы меню"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 8,
            padding: 12,
            overflowY: "auto",
            flex: 1,
            minHeight: 0,
          }}
        >
          {items.map((item) => {
            const active = activeId === item.id;
            const badge = badges?.[item.id] ?? 0;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelect(item.id)}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  gap: 3,
                  width: "100%",
                  padding: "12px 14px",
                  border: `1px solid ${active ? scheme.accent : t.stroke.secondary}`,
                  borderRadius: 10,
                  background: active ? t.fill.tertiary : t.bg.editor,
                  color: t.text.primary,
                  textAlign: "left",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  boxShadow: active ? `inset 3px 0 0 ${scheme.accentControl}` : undefined,
                  transition: "background 0.15s ease, border-color 0.15s ease",
                }}
              >
                <span
                  style={{
                    fontSize: 14,
                    fontWeight: 700,
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                    width: "100%",
                    justifyContent: "space-between",
                  }}
                >
                  <span>{item.label}</span>
                  {badge > 0 ? (
                    <span
                      aria-label={`Непрочитано: ${badge}`}
                      style={{
                        minWidth: 20,
                        height: 20,
                        padding: "0 6px",
                        borderRadius: 999,
                        background: scheme.badge,
                        color: "#fff",
                        fontSize: 11,
                        fontWeight: 700,
                        display: "inline-grid",
                        placeItems: "center",
                        lineHeight: 1,
                      }}
                    >
                      {badge > 99 ? "99+" : badge}
                    </span>
                  ) : null}
                </span>
                <span style={{ fontSize: 11, color: t.text.secondary, lineHeight: 1.35 }}>{item.hint}</span>
              </button>
            );
          })}
        </nav>
      </aside>
    </div>
  );
}

export function ArmOperatorView({
  t,
  scheme,
  selectedQueue,
  onSelectQueue,
  reply,
  suflerSuggestionText,
  onReplyChange,
  onInsertSufler,
  toast,
  onClearToast,
  presence,
  onPresenceChange,
  viewMode,
  onViewModeChange,
  closeTopic,
  onCloseTopicChange,
  operatorName = "Иванов И.И.",
  statsDrawerOpen: statsDrawerOpenProp,
  onStatsDrawerOpenChange,
  armRole: armRoleProp = "operator",
  viewOnly = false,
  allowTransferInView = false,
  actorName = "",
}: {
  t: ArmTheme;
  scheme: SchemePalette;
  selectedQueue: string;
  onSelectQueue: (id: string) => void;
  reply: string;
  suflerSuggestionText: string;
  onReplyChange: (v: string) => void;
  onInsertSufler: (answerText: string) => void;
  toast: string | null;
  onClearToast: () => void;
  presence: OperatorPresence;
  onPresenceChange: (next: OperatorPresence) => void;
  viewMode: ArmView;
  onViewModeChange: (next: ArmView) => void;
  closeTopic: string;
  onCloseTopicChange: (next: string) => void;
  /** Observed / current ARM operator display name (queue filter + labels). */
  operatorName?: string;
  statsDrawerOpen?: boolean;
  onStatsDrawerOpenChange?: (open: boolean) => void;
  armRole?: ArmRole;
  viewOnly?: boolean;
  allowTransferInView?: boolean;
  /** Logged-in user who may take over (supervisor). Falls back to operatorName. */
  actorName?: string;
}): JSX.Element {
  const armRole: ArmRole = armRoleProp;
  const actingName = (actorName || operatorName).trim() || operatorName;
  const operatorInitials = initialsFromDisplayName(
    viewOnly ? actingName : operatorName,
  );
  const menuContext: ArmMenuContext = viewOnly ? "view" : "operate";
  const [closedDialogIds, setClosedDialogIds] = useState<Record<string, boolean>>({});
  const [blockedDialogIds, setBlockedDialogIds] = useState<Record<string, boolean>>({});
  const [summaryHistory, setSummaryHistory] = useState<SummaryHistoryData>(EMPTY_SUMMARY_HISTORY);
  const [transferOperators, setTransferOperators] = useState<ChatOperator[]>([]);
  const [transferDepartment, setTransferDepartment] = useState("");
  const [pendingAttachment, setPendingAttachment] = useState<File | null>(null);
  const [queuesReady, setQueuesReady] = useState(false);
  const [liveWaiting, setLiveWaiting] = useState<QueueItem[]>([]);
  const [liveShared, setLiveShared] = useState<QueueItem[]>([]);
  const [liveMine, setLiveMine] = useState<QueueItem[]>([]);
  const [liveColleagues, setLiveColleagues] = useState<QueueItem[]>([]);
  const [liveOffline, setLiveOffline] = useState<QueueItem[]>([]);
  const [liveClosed, setLiveClosed] = useState<QueueItem[]>([]);
  const [liveInitiated, setLiveInitiated] = useState<QueueItem[]>([]);
  const [lineOpen, setLineOpen] = useState(true);
  const [liveMessages, setLiveMessages] = useState<OnlineChatMessage[]>([]);
  const [clientDraft, setClientDraft] = useState("");
  const [quoteMessage, setQuoteMessage] = useState<OnlineChatMessage | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateCategory, setTemplateCategory] = useState<string | null>(null);
  const [composerTemplates, setComposerTemplates] = useState(() => loadReplyTemplates(operatorName));
  const [transferDialogOpen, setTransferDialogOpen] = useState(false);
  const [transferTargetKind, setTransferTargetKind] = useState<"operator" | "supervisor">("operator");
  const [transferOperatorName, setTransferOperatorName] = useState("");
  const [dialogTopics, setDialogTopics] = useState<DialogTopicNode[]>([]);
  const [selectedCloseTopicId, setSelectedCloseTopicId] = useState("");
  const [recommendedTopicId, setRecommendedTopicId] = useState("");
  const [recommendedTopicPath, setRecommendedTopicPath] = useState("");
  const [liveSuflerHints, setLiveSuflerHints] = useState<SuflerHintData[]>([]);
  const [liveSuflerRaw, setLiveSuflerRaw] = useState<SuflerHint[]>([]);
  const [suflerRequestId, setSuflerRequestId] = useState("");
  const [suflerQuery, setSuflerQuery] = useState("");
  const [suflerLoading, setSuflerLoading] = useState(false);
  const [suflerError, setSuflerError] = useState("");
  // Distinguish "not in KB" (calm, no button) from "sufler down" (warning + report button).
  const [suflerReportVisible, setSuflerReportVisible] = useState(false);
  const [suflerReportSent, setSuflerReportSent] = useState(false);
  // Supervisor/admin banner when an operator reports a sufler outage.
  const [suflerOutageNotice, setSuflerOutageNotice] = useState<
    { operatorName: string; detail: string; query: string; at: string } | null
  >(null);
  const [suflerScenarioPath, setSuflerScenarioPath] = useState("");
  const [suflerSuggested, setSuflerSuggested] = useState<
    NonNullable<SuggestResponse["suggested_scenario"]> | null
  >(null);
  const kb = useKnowledgeBaseSelection();
  const kbSlugsKey = kb.slugs.join("|");
  const [assignmentGraceUntil, setAssignmentGraceUntil] = useState<number | null>(null);
  const [unreadByDialog, setUnreadByDialog] = useState<Record<string, number>>({});
  const [acceptingDialogId, setAcceptingDialogId] = useState<string | null>(null);
  const [operatorCapacity, setOperatorCapacity] = useState(3);
  const topicScoreByDialogRef = useRef<Record<string, Record<string, number>>>({});
  const suflerTurnKeyRef = useRef<string>("");
  /** Snapshot summary once per dialog — must not change mid-conversation. */
  const summaryByDialogRef = useRef<Record<string, SummaryHistoryData>>({});
  const [editMessageTarget, setEditMessageTarget] = useState<OnlineChatMessage | null>(null);
  const [editMessageText, setEditMessageText] = useState("");
  const [deleteMessageTarget, setDeleteMessageTarget] = useState<OnlineChatMessage | null>(null);
  const [clientBlocks, setClientBlocks] = useState<{ id: string; phone_normalized: string }[]>([]);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [voiceRecording, setVoiceRecording] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // Auto-scroll only when the operator is already near the bottom. Prevents the
  // periodic queue refresh from yanking the view down while reading history.
  const isAtBottomRef = useRef(true);
  const lastDialogIdRef = useRef<string | undefined>(undefined);
  const readMessageIdsRef = useRef<Set<string>>(new Set());
  const selectedQueueRef = useRef(selectedQueue);
  const sharedPeekRef = useRef(false);
  selectedQueueRef.current = selectedQueue;

  useEffect(() => {
    // Sub-second ticks keep the second boundary crisp without UI stutter on refresh.
    const timer = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false
    void fetchDialogTopics(true)
      .then((items) => {
        if (!cancelled) setDialogTopics(items)
      })
      .catch(() => {
        if (!cancelled) setDialogTopics([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!closeTopic) {
      setSelectedCloseTopicId("")
      return
    }
    const leaves = flattenTopicLeaves(dialogTopics)
    const found = leaves.find((item) => item.path === closeTopic)
    setSelectedCloseTopicId(found?.id || "")
  }, [closeTopic, dialogTopics])

  const scrollMessagesToEnd = useCallback((behavior: ScrollBehavior = "smooth") => {
    const scroller = messagesScrollRef.current;
    if (scroller) {
      scroller.scrollTo({ top: scroller.scrollHeight, behavior });
      isAtBottomRef.current = true;
      return;
    }
    messagesEndRef.current?.scrollIntoView({ behavior, block: "end" });
    isAtBottomRef.current = true;
  }, []);

  const handleMessagesScroll = useCallback(() => {
    const scroller = messagesScrollRef.current;
    if (!scroller) return;
    const distanceFromBottom =
      scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    // Treat "within ~80px of the bottom" as pinned so tiny layout shifts still autoscroll.
    isAtBottomRef.current = distanceFromBottom <= 80;
  }, []);

  const refreshLiveQueues = useCallback(async () => {
    try {
      const [
        waiting,
        activeDialogs,
        closedDialogs,
        initiatedDialogs,
        offlineWaiting,
        offlineActive,
      ] = await Promise.all([
        listDialogs("waiting"),
        listDialogs("active"),
        listDialogs("closed"),
        listDialogs(undefined, { initiated_by: "operator" }),
        listDialogs("waiting", { client_online: false }),
        listDialogs("active", { client_online: false }),
      ]);

      // Общая очередь — все неназначенные (waiting), и для оператора, и в режиме просмотра.
      setLiveShared(
        waiting.map((dialog, index) => dialogToQueueItem(dialog, { active: index === 0 })),
      );

      if (viewOnly) {
        // Observation: shared queue stays visible; selected operator's dialogs in colleagues.
        const observed = activeDialogs.filter(
          (dialog) => dialog.operator_name === operatorName,
        );
        setLiveWaiting([]);
        setLiveMine([]);
        setLiveColleagues(
          observed.map((dialog, index) => ({
            ...dialogToQueueItem(dialog, { active: index === 0 }),
            readOnly: true,
            operatorName: dialog.operator_name ?? operatorName,
          })),
        );
      } else if (armRole === "supervisor") {
        // Supervisor own ARM: only dialogs already owned by supervisor (take-over / transfer).
        // Orphan / unassigned actives must not appear as writable "mine".
        const mineActive = activeDialogs.filter(
          (dialog) => dialog.operator_name === operatorName,
        );
        const awaitingReply = mineActive.filter((dialog) => dialog.needs_reply);
        const mineIdle = mineActive.filter((dialog) => !dialog.needs_reply);
        setLiveWaiting(
          awaitingReply.map((dialog, index) => dialogToQueueItem(dialog, { active: index === 0 })),
        );
        setLiveMine(mineIdle.map((dialog, index) => dialogToQueueItem(dialog, { active: index === 0 })));
        setLiveColleagues([]);
      } else {
        const mineActive = activeDialogs.filter(
          (dialog) => dialog.operator_name === operatorName,
        );
        // Ожидают ответа — мои active, где последнее сообщение от клиента.
        const awaitingReply = mineActive.filter((dialog) => dialog.needs_reply);
        // В диалоге со мной — мои active без неотвеченного сообщения клиента.
        const mineIdle = mineActive.filter((dialog) => !dialog.needs_reply);
        setLiveWaiting(
          awaitingReply.map((dialog, index) => dialogToQueueItem(dialog, { active: index === 0 })),
        );
        setLiveMine(mineIdle.map((dialog, index) => dialogToQueueItem(dialog, { active: index === 0 })));
        // Операторам диалоги коллег недоступны — только супервизору.
        setLiveColleagues([]);
      }

      const offlineMerged = [...offlineWaiting, ...offlineActive];
      const offlineUnique = Array.from(
        new Map(offlineMerged.map((dialog) => [dialog.id, dialog])).values(),
      );
      setLiveOffline(
        offlineUnique.map((dialog) => ({
          ...dialogToQueueItem(dialog),
          result: "offline" as const,
        })),
      );

      setLiveClosed(
        closedDialogs.slice(0, 20).map((dialog) => ({
          ...dialogToQueueItem(dialog),
          result: "closed" as const,
        })),
      );

      setLiveInitiated(
        viewOnly
          ? []
          : initiatedDialogs
              .filter((dialog) => !dialog.operator_name || dialog.operator_name === operatorName)
              .map((dialog) => dialogToQueueItem(dialog)),
      );
      if (viewOnly) {
        setLiveOffline([]);
        setLiveClosed([]);
      }
    } catch {
      /* Backend may be offline — show empty live queues, never mock clients. */
      setLiveWaiting([]);
      setLiveShared([]);
      setLiveMine([]);
      setLiveColleagues([]);
      setLiveOffline([]);
      setLiveClosed([]);
      setLiveInitiated([]);
    } finally {
      setQueuesReady(true);
    }
  }, [operatorName, viewOnly, armRole]);

  useEffect(() => {
    let cancelled = false;
    const syncSchedule = () => {
      void getWorkScheduleStatus()
        .then((status) => {
          if (cancelled) return;
          setLineOpen(status.is_open);
        })
        .catch(() => undefined);
    };
    syncSchedule();
    const timer = window.setInterval(syncSchedule, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    void refreshLiveQueues();
    const timer = window.setInterval(() => {
      void refreshLiveQueues();
    }, 2000);
    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket(onlineChatArmWsUrl());
      socket.onmessage = (event) => {
        void refreshLiveQueues();
        try {
          const data = JSON.parse(event.data) as {
            type?: string;
            payload?: OnlineChatMessage & {
              dialog_id?: string;
              message_ids?: string[];
              messages?: OnlineChatMessage[];
              speaker?: string;
              text?: string;
              unread_count?: number;
              recipient_name?: string;
              recipient_id?: string;
            };
          };
          if (data.type === "internal.message.created" || data.type === "internal.messages.read") {
            void getInternalUnreadCount(operatorName)
              .then((result) => setInternalUnread(result.unread_count))
              .catch(() => undefined);
          }
          if (data.type === "sufler.outage") {
            const notice = (data.payload || {}) as {
              operator_name?: string;
              detail?: string;
              query?: string;
              reported_at?: string;
            };
            setSuflerOutageNotice({
              operatorName: notice.operator_name || "оператор",
              detail: notice.detail || "Суфлёр недоступен",
              query: notice.query || "",
              at: notice.reported_at || new Date().toISOString(),
            });
            return;
          }
          const dialogId = data.payload?.dialog_id;
          if (data.type === "typing.start") {
            if (
              data.payload?.speaker === "client" &&
              dialogId === selectedQueueRef.current
            ) {
              const draftPayload = data.payload as { draft?: string; text?: string };
              setClientDraft(draftPayload.draft || draftPayload.text || "…");
            }
            return;
          }
          if (data.type === "typing.stop") {
            if (dialogId === selectedQueueRef.current) setClientDraft("");
            return;
          }
          if (data.type === "messages.read" && data.payload?.message_ids?.length) {
            const ids = data.payload.message_ids;
            ids.forEach((id) => readMessageIdsRef.current.add(id));
            if (!dialogId || dialogId === selectedQueueRef.current) {
              setLiveMessages((prev) =>
                prev.map((item) =>
                  ids.includes(item.id)
                    ? { ...item, receipt_status: "read" as ReceiptStatus }
                    : item,
                ),
              );
            }
            return;
          }
          if (data.type === "message.created" && data.payload?.id) {
            const incoming = data.payload as OnlineChatMessage;
            const msgDialogId = dialogId || incoming.dialog_id;
            if (
              incoming.speaker === "client"
              && msgDialogId
              && msgDialogId !== selectedQueueRef.current
              && !sharedPeekRef.current
            ) {
              setUnreadByDialog((prev) => ({
                ...prev,
                [msgDialogId]: (prev[msgDialogId] || 0) + 1,
              }));
            }
            if (msgDialogId && msgDialogId !== selectedQueueRef.current) return;
            const withReceipt =
              incoming.receipt_status === "read" ||
              readMessageIdsRef.current.has(incoming.id)
                ? { ...incoming, receipt_status: "read" as ReceiptStatus }
                : incoming;
            setLiveMessages((prev) => {
              if (prev.some((item) => item.id === withReceipt.id)) {
                return prev.map((item) =>
                  item.id === withReceipt.id ? { ...item, ...withReceipt } : item,
                );
              }
              return [...prev, withReceipt];
            });
            if (incoming.speaker === "client" && msgDialogId && !sharedPeekRef.current) {
              void markDialogRead(msgDialogId, "operator").catch(() => {});
            }
            return;
          }
          if (dialogId && dialogId !== selectedQueueRef.current) return;
          if (data.type === "message.updated" && data.payload?.id) {
            const updated = data.payload as OnlineChatMessage;
            setLiveMessages((prev) =>
              prev.map((item) =>
                item.id === updated.id
                  ? {
                      ...item,
                      ...updated,
                      receipt_status:
                        updated.receipt_status ||
                        (readMessageIdsRef.current.has(updated.id)
                          ? "read"
                          : item.receipt_status),
                    }
                  : item,
              ),
            );
            return;
          }
        } catch {
          /* ignore malformed events */
        }
      };
    } catch {
      /* WebSocket unavailable */
    }
    return () => {
      window.clearInterval(timer);
      socket?.close();
    };
  }, [refreshLiveQueues, operatorName]);

  const liveMode = queuesReady;

  const liveSectionItems: Partial<Record<QueueSectionId, QueueItem[]>> = useMemo(
    () => {
      const withUnread = (items: QueueItem[]) =>
        items.map((item) => ({
          ...item,
          unreadCount: unreadByDialog[item.id] || (item.needsReply ? 1 : 0) || undefined,
        }));
      // waiting (нужен ответ) + mine → одна секция «В диалоге со мной»
      const mineMerged = withUnread([
        ...liveWaiting,
        ...liveMine.filter((item) => !liveWaiting.some((wait) => wait.id === item.id)),
      ]);
      return {
        waiting: [],
        mine: mineMerged,
        colleagues: withUnread(liveColleagues),
        offline: liveOffline,
        closed: liveClosed,
        shared: withUnread(liveShared),
        initiated: liveInitiated,
      };
    },
    [
      liveWaiting,
      liveShared,
      liveMine,
      liveColleagues,
      liveOffline,
      liveClosed,
      liveInitiated,
      unreadByDialog,
    ],
  );

  const visibleSections = useMemo(() => {
    const sections = queueSectionsForRole(armRole);
    return sections.map((section) => {
      const items = liveMode ? (liveSectionItems[section.id] ?? []) : [];
      return {
        ...section,
        items,
        count: items.length,
        defaultExpanded: items.length > 0,
      };
    });
  }, [armRole, liveMode, liveSectionItems]);

  const remainingDialogs = visibleSections
    .flatMap((section) => section.items)
    .filter((item) => !closedDialogIds[item.id]);
  const active =
    remainingDialogs.find((q) => q.id === selectedQueue) ??
    remainingDialogs.find((q) => q.live) ??
    remainingDialogs[0] ??
    null;
  const hasActiveDialog = !!active;
  const isSharedQueuePeek =
    !!active?.live && liveShared.some((item) => item.id === active.id);
  sharedPeekRef.current = isSharedQueuePeek;
  // Supervisor may write only in dialogs they already own (take-over / transfer).
  const supervisorOwnsActive =
    armRole === "supervisor" &&
    !!active?.live &&
    !!active.operatorName &&
    active.operatorName === actingName;
  const isReadOnly =
    viewOnly ||
    viewMode === "colleague" ||
    isSharedQueuePeek ||
    (armRole === "supervisor" && !supervisorOwnsActive) ||
    (!!active && active.live === false);
  const canTakeOverDialog =
    armRole === "supervisor" &&
    isReadOnly &&
    !!active?.live &&
    !isSharedQueuePeek &&
    !!active.operatorName &&
    active.operatorName !== actingName;
  const canTransferDespiteView =
    canTakeOverDialog ||
    ((viewOnly || viewMode === "colleague") && allowTransferInView);
  const isClientBlocked = !!(active && blockedDialogIds[active.id]);
  const composerLocked = isReadOnly || isClientBlocked || !hasActiveDialog;

  useEffect(() => {
    const dialogId = active?.id || ""
    setRecommendedTopicId("")
    setRecommendedTopicPath("")
    if (!dialogId) return
    if (!topicScoreByDialogRef.current[dialogId]) {
      topicScoreByDialogRef.current[dialogId] = {}
    }
  }, [active?.id])

  useEffect(() => {
    if (!hasActiveDialog) return;
    const dialogChanged = lastDialogIdRef.current !== active?.id;
    if (dialogChanged) {
      // Switching into a dialog always lands on the latest message.
      lastDialogIdRef.current = active?.id;
      isAtBottomRef.current = true;
      scrollMessagesToEnd("auto");
      return;
    }
    // Otherwise only follow new content when the operator is already at the bottom;
    // never steal their position while they scroll up to read history.
    if (isAtBottomRef.current) {
      scrollMessagesToEnd(liveMessages.length <= 1 ? "auto" : "smooth");
    }
  }, [liveMessages, clientDraft, active?.id, hasActiveDialog, scrollMessagesToEnd]);

  const clientForCard: ClientInfoData = active?.live
    ? {
        ...ACTIVE_CLIENT,
        name: active.name,
        phoneFull: active.phone || "—",
        phoneMasked: active.phone ? maskPhone(active.phone) : "—",
        dialogNo: active.refCode ? `№ ${active.refCode}` : `№ ${dialogRefCode({ id: active.id })}`,
        email:
          active.clientFields?.find((item) => /e-?mail|почт/i.test(item.label))?.value ||
          "—",
        channel: active.channel,
        entryPath: active.entryUrl || ACTIVE_CLIENT.entryPath,
        entryChannel: "Виджет сайта",
        visitorId: active.id.slice(0, 12),
        fields: active.clientFields || [],
      }
    : ACTIVE_CLIENT;

  useEffect(() => {
    setPendingAttachment(null);
  }, [active?.id]);

  useEffect(() => {
    if (!active?.live) {
      setLiveMessages([]);
      setClientDraft("");
      setQuoteMessage(null);
      return;
    }
    let cancelled = false;
    const dialogId = active.id;
    const peekShared = liveShared.some((item) => item.id === dialogId);
    void getDialog(dialogId, { includeHistory: true })
      .then((dialog) => {
        if (!cancelled) {
          const messages = dialog.messages ?? [];
          for (const message of messages) {
            if (message.receipt_status === "read") {
              readMessageIdsRef.current.add(message.id);
            }
          }
          setLiveMessages(messages);
          // Viewing shared-queue dialogs must not mark client messages as read.
          if (!viewOnly && !peekShared) {
            void markDialogRead(dialogId, "operator").catch(() => {});
          }
        }
      })
      .catch(() => {
        if (!cancelled) setLiveMessages([]);
      });

    return () => {
      cancelled = true;
    };
  }, [active?.id, active?.live, liveShared, viewOnly]);

  useEffect(() => {
    void operatorsApi
      .list()
      .then((items) => {
        setTransferOperators(items.filter((item) => item.is_active !== false && item.name));
        const me = items.find((item) => item.name === operatorName);
        if (me?.capacity != null && me.capacity > 0) {
          setOperatorCapacity(me.capacity);
        }
      })
      .catch(() => setTransferOperators([]));
  }, [operatorName]);

  const myActiveCount = liveWaiting.length + liveMine.length;
  const atCapacity = myActiveCount >= operatorCapacity;

  useEffect(() => {
    if (!active?.live || !active.id) {
      setSummaryHistory(EMPTY_SUMMARY_HISTORY);
      return;
    }
    const cached = summaryByDialogRef.current[active.id];
    // Do not keep a stale "first appeal" snapshot — retry until history is found.
    if (cached && !cached.isFirst) {
      setSummaryHistory(cached);
      return;
    }
    let cancelled = false;
    void fetchClientHistory({
      dialogId: active.id,
      phone: active.phone || undefined,
    })
      .then((response) => {
        if (cancelled) return;
        const next = historyToSummary({
          items: response.items ?? [],
          summary: response.summary ?? "",
          detailedSummary: response.detailed_summary ?? "",
          topics: response.summary_topics ?? [],
          blocks: response.detailed_blocks ?? [],
          isFirst: response.is_first,
          previousCount: response.previous_count,
        });
        summaryByDialogRef.current[active.id] = next;
        setSummaryHistory(next);
      })
      .catch(() => {
        if (!cancelled) setSummaryHistory(EMPTY_SUMMARY_HISTORY);
      });
    return () => {
      cancelled = true;
    };
  }, [active?.id, active?.live, active?.phone]);

  // The "current turn" is the trailing run of consecutive client messages
  // (after the last operator/bot/system reply). This lets the sufler treat a
  // question split into single-word messages ("привет" "как открыть" "вклад")
  // as ONE question, while never looking at older topics from the history.
  const currentTurn = useMemo(() => {
    const turn: OnlineChatMessage[] = [];
    for (let i = liveMessages.length - 1; i >= 0; i -= 1) {
      const item = liveMessages[i];
      if (item.is_deleted || item.is_history) continue;
      if (item.speaker === "client") {
        if (item.text.trim()) turn.unshift(item);
        continue;
      }
      // Welcome / offline bot notices and system lines must not wipe the current
      // client question — only an operator reply ends the turn for the sufler.
      if (item.speaker === "operator") break;
    }
    return turn;
  }, [liveMessages]);

  const currentTurnText = useMemo(
    () =>
      currentTurn
        .map((item) => item.text.trim())
        .filter(Boolean)
        .join(" "),
    [currentTurn],
  );
  const currentTurnLastId = currentTurn.length
    ? currentTurn[currentTurn.length - 1].id
    : "";
  const currentTurnCount = currentTurn.length;

  useEffect(() => {
    // Sufler ran but has nothing relevant in the KB — calm notice, no report button.
    const applyNoKnowledge = () => {
      setLiveSuflerHints([]);
      setLiveSuflerRaw([]);
      setSuflerLoading(false);
      setSuflerReportVisible(false);
      setSuflerScenarioPath("");
      setSuflerSuggested(null);
      setSuflerError(SUFLER_NO_KNOWLEDGE_MESSAGE);
    };
    // Sufler itself is down — warning + "Сообщить о проблеме".
    const applyUnavailable = () => {
      setLiveSuflerHints([]);
      setLiveSuflerRaw([]);
      setSuflerLoading(false);
      setSuflerReportVisible(true);
      setSuflerScenarioPath("");
      setSuflerSuggested(null);
      setSuflerError(SUFLER_UNAVAILABLE_MESSAGE);
    };
    const applyIdle = () => {
      setLiveSuflerHints([]);
      setLiveSuflerRaw([]);
      setSuflerLoading(false);
      setSuflerReportVisible(false);
      setSuflerScenarioPath("");
      setSuflerSuggested(null);
      setSuflerError("");
    };

    // Sufler is strictly scoped to the active dialog id (no cross-dialog leakage).
    if (!active?.live) {
      suflerTurnKeyRef.current = "";
      applyIdle();
      return;
    }
    if (active.isTestClient) {
      // Demo: one designated test client showcases the outage + report flow;
      // every other test client shows the ordinary "not in KB" answer.
      suflerTurnKeyRef.current = `${active.id}:test`;
      setSuflerReportSent(false);
      setSuflerQuery(currentTurnText);
      if (testClientNumber(active) === DEMO_SUFLER_OUTAGE_CLIENT_NUMBER) {
        applyUnavailable();
      } else {
        applyNoKnowledge();
      }
      return;
    }
    if (!currentTurnCount || !currentTurnText.trim()) {
      suflerTurnKeyRef.current = "";
      applyIdle();
      return;
    }
    // Key includes the fragment count so each new single-word message re-arms
    // the debounce until the client finishes the current question.
    const turnKey = `${active.id}:${currentTurnLastId}:${currentTurnCount}:${kbSlugsKey}`;
    if (suflerTurnKeyRef.current === turnKey) {
      return;
    }
    const requestKey = turnKey;
    suflerTurnKeyRef.current = requestKey;
    setSuflerReportSent(false);
    setSuflerReportVisible(false);
    setSuflerLoading(true);
    setSuflerError("");
    setSuflerQuery(currentTurnText);

    let timeoutId = 0;
    // Debounce so fragmented single-word messages get batched into one query.
    const debounceId = window.setTimeout(() => {
      if (suflerTurnKeyRef.current !== requestKey) return;
      // Small talk / non-bank: sufler must not react — show "not in KB".
      if (isSuflerChitChat(currentTurnText)) {
        applyNoKnowledge();
        return;
      }
      timeoutId = window.setTimeout(() => {
        if (suflerTurnKeyRef.current === requestKey) {
          applyUnavailable();
        }
      }, 25000);
      // Sufler sees ONLY the current question — never the chat history.
      void requestSuflerSuggest(currentTurnText, 3, {
        channel: "online_chat",
        sessionId: `chat:${active.id}`,
        ...(kb.status === "ready" ? { kbSlugs: kb.slugs } : {}),
      })
        .then((result) => {
          if (suflerTurnKeyRef.current !== requestKey) return;
          window.clearTimeout(timeoutId);
          setSuflerRequestId(result.request_id || "");
          const usable = (result.hints || []).filter(
            (hint) => (hint.relevance_percent ?? hint.relevance_score * 100) > 20,
          );
          if (usable.length) {
            setLiveSuflerRaw(usable);
            setLiveSuflerHints(usable.map(mapApiHintToCard));
            setSuflerReportVisible(false);
            setSuflerError("");
            if (result.scenario?.path?.length) {
              setSuflerScenarioPath(
                `${result.scenario.code} · ${result.scenario.path.join(" → ")}`,
              );
              setSuflerSuggested(null);
            } else {
              setSuflerScenarioPath("");
              setSuflerSuggested(result.suggested_scenario ?? null);
            }
            const articleTitles = usable
              .map((hint) => hint.citations?.[0]?.title?.trim() || "")
              .filter(Boolean)
            if (articleTitles.length && active?.id) {
              void suggestDialogTopic(articleTitles)
                .then((topicResult) => {
                  if (suflerTurnKeyRef.current !== requestKey) return
                  if (!topicResult.topic_id) return
                  const dialogId = active.id
                  const scores = topicScoreByDialogRef.current[dialogId] || {}
                  const avgRelevance = usable.reduce(
                    (sum, hint) => sum + (hint.relevance_percent ?? hint.relevance_score * 100),
                    0,
                  ) / usable.length
                  const weight = Math.max(1, currentTurnCount) * Math.max(0.35, avgRelevance / 100)
                  scores[topicResult.topic_id] = (scores[topicResult.topic_id] ?? 0) + weight
                  topicScoreByDialogRef.current[dialogId] = scores
                  const topEntry = Object.entries(scores).sort((a, b) => b[1] - a[1])[0]
                  if (!topEntry) return
                  const [topId] = topEntry
                  const resolvedTopicPath = topicPathById(dialogTopics, topId) || topicResult.topic_path || ""
                  setRecommendedTopicId(topId)
                  setRecommendedTopicPath(resolvedTopicPath)
                })
                .catch(() => undefined)
            }
          } else if (result.blocked_reason === "sufler_unavailable") {
            applyUnavailable();
          } else {
            // no_relevant_knowledge or only low-relevance hits → nothing in KB.
            applyNoKnowledge();
          }
        })
        .catch(() => {
          if (suflerTurnKeyRef.current !== requestKey) return;
          window.clearTimeout(timeoutId);
          applyUnavailable();
        })
        .finally(() => {
          if (suflerTurnKeyRef.current === requestKey) {
            window.clearTimeout(timeoutId);
            setSuflerLoading(false);
          }
        });
    }, SUFLER_FRAGMENT_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(debounceId);
      window.clearTimeout(timeoutId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    active?.id,
    active?.live,
    active?.isTestClient,
    currentTurnLastId,
    currentTurnCount,
    currentTurnText,
    kbSlugsKey,
    kb.status,
  ]);

  useEffect(() => {
    if (assignmentGraceUntil == null) return;
    setGraceNoticeDismissed(false);
    setExpandedSections((prev) => ({ ...prev, shared: true }));
    if (assignmentGraceUntil <= Date.now()) {
      setAssignmentGraceUntil(null);
      return;
    }
    const timer = window.setInterval(() => {
      if (assignmentGraceUntil <= Date.now()) {
        setAssignmentGraceUntil(null);
        void refreshLiveQueues();
      }
    }, 500);
    return () => window.clearInterval(timer);
  }, [assignmentGraceUntil, refreshLiveQueues]);

  const handleReportSuflerOutage = useCallback(() => {
    if (suflerReportSent) return;
    setSuflerReportSent(true);
    void reportSuflerOutage({
      dialog_id: active?.id,
      operator_name: operatorName,
      query: suflerQuery,
      detail: suflerError || SUFLER_UNAVAILABLE_MESSAGE,
    }).catch(() => {
      // Allow retry if the notification failed to reach the backend.
      setSuflerReportSent(false);
    });
  }, [suflerReportSent, active?.id, operatorName, suflerQuery, suflerError]);

  const handleSelectQueue = (id: string) => {
    onSelectQueue(id);
    setUnreadByDialog((prev) => {
      if (!prev[id]) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
    const section = findSectionForQueueItem(id, visibleSections);
    if (section?.id === "colleagues") {
      onViewModeChange("colleague");
    } else {
      onViewModeChange("active");
    }
  };

  const [armOpen, setArmOpen] = useState(true);
  const [leftWidth, setLeftWidth] = useState(ARM_LEFT_WIDTH_DEFAULT);
  const [rightWidth, setRightWidth] = useState(ARM_RIGHT_WIDTH_DEFAULT);
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [canvasBuild, setCanvasBuild] = useState("");
  const [statsDrawerOpenLocal, setStatsDrawerOpenLocal] = useState(false);
  const statsDrawerOpen = statsDrawerOpenProp ?? statsDrawerOpenLocal;
  const setStatsDrawerOpen = useCallback(
    (open: boolean) => {
      if (onStatsDrawerOpenChange) onStatsDrawerOpenChange(open);
      else setStatsDrawerOpenLocal(open);
    },
    [onStatsDrawerOpenChange],
  );
  const [statsTab, setStatsTab] = useState<ArmStatsTab>(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get("historyDialog") || params.get("historyOperator")) return "history";
    } catch {
      /* ignore */
    }
    return "dialogs";
  });
  const [internalUnread, setInternalUnread] = useState(0);

  useEffect(() => {
    if (canvasBuild !== CANVAS_MOCKUP_VERSION) {
      setCanvasBuild(CANVAS_MOCKUP_VERSION);
      setStatsDrawerOpen(false);
      const params = new URLSearchParams(window.location.search);
      if (!(params.get("historyDialog") || params.get("historyOperator"))) {
        setStatsTab("dialogs");
      }
    }
  }, [canvasBuild, setCanvasBuild, setStatsDrawerOpen, setStatsTab]);

  useEffect(() => {
    let cancelled = false;
    const pollUnread = () => {
      void getInternalUnreadCount(operatorName)
        .then((result) => {
          if (!cancelled) setInternalUnread(result.unread_count);
        })
        .catch(() => undefined);
    };
    pollUnread();
    const timer = window.setInterval(pollUnread, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [operatorName]);

  useEffect(() => {
    const allowed = armMenuItemsForRole(armRole, menuContext).some((item) => item.id === statsTab);
    if (!allowed) setStatsTab(firstArmStatsTabForRole(armRole, menuContext));
  }, [armRole, menuContext, statsTab]);
  const [expandedSections, setExpandedSections] = useState<Record<QueueSectionId, boolean>>(
    defaultExpandedSections(),
  );
  const [collapsedCards, setCollapsedCards] = useState<Record<string, boolean>>({});
  const [expandedHintIds, setExpandedHintIds] = useState<Record<string, boolean>>({});
  const [expandedClientCard, setExpandedClientCard] = useState(false);
  const [expandedSummaryCard, setExpandedSummaryCard] = useState(false);
  const [composerNotice, setComposerNotice] = useState<string | null>(null);
  const [composerNoticeTone, setComposerNoticeTone] = useState<"success" | "info" | "warning" | "danger">("success");
  const pushComposerNotice = (
    message: string,
    tone: "success" | "info" | "warning" | "danger" = "success",
  ) => {
    setComposerNoticeTone(tone);
    setComposerNotice(message);
  };
  const [, setGraceNoticeDismissed] = useState(false);
  const [aiImproveModal, setAiImproveModal] = useState<AiImproveModalState | null>(null);
  const [closeDialogConfirmOpen, setCloseDialogConfirmOpen] = useState(false);
  const [blockClientConfirmOpen, setBlockClientConfirmOpen] = useState(false);

  useEffect(() => {
    setExpandedSections((prev) => {
      const next = { ...prev };
      if (liveWaiting.length > 0) next.waiting = true;
      if (liveInitiated.length > 0) next.initiated = true;
      if (liveShared.length > 0) next.shared = true;
      if (liveColleagues.length > 0) next.colleagues = true;
      return next;
    });
  }, [liveWaiting.length, liveInitiated.length, liveShared.length, liveColleagues.length]);

  useEffect(() => {
    if (!viewOnly || liveColleagues.length === 0) return;
    onViewModeChange("colleague");
    if (!liveColleagues.some((item) => item.id === selectedQueue)) {
      onSelectQueue(liveColleagues[0].id);
    }
  }, [viewOnly, liveColleagues, selectedQueue, onSelectQueue, onViewModeChange]);

  useEffect(() => {
    if (armRole !== "admin") return;
    void listClientBlocks(true)
      .then((blocks) =>
        setClientBlocks(blocks.map((block) => ({ id: block.id, phone_normalized: block.phone_normalized }))),
      )
      .catch(() => {});
  }, [armRole]);

  useEffect(() => {
    if (liveMine.length === 0) return;
    setExpandedSections((prev) => (prev.mine ? prev : { ...prev, mine: true }));
  }, [liveMine.length]);

  useEffect(() => {
    if (!liveMode) return;
    const syncViewModeForId = (id: string) => {
      const section = findSectionForQueueItem(id, visibleSections);
      if (section?.id === "colleagues") {
        if (viewMode !== "colleague") onViewModeChange("colleague");
      }
    };
    if (selectedQueue && remainingDialogs.some((item) => item.id === selectedQueue)) {
      syncViewModeForId(selectedQueue);
      return;
    }
    const firstLive = remainingDialogs.find((item) => item.live);
    if (!firstLive) return;
    onSelectQueue(firstLive.id);
    const section = findSectionForQueueItem(firstLive.id, visibleSections);
    onViewModeChange(section?.id === "colleagues" ? "colleague" : "active");
  }, [
    liveMode,
    selectedQueue,
    remainingDialogs,
    onSelectQueue,
    onViewModeChange,
    visibleSections,
    viewMode,
  ]);

  const clearComposerNotice = () => {
    setComposerNotice(null);
    setComposerNoticeTone("success");
  };

  const visibleQueueSections = visibleSections.map((section) => {
    const items = section.items.filter((item) => !closedDialogIds[item.id]);
    return { ...section, items, count: items.length };
  });

  useEffect(() => {
    if (selectedQueue && !closedDialogIds[selectedQueue]) return;
    const next = remainingDialogs.find((item) => !closedDialogIds[item.id]);
    if (next) {
      if (next.id !== selectedQueue) onSelectQueue(next.id);
      return;
    }
    if (selectedQueue) onSelectQueue("");
  }, [selectedQueue, closedDialogIds, onSelectQueue, remainingDialogs]);

  const handleConfirmCloseDialog = () => {
    if (!active) {
      setCloseDialogConfirmOpen(false);
      return;
    }
    const topic = closeTopic.trim();
    const topicId = selectedCloseTopicId.trim();
    if (!topic) {
      setCloseDialogConfirmOpen(false);
      pushComposerNotice("Выберите тематику закрытия перед завершением диалога.", "danger");
      return;
    }
    const closingId = active.id;
    const closedName = active.name;
    const wasLive = !!active.live;
    setCloseDialogConfirmOpen(false);
    setClosedDialogIds((prev) => ({ ...prev, [closingId]: true }));
    setBlockedDialogIds((prev) => {
      if (!prev[closingId]) return prev;
      const next = { ...prev };
      delete next[closingId];
      return next;
    });
    if (wasLive) {
      void closeDialogRemote(closingId, topic, topicId || undefined)
        .then((result) => {
          // Trust server grace window — it already checks capacity / mode.
          if (result.assignment_grace_until) {
            const until = Date.parse(result.assignment_grace_until);
            if (!Number.isNaN(until)) {
              setAssignmentGraceUntil(until);
            }
          } else {
            setAssignmentGraceUntil(null);
          }
          void refreshLiveQueues();
        })
        .catch(() => {
          setClosedDialogIds((prev) => {
            const next = { ...prev };
            delete next[closingId];
            return next;
          });
          pushComposerNotice("Не удалось закрыть диалог на сервере. Попробуйте ещё раз.", "danger");
        });
    }
    onCloseTopicChange("");
    setSelectedCloseTopicId("");
    const nextDialog = remainingDialogs.find((item) => item.id !== closingId);
    if (nextDialog) {
      onSelectQueue(nextDialog.id);
      pushComposerNotice(`Диалог с ${closedName} закрыт · ${topic}.`);
    } else {
      onSelectQueue("");
      pushComposerNotice(`Диалог закрыт · ${topic}. Очередь пуста — можно взять из общей очереди.`);
    }
  };

  const handleAcceptSharedDialog = (dialogId?: string, clientName?: string) => {
    const id = dialogId || active?.id;
    if (!id || acceptingDialogId || viewOnly) return;
    if (!lineOpen) {
      pushComposerNotice("Сейчас нерабочее время. Диалоги копятся в очереди.", "danger");
      return;
    }
    if (atCapacity) {
      pushComposerNotice(`Лимит диалогов ${myActiveCount}/${operatorCapacity}. Освободите слот, чтобы взять ещё.`);
      return;
    }
    setAcceptingDialogId(id);
    void acceptDialog(id, operatorName)
      .then(() => {
        setAssignmentGraceUntil(null);
        onSelectQueue(id);
        onViewModeChange("active");
        pushComposerNotice(`Диалог с ${clientName || active?.name || "клиентом"} принят.`);
        void refreshLiveQueues();
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : "Не удалось принять диалог";
        pushComposerNotice(message, "danger");
      })
      .finally(() => setAcceptingDialogId(null));
  };

  const handleTakeOverDialog = () => {
    if (!active?.live || !canTakeOverDialog) return;
    void transferDialogRemote(active.id, actingName, active.operatorName || "")
      .then(() => {
        pushComposerNotice(`Диалог с ${active.name} взят на себя.`);
        window.location.assign("/online-chat");
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : "Не удалось взять диалог";
        pushComposerNotice(message, "danger");
      });
  };

  const handleConfirmBlockClient = () => {
    if (!active) {
      setBlockClientConfirmOpen(false);
      return;
    }
    setBlockClientConfirmOpen(false);
    setBlockedDialogIds((prev) => ({ ...prev, [active.id]: true }));
    if (active.live) {
      void blockDialogRemote(active.id, { blocked_by: operatorName })
        .then(() => void refreshLiveQueues())
        .catch(() => {});
    }
    pushComposerNotice(`Клиент ${active.name} заблокирован.`);
  };

  const deliverReply = (notice: string) => {
    const text = reply.trim();
    const file = pendingAttachment;
    if ((!text && !file) || !active || composerLocked) return;
    const replyToId = quoteMessage?.id;
    if (active.live) {
      const sendPromise = file
        ? uploadOperatorAttachment(active.id, file, operatorName, text)
        : sendOperatorMessage(active.id, text, {
            reply_to_id: replyToId,
            operator_name: operatorName,
            response_origin: suflerSuggestionText ? "sufler" : undefined,
            sufler_suggestion_text: suflerSuggestionText || undefined,
          });
      void sendPromise
        .then((message) => {
          const withReceipt =
            message.receipt_status === "read" ||
            readMessageIdsRef.current.has(message.id)
              ? { ...message, receipt_status: "read" as ReceiptStatus }
              : message;
          setLiveMessages((prev) => {
            if (prev.some((item) => item.id === withReceipt.id)) {
              return prev.map((item) =>
                item.id === withReceipt.id ? { ...item, ...withReceipt } : item,
              );
            }
            return [...prev, withReceipt];
          });
          onReplyChange("");
          setPendingAttachment(null);
          setQuoteMessage(null);
          pushComposerNotice(
            file
              ? text
                ? `Файл «${file.name}» и сообщение отправлены.`
                : `Файл «${file.name}» отправлен.`
              : notice,
          );
          void refreshLiveQueues();
        })
        .catch(() => {
          pushComposerNotice(
            file ? "Не удалось отправить файл." : "Не удалось отправить сообщение.",
            "danger",
          );
        });
      return;
    }
    onReplyChange("");
    setPendingAttachment(null);
    setQuoteMessage(null);
    pushComposerNotice(notice);
  };

  const transferOperatorsOnly = useMemo(
    () =>
      transferOperators.filter(
        (item) => item.name !== operatorName && (item.role ?? "operator") === "operator",
      ),
    [transferOperators, operatorName],
  );
  const transferSupervisorsOnly = useMemo(
    () =>
      transferOperators.filter(
        (item) => item.name !== operatorName && item.role === "supervisor",
      ),
    [transferOperators, operatorName],
  );

  const transferDepartments = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of transferOperatorsOnly) {
      const deptName = item.department_name?.trim() || "Без отдела";
      const deptId = String(item.department_id ?? item.department ?? deptName);
      map.set(deptId, deptName);
    }
    return Array.from(map.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name, "ru"));
  }, [transferOperatorsOnly]);

  const transferOperatorOptions = useMemo(() => {
    if (transferTargetKind === "supervisor") {
      const list = transferSupervisorsOnly.length
        ? transferSupervisorsOnly
        : [{ name: "Козлова Е.В." } as ChatOperator];
      return list
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name, "ru"))
        .map((item) => ({ value: item.name, label: item.name }));
    }
    const inDept = transferOperatorsOnly.filter((item) => {
      const deptName = item.department_name?.trim() || "Без отдела";
      const deptId = String(item.department_id ?? item.department ?? deptName);
      return deptId === transferDepartment;
    });
    if (inDept.length) {
      return inDept
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name, "ru"))
        .map((item) => ({ value: item.name, label: item.name }));
    }
    if (!transferOperatorsOnly.length) {
      return TRANSFER_OPERATORS
        .filter((name) => name !== operatorName)
        .map((name) => ({ value: name, label: name }));
    }
    return [];
  }, [
    transferTargetKind,
    transferSupervisorsOnly,
    transferOperatorsOnly,
    transferDepartment,
    operatorName,
  ]);

  const openTransferDialog = () => {
    if (!active?.live) return;
    if (composerLocked && !canTransferDespiteView) return;
    setTransferTargetKind("operator");
    const firstDept = transferDepartments[0]?.id ?? "";
    setTransferDepartment(firstDept);
    const firstOps = transferOperatorsOnly
      .filter((item) => {
        const deptName = item.department_name?.trim() || "Без отдела";
        const deptId = String(item.department_id ?? item.department ?? deptName);
        return deptId === firstDept;
      })
      .map((item) => item.name);
    setTransferOperatorName(firstOps[0] ?? TRANSFER_OPERATORS.find((name) => name !== operatorName) ?? "");
    setTransferDialogOpen(true);
  };

  const graceSecondsLeft =
    assignmentGraceUntil != null
      ? Math.max(0, Math.ceil((assignmentGraceUntil - nowMs) / 1000))
      : 0;
  const showGraceTimer = graceSecondsLeft > 0;

  const showTakeToolbarButton =
    !!active?.live &&
    !viewOnly &&
    (armRole === "supervisor" || isSharedQueuePeek);
  const takeToolbarEnabled =
    showTakeToolbarButton &&
    lineOpen &&
    !acceptingDialogId &&
    ((canTakeOverDialog) ||
      (isSharedQueuePeek && !atCapacity && !supervisorOwnsActive));
  const takeToolbarLabel = canTakeOverDialog
    ? "Взять на себя"
    : isSharedQueuePeek
      ? atCapacity
        ? `Лимит ${myActiveCount}/${operatorCapacity}`
        : "Взять диалог"
      : "Взять на себя";
  const handleTakeToolbar = () => {
    if (canTakeOverDialog) {
      handleTakeOverDialog();
      return;
    }
    if (isSharedQueuePeek) {
      handleAcceptSharedDialog();
    }
  };

  const overlayNotices = [
    ...(composerNotice
      ? [{
          id: "composer",
          message: composerNotice,
          tone: composerNoticeTone,
          onDone: clearComposerNotice,
        }]
      : []),
    ...(toast
      ? [{ id: "toast", message: toast, tone: "success" as const, onDone: onClearToast }]
      : []),
  ];

  const handleConfirmTransferDialog = () => {
    if (!active?.live) return;
    const toName = transferOperatorName.trim();
    if (!toName) return;
    const transferredId = active.id;
    const transferredName = active.name;
    setTransferDialogOpen(false);
    const preferNext =
      liveWaiting.find((item) => item.id !== transferredId)
      ?? remainingDialogs.find((item) => item.id !== transferredId && !item.readOnly);
    if (preferNext) onSelectQueue(preferNext.id);
    else onSelectQueue("");
    void transferDialogRemote(transferredId, toName, operatorName)
      .then(async () => {
        pushComposerNotice(`Диалог с ${transferredName} переведён на ${toName}.`);
        await refreshLiveQueues();
      })
      .catch(() => {
        pushComposerNotice("Не удалось перевести диалог.", "danger");
        onSelectQueue(transferredId);
      });
  };

  const handleDownloadAttachment = (message: OnlineChatMessage) => {
    if (!active?.id || !message.attachment_name) return;
    void downloadAttachment(active.id, message.id, message.attachment_name).catch(() => {
      pushComposerNotice("Не удалось скачать файл.", "danger");
    });
  };

  const handleFilePick = (file: File) => {
    if (!active?.live || composerLocked) return;
    setPendingAttachment(file);
    pushComposerNotice(`Файл «${file.name}» прикреплён. Напишите сообщение при необходимости и нажмите «Отправить».`);
  };

  const openEditMessage = (message: OnlineChatMessage) => {
    if (!active?.live) return;
    setEditMessageTarget(message);
    setEditMessageText(message.raw_text || message.text);
  };

  const handleConfirmEditMessage = () => {
    if (!active?.live || !editMessageTarget) return;
    const nextText = editMessageText.trim();
    const previous = (editMessageTarget.raw_text || editMessageTarget.text || "").trim();
    const hasAttachment = Boolean(editMessageTarget.attachment_key || editMessageTarget.attachment_name);
    if ((!nextText && !hasAttachment) || nextText === previous) {
      setEditMessageTarget(null);
      return;
    }
    const messageId = editMessageTarget.id;
    setEditMessageTarget(null);
    void editMessageRemote(active.id, messageId, nextText)
      .then((updated) => {
        setLiveMessages((prev) =>
          prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
        );
      })
      .catch(() => {
        pushComposerNotice("Не удалось изменить сообщение.", "danger");
      });
  };

  const openDeleteMessage = (message: OnlineChatMessage) => {
    if (!active?.live) return;
    setDeleteMessageTarget(message);
  };

  const handleConfirmDeleteMessage = () => {
    if (!active?.live || !deleteMessageTarget) return;
    const messageId = deleteMessageTarget.id;
    setDeleteMessageTarget(null);
    void deleteMessageRemote(active.id, messageId)
      .then((deleted) => {
        setLiveMessages((prev) =>
          prev.map((item) =>
            item.id === deleted.id ? { ...item, is_deleted: true, text: "" } : item,
          ),
        );
      })
      .catch(() => {
        pushComposerNotice("Не удалось удалить сообщение.", "danger");
      });
  };

  const activePhoneBlock = useMemo(() => {
    if (!active?.phone || armRole !== "admin") return null;
    const digits = active.phone.replace(/\D/g, "");
    return clientBlocks.find((block) => block.phone_normalized.replace(/\D/g, "") === digits) ?? null;
  }, [active?.phone, armRole, clientBlocks]);

  const handleLiftBlock = () => {
    if (!activePhoneBlock) return;
    void liftClientBlock(activePhoneBlock.id, operatorName)
      .then(() => {
        setClientBlocks((prev) => prev.filter((block) => block.id !== activePhoneBlock.id));
        pushComposerNotice("Блокировка клиента снята.");
      })
      .catch(() => {
        pushComposerNotice("Не удалось снять блокировку.", "danger");
      });
  };

  const handleAiImprove = () => {
    setComposerNotice(null);
    const trimmed = reply.trim();
    if (trimmed.length === 0) return;
    const improved = polishTextDemo(reply);
    setAiImproveModal({ original: reply, improved });
  };

  const handleAcceptAiImprove = () => {
    if (!aiImproveModal) return;
    onReplyChange(aiImproveModal.improved);
    setAiImproveModal(null);
  };

  const handleDismissAiImprove = () => {
    setAiImproveModal(null);
  };
  const boundedLeftWidth = clampWidth(leftWidth, ARM_LEFT_WIDTH_MIN, ARM_LEFT_WIDTH_MAX);
  const boundedRightWidth = clampWidth(rightWidth, ARM_RIGHT_WIDTH_MIN, ARM_RIGHT_WIDTH_MAX);

  const toggleSection = (sectionId: QueueSectionId) => {
    setExpandedSections((prev) => {
      const section = visibleSections.find((s) => s.id === sectionId);
      if (!section) return prev;
      return { ...prev, [sectionId]: !isSectionExpanded(prev, section) };
    });
  };
  const collapseCard = (cardId: string) => {
    setCollapsedCards((prev) => ({ ...prev, [cardId]: true }));
  };
  const expandCard = (cardId: string) => {
    setCollapsedCards((prev) => {
      const next = { ...prev };
      delete next[cardId];
      return next;
    });
  };
  const collapseAllQueue = () => {
    setExpandedSections(allSectionsCollapsedState(visibleSections));
    setCollapsedCards({});
  };
  const expandAllQueue = () => {
    setExpandedSections(allSectionsExpandedState(visibleSections));
    setCollapsedCards({});
  };
  const allSectionsCollapsed = areAllSectionsCollapsed(expandedSections, visibleSections);

  if (!armOpen) {
    return (
      <Button variant="secondary" onClick={() => setArmOpen(true)}>
        Открыть окно · АРМ оператора
      </Button>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        flex: 1,
        minHeight: 0,
        minWidth: 900,
        position: "relative",
      }}
    >
      <style>{`
        @keyframes oc-unread-pulse {
          0%, 100% { box-shadow: 0 0 0 2px rgba(0, 122, 67, 0.22); }
          50% { box-shadow: 0 0 0 4px rgba(0, 122, 67, 0.38); }
        }
      `}</style>
      <div
        style={{
          position: "relative",
          ...panelStyle(t),
          padding: "10px 16px",
          borderRadius: `${RADIUS_MD} ${RADIUS_MD} 0 0`,
          borderBottom: `1px solid ${scheme.accent}`,
          background: scheme.headerBg,
          zIndex: 5,
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <Row
          style={{
            gap: 6,
            flexWrap: "wrap",
            alignItems: "center",
            minWidth: 0,
            flex: 1,
          }}
        >
          {OPERATOR_STATUSES.map((status) => (
            <OperatorStatusPill
              key={status.id}
              t={t}
              status={status}
              active={presence === status.id}
              size="md"
              onClick={viewOnly ? undefined : () => onPresenceChange(status.id)}
            />
          ))}
          {viewOnly ? (
            <Pill tone="warning" size="sm">
              только просмотр
            </Pill>
          ) : null}
        </Row>
      </div>

      <div style={{ display: "flex", flex: 1, minHeight: 0, position: "relative", overflow: "hidden" }}>
        <ArmOverlayMenu
          t={t}
          scheme={scheme}
          open={statsDrawerOpen}
          armRole={armRole}
          menuContext={menuContext}
          activeId={statsTab}
          badges={{ internal: internalUnread }}
          onSelect={(id) => {
            if (id === "employees") {
              window.location.assign("/online-chat");
              return;
            }
            setStatsTab(id);
            setStatsDrawerOpen(false);
          }}
          onClose={() => setStatsDrawerOpen(false)}
        />
        {isArmWorkspaceModule(statsTab) ? (
          <ArmModulesHost
            tab={statsTab as ArmModuleId}
            t={t}
            scheme={scheme}
            operatorName={operatorName}
            armRole={armRole}
            onBack={() => setStatsTab("dialogs")}
            onNavigate={(id) => setStatsTab(id as ArmStatsTab)}
            onUnreadChange={setInternalUnread}
          />
        ) : (
        <>
        {/* Queues */}
        {leftPanelCollapsed ? (
          <div
            style={{
              width: 28,
              flexShrink: 0,
              ...panelStyle(t, { borderRadius: 0, borderRight: "none" }),
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              paddingTop: 12,
            }}
          >
            <button
              type="button"
              title="Развернуть панель очереди"
              aria-label="Развернуть панель очереди"
              onClick={() => setLeftPanelCollapsed((collapsed) => !collapsed)}
              style={{
                border: "none",
                background: "transparent",
                color: scheme.accentControl,
                fontSize: 12,
                cursor: "pointer",
                padding: "4px 2px",
                fontFamily: "inherit",
              }}
            >
              »»
            </button>
          </div>
        ) : (
          <div
            style={{
              width: boundedLeftWidth,
              flexShrink: 0,
              minHeight: 0,
              alignSelf: "stretch",
              ...panelStyle(t, { borderRadius: 0, borderRight: "none" }),
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            <div style={{ padding: "12px 12px 8px", flexShrink: 0 }}>
            <Row style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 4 }}>
              <button
                type="button"
                title={allSectionsCollapsed ? "Развернуть все" : "Свернуть все"}
                aria-label={allSectionsCollapsed ? "Развернуть все секции" : "Свернуть все секции"}
                onClick={() => (allSectionsCollapsed ? expandAllQueue() : collapseAllQueue())}
                style={{
                  border: `1px solid ${scheme.accentWeak}`,
                  background: `linear-gradient(180deg, ${t.bg.elevated} 0%, ${t.fill.secondary} 100%)`,
                  color: scheme.accentControl,
                  fontSize: 12,
                  fontWeight: 650,
                  cursor: "pointer",
                  padding: "6px 12px",
                  fontFamily: "inherit",
                  borderRadius: 999,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 7,
                  lineHeight: 1.2,
                  boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                }}
              >
                <span
                  aria-hidden
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: 999,
                    display: "inline-grid",
                    placeItems: "center",
                    background: scheme.accentWeak,
                    color: scheme.accentControl,
                    fontSize: 12,
                    lineHeight: 1,
                  }}
                >
                  {allSectionsCollapsed ? "+" : "−"}
                </span>
                {allSectionsCollapsed ? "Развернуть все" : "Свернуть все"}
              </button>
              {showGraceTimer ? (
                <span
                  title="Выберите диалог из общей очереди до автоназначения"
                  style={{
                    flex: "1 1 auto",
                    textAlign: "center",
                    fontSize: 12,
                    fontWeight: 700,
                    fontVariantNumeric: "tabular-nums",
                    color: "#B45309",
                    background: "#FFF7ED",
                    border: "1px solid #FDBA74",
                    borderRadius: 999,
                    padding: "5px 10px",
                    whiteSpace: "nowrap",
                  }}
                >
                  Выбор · {graceSecondsLeft}с
                </span>
              ) : (
                <span style={{ flex: 1 }} />
              )}
              <button
                type="button"
                title="Свернуть панель очереди"
                aria-label="Свернуть панель очереди"
                onClick={() => setLeftPanelCollapsed((collapsed) => !collapsed)}
                style={{
                  border: "none",
                  background: "transparent",
                  color: t.text.tertiary,
                  fontSize: 12,
                  cursor: "pointer",
                  padding: "2px 4px",
                  fontFamily: "inherit",
                  flexShrink: 0,
                }}
              >
                ««
              </button>
            </Row>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "0 12px 12px" }}>
            <Stack style={{ gap: 12 }}>
              {visibleQueueSections.map((section) => {
                const sectionExpanded = isSectionExpanded(expandedSections, section);
                return (
                  <div key={section.id}>
                    <QueueSectionHeader
                      t={t}
                      scheme={scheme}
                      title={section.title}
                      count={section.count}
                      unreadTotal={
                        section.id === "mine"
                          ? section.items.reduce((sum, item) => sum + (item.unreadCount || 0), 0)
                          : 0
                      }
                      expanded={sectionExpanded}
                      onToggle={() => toggleSection(section.id)}
                    />
                    {sectionExpanded ? (
                      <Stack style={{ gap: 8 }}>
                        {section.items.map((q) => {
                          const cardCollapsed = !!collapsedCards[q.id];

                          if (cardCollapsed) {
                            return (
                              <QueueListRow
                                key={q.id}
                                item={q}
                                t={t}
                                selected={q.id === selectedQueue}
                                nowMs={nowMs}
                                onClick={() => {
                                  handleSelectQueue(q.id);
                                  expandCard(q.id);
                                }}
                              />
                            );
                          }

                          return (
                            <QueueCard
                              key={q.id}
                              item={q}
                              t={t}
                              scheme={scheme}
                              selected={q.id === selectedQueue}
                              nowMs={nowMs}
                              onSelect={() => handleSelectQueue(q.id)}
                              onCollapse={() => collapseCard(q.id)}
                              onAccept={
                                section.id === "shared" &&
                                !viewOnly &&
                                armRole !== "supervisor"
                                  ? () => handleAcceptSharedDialog(q.id, q.name)
                                  : undefined
                              }
                              acceptDisabled={
                                section.id === "shared" &&
                                !viewOnly &&
                                armRole !== "supervisor"
                                  ? atCapacity || !lineOpen
                                  : undefined
                              }
                              acceptBusy={acceptingDialogId === q.id}
                            />
                          );
                        })}
                      </Stack>
                    ) : null}
                  </div>
                );
              })}
            </Stack>
            </div>
          </div>
        )}

        {!leftPanelCollapsed ? (
          <ColumnResizeHandle
            t={t}
            label="Изменить ширину панели очереди"
            onMouseDown={(event) =>
              startColumnResize(event, boundedLeftWidth, setLeftWidth, ARM_LEFT_WIDTH_MIN, ARM_LEFT_WIDTH_MAX)
            }
          />
        ) : null}

        {/* Chat */}
        <div
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 0,
            position: "relative",
            ...panelStyle(t, { borderRadius: 0 }),
            display: "flex",
            flexDirection: "column",
          }}
        >
          {!hasActiveDialog || !active ? (
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: 24,
                gap: 12,
                position: "relative",
              }}
            >
              <Text style={{ color: t.text.secondary, fontSize: 14, textAlign: "center", maxWidth: 420 }}>
                {queuesReady
                  ? "Очередь пуста. Чтобы появился поток обращений, создайте сценарий в разделе «Симулятор» (тест)."
                  : "Загружаем очереди…"}
              </Text>
              {queuesReady ? (
                <a
                  href="/online-chat/simulator"
                  style={{ color: scheme.accentControl, fontSize: 13, fontWeight: 600 }}
                >
                  Открыть симулятор
                </a>
              ) : null}
              <ComposerOverlayNotices
                placement="bottom"
                notices={overlayNotices}
              />
            </div>
          ) : (
            <>
          <div style={{ padding: "12px 16px", borderBottom: `1px solid ${t.stroke.secondary}`, flexShrink: 0 }}>
            <Row style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
              <div style={{ minWidth: 0 }}>
                <Row style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <Text weight="semibold">{active.name}</Text>
                  {isClientBlocked ? (
                    <Pill tone="warning" size="sm">
                      Клиент заблокирован
                    </Pill>
                  ) : null}
                </Row>
                <Row style={{ gap: 8, marginTop: 4 }}>
                  <Pill tone="info" size="sm">
                    {active.channel}
                  </Pill>
                </Row>
              </div>
              {viewOnly ? (
                <div
                  style={{
                    flex: 1,
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "flex-start",
                    minWidth: 0,
                    paddingTop: 2,
                  }}
                >
                  <Callout tone="warning" style={{ fontSize: 12, maxWidth: 420, width: "100%" }}>
                    {`Просмотр АРМ оператора ${operatorName}.`}
                    {canTakeOverDialog
                      ? " Без ответа клиенту — можно взять диалог на себя."
                      : " Только наблюдение, без действий от лица оператора."}
                  </Callout>
                </div>
              ) : (
                <Spacer />
              )}
              <Stack gap={6} style={{ alignItems: "flex-end", flexShrink: 0 }}>
                {(() => {
                  const resolved = resolveQueueWait(active, nowMs);
                  return resolved.slaTone ? (
                    <SlaWaitPill wait={resolved.wait} slaTone={resolved.slaTone} />
                  ) : (
                    <Pill tone={resolved.urgent ? "warning" : "neutral"} size="sm">
                      SLA {resolved.wait}
                    </Pill>
                  );
                })()}
                <Text style={{ fontSize: 12, color: t.text.secondary, textAlign: "right" }}>
                  {viewMode === "colleague"
                    ? `Просмотр · ${active.operatorName ?? "коллега"}`
                    : "Мой диалог"}
                </Text>
              </Stack>
            </Row>
            {isClientBlocked ? (
              <Callout tone="warning" style={{ marginTop: 10, fontSize: 12 }}>
                Пользователь заблокирован. Отправка сообщений недоступна.
              </Callout>
            ) : null}
          </div>
          <div style={{ padding: "8px 16px", borderBottom: `1px solid ${t.stroke.tertiary}`, flexShrink: 0 }}>
            <Row style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <Text style={{ fontSize: 12, color: t.text.secondary }}>Тематика закрытия:</Text>
              <TopicSelect
                t={t}
                value={closeTopic}
                options={dialogTopics}
                recommendedPath={recommendedTopicPath}
                recommendedId={recommendedTopicId}
                onChange={(nextPath, nextId) => {
                  onCloseTopicChange(nextPath)
                  setSelectedCloseTopicId(nextId)
                }}
                disabled={isReadOnly}
                style={{ flex: "1 1 220px", maxWidth: 340 }}
              />
              <Spacer />
              <Button
                variant="ghost"
                size="sm"
                style={{ color: t.text.tertiary, fontSize: 11 }}
                disabled={isReadOnly || isClientBlocked}
                onClick={() => setBlockClientConfirmOpen(true)}
              >
                {isClientBlocked ? "Заблокирован" : "Заблокировать"}
              </Button>
              {activePhoneBlock ? (
                <Button
                  variant="ghost"
                  size="sm"
                  style={{ color: t.text.tertiary, fontSize: 11 }}
                  onClick={handleLiftBlock}
                >
                  Снять блокировку
                </Button>
              ) : null}
              <Button
                variant="primary"
                size="sm"
                disabled={isReadOnly}
                onClick={() => setCloseDialogConfirmOpen(true)}
              >
                Закрыть диалог
              </Button>
            </Row>
          </div>
          <div
            ref={messagesScrollRef}
            onScroll={handleMessagesScroll}
            style={{
              flex: 1,
              minHeight: 0,
              padding: "16px 16px 20px",
              overflowY: "auto",
              overflowX: "hidden",
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {active.live ? (
              liveMessages.length > 0 ? (
                liveMessages.map((message) => {
                  const isHistory = Boolean(message.is_history);
                  if (message.speaker === "system") {
                    return (
                      <MessageBubble
                        key={message.id}
                        t={t}
                        scheme={scheme}
                        side="system"
                        text={message.text}
                        isHistory={isHistory}
                      />
                    );
                  }
                  if (message.speaker === "operator") {
                    return (
                      <MessageBubble
                        key={message.id}
                        t={t}
                        scheme={scheme}
                        side="operator"
                        label={`${operatorName} · оператор`}
                        avatarInitials={operatorInitials}
                        text={message.text}
                        time={messageTimeLabel(message.created_at)}
                        quotedText={message.quoted_text}
                        attachmentName={message.attachment_name}
                        attachmentDownloadable={canDownloadAttachment(message)}
                        onDownloadAttachment={
                          canDownloadAttachment(message)
                            ? () => handleDownloadAttachment(message)
                            : undefined
                        }
                        isDeleted={message.is_deleted}
                        editedAt={message.edited_at}
                        isHistory={isHistory}
                        receiptStatus={
                          // Read receipts only for website widget — other channels have no read API.
                          message.is_deleted ||
                          isHistory ||
                          (active.channel !== "Сайт" && active.channel !== "widget")
                            ? undefined
                            : message.receipt_status === "read" ||
                                readMessageIdsRef.current.has(message.id)
                              ? "read"
                              : "delivered"
                        }
                        onEdit={
                          !isHistory && !isReadOnly && !message.is_deleted
                            ? () => openEditMessage(message)
                            : undefined
                        }
                        onDelete={
                          !isHistory && !isReadOnly && !message.is_deleted
                            ? () => openDeleteMessage(message)
                            : undefined
                        }
                      />
                    );
                  }
                  if (message.speaker === "bot") {
                    return (
                      <MessageBubble
                        key={message.id}
                        t={t}
                        scheme={scheme}
                        side="operator"
                        label="Виртуальный помощник · бот"
                        avatarInitials="Б"
                        text={message.text}
                        time={messageTimeLabel(message.created_at)}
                        isHistory={isHistory}
                        receiptStatus={
                          !isHistory &&
                          (active.channel === "Сайт" || active.channel === "widget")
                            ? message.receipt_status
                            : undefined
                        }
                      />
                    );
                  }
                  return (
                    <MessageBubble
                      key={message.id}
                      t={t}
                      scheme={scheme}
                      side="client"
                      label={active.name}
                      avatarInitials={initialsFromDisplayName(active.name)}
                      text={message.text}
                      time={messageTimeLabel(message.created_at)}
                      quotedText={message.quoted_text}
                      editedAt={message.edited_at}
                      attachmentName={message.attachment_name}
                      attachmentDownloadable={canDownloadAttachment(message)}
                      onDownloadAttachment={
                        canDownloadAttachment(message)
                          ? () => handleDownloadAttachment(message)
                          : undefined
                      }
                      isDeleted={message.is_deleted}
                      isHistory={isHistory}
                      onQuote={
                        !isHistory && !isReadOnly && !message.is_deleted
                          ? () => setQuoteMessage(message)
                          : undefined
                      }
                    />
                  );
                })
              ) : (
                <Text style={{ fontSize: 12, color: t.text.secondary }}>
                  Загрузка сообщений…
                </Text>
              )
            ) : (
              <>
                <MessageBubble
                  t={t}
                  scheme={scheme}
                  side="system"
                  text={`Оператор ${operatorName} подключился к диалогу`}
                />
                <MessageBubble
                  t={t}
                  scheme={scheme}
                  side="client"
                  label={active.name}
                  avatarInitials={initialsFromDisplayName(active.name)}
                  text={active.preview}
                  time="10:03"
                />
                <MessageBubble
                  t={t}
                  scheme={scheme}
                  side="operator"
                  label={`${operatorName} · оператор`}
                  avatarInitials={operatorInitials}
                  text="Проверяю лимиты по вашей карте, одну минуту."
                  time="10:04"
                  receiptStatus="read"
                />
              </>
            )}
            <div ref={messagesEndRef} aria-hidden style={{ height: 1, flexShrink: 0 }} />
          </div>
          <div
            style={{
              position: "relative",
              padding: 12,
              borderTop: `1px solid ${t.stroke.secondary}`,
              flexShrink: 0,
              background: t.bg.elevated,
            }}
          >
            <ComposerOverlayNotices notices={overlayNotices} />
            <input
              ref={fileInputRef}
              type="file"
              style={{ display: "none" }}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) handleFilePick(file);
                event.target.value = "";
              }}
            />
            <Row style={{ gap: 8, marginBottom: 8, flexWrap: "wrap", alignItems: "center", position: "relative" }}>
              <IconButton
                title="Шаблоны ответов"
                aria-label="Шаблоны ответов"
                disabled={composerLocked}
                active={showTemplates}
                onClick={() => {
                  setComposerTemplates(loadReplyTemplates(operatorName));
                  setTemplateCategory(null);
                  setShowTemplates((open) => !open);
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path
                    d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                  />
                </svg>
              </IconButton>
              {showTemplates && !composerLocked ? (
                <div
                  role="listbox"
                  aria-label="Шаблоны ответов"
                  style={{
                    position: "absolute",
                    bottom: "100%",
                    left: 0,
                    marginBottom: 8,
                    zIndex: 20,
                    width: 360,
                    maxWidth: "min(360px, calc(100vw - 48px))",
                    maxHeight: "min(320px, 45vh)",
                    display: "flex",
                    flexDirection: "column",
                    background: t.bg.elevated,
                    border: `1px solid ${scheme.accentWeak}`,
                    borderRadius: 12,
                    padding: 10,
                    boxShadow: "0 14px 36px rgba(12, 40, 28, 0.16)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                      padding: "2px 6px 10px",
                      borderBottom: `1px solid ${t.stroke.secondary}`,
                      marginBottom: 8,
                      flexShrink: 0,
                    }}
                  >
                    <div>
                      <Text weight="semibold" style={{ fontSize: 13, color: t.text.primary }}>
                        Шаблоны ответов
                      </Text>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label="Закрыть шаблоны"
                      onClick={() => {
                        setShowTemplates(false);
                        setTemplateCategory(null);
                      }}
                    >
                      ✕
                    </Button>
                  </div>
                  <Stack gap={4} style={{ overflowY: "auto", minHeight: 0, flex: 1, paddingRight: 2 }}>
                    {!templateCategory ? (
                      [...new Set(composerTemplates.map((item) => item.category))].map((category) => {
                        const count = composerTemplates.filter((item) => item.category === category).length;
                        return (
                          <button
                            key={category}
                            type="button"
                            onClick={() => setTemplateCategory(category)}
                            style={{
                              border: `1px solid ${t.stroke.secondary}`,
                              background: t.bg.editor,
                              textAlign: "left",
                              padding: "10px 12px",
                              borderRadius: 10,
                              cursor: "pointer",
                              fontFamily: "inherit",
                              fontSize: 13,
                              color: t.text.primary,
                              display: "flex",
                              justifyContent: "space-between",
                              gap: 8,
                            }}
                          >
                            <span style={{ fontWeight: 600 }}>{category}</span>
                            <span style={{ color: t.text.tertiary, fontSize: 12 }}>{count}</span>
                          </button>
                        );
                      })
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => setTemplateCategory(null)}
                          style={{
                            border: "none",
                            background: "transparent",
                            textAlign: "left",
                            padding: "4px 6px 8px",
                            cursor: "pointer",
                            fontFamily: "inherit",
                            fontSize: 12,
                            color: t.text.secondary,
                          }}
                        >
                          ← Категории
                        </button>
                        {composerTemplates
                          .filter((template) => template.category === templateCategory)
                          .map((template, index) => (
                      <button
                        key={template.id}
                        type="button"
                        role="option"
                        onClick={() => {
                          const text = template.body
                            .replaceAll("{{client_name}}", active?.name ?? "клиент")
                            .replaceAll("{{operator_name}}", operatorName);
                          onReplyChange(text);
                          setShowTemplates(false);
                          setTemplateCategory(null);
                        }}
                        style={{
                          border: `1px solid ${t.stroke.secondary}`,
                          background: t.bg.editor,
                          textAlign: "left",
                          padding: "10px 12px",
                          borderRadius: 10,
                          cursor: "pointer",
                          fontFamily: "inherit",
                          fontSize: 12,
                          lineHeight: 1.4,
                          color: t.text.primary,
                          display: "flex",
                          gap: 10,
                          alignItems: "flex-start",
                          transition: "background 120ms ease, border-color 120ms ease",
                        }}
                        onMouseEnter={(event) => {
                          event.currentTarget.style.background = scheme.accentWeak;
                          event.currentTarget.style.borderColor = scheme.accent;
                        }}
                        onMouseLeave={(event) => {
                          event.currentTarget.style.background = t.bg.editor;
                          event.currentTarget.style.borderColor = t.stroke.secondary;
                        }}
                      >
                        <span
                          style={{
                            flexShrink: 0,
                            width: 22,
                            height: 22,
                            borderRadius: 7,
                            background: scheme.accent,
                            color: "#fff",
                            fontSize: 11,
                            fontWeight: 700,
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            marginTop: 1,
                          }}
                        >
                          {index + 1}
                        </span>
                        <span style={{ minWidth: 0 }}>
                          <span style={{ fontWeight: 600, display: "block", marginBottom: 2 }}>
                            {template.favorite ? "★ " : ""}
                            {template.title}
                          </span>
                          {template.body}
                        </span>
                      </button>
                          ))}
                      </>
                    )}
                  </Stack>
                </div>
              ) : null}
              <IconButton
                title="Перевести диалог"
                aria-label="Перевести диалог"
                disabled={!active?.live || (composerLocked && !canTransferDespiteView)}
                onClick={openTransferDialog}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path
                    d="M17 8H7l3.5-3.5M7 16h10l-3.5 3.5"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </IconButton>
              {showTakeToolbarButton ? (
                <IconButton
                  title={
                    acceptingDialogId === active?.id
                      ? "Принимаем…"
                      : takeToolbarLabel
                  }
                  aria-label={takeToolbarLabel}
                  disabled={!takeToolbarEnabled || acceptingDialogId === active?.id}
                  onClick={handleTakeToolbar}
                  style={{
                    background: scheme.accent,
                    borderColor: scheme.accent,
                    color: "#fff",
                    opacity: takeToolbarEnabled ? 1 : 0.5,
                    filter: takeToolbarEnabled ? undefined : "saturate(0.6)",
                  }}
                >
                  <TakeDialogIcon size={18} />
                </IconButton>
              ) : null}
            </Row>
            {clientDraft && active?.live && !composerLocked ? (
              <Callout tone="info" style={{ marginBottom: 8, fontSize: 12 }}>
                Клиент набирает: {clientDraft}
              </Callout>
            ) : null}
            {isSharedQueuePeek ? (
              <Callout tone="info" style={{ marginBottom: 8, fontSize: 12 }}>
                {armRole === "supervisor"
                  ? "Просмотр общей очереди. Чтобы отвечать клиенту, нажмите «Взять диалог»."
                  : `Просмотр общей очереди: ответ недоступен, пока диалог не принят${
                      atCapacity ? ` (лимит ${myActiveCount}/${operatorCapacity})` : ""
                    }.`}
              </Callout>
            ) : null}
            {canTakeOverDialog ? (
              <Callout tone="info" style={{ marginBottom: 8, fontSize: 12 }}>
                Режим просмотра чужого диалога. Чтобы отвечать, нажмите «Взять на себя».
              </Callout>
            ) : null}
            {quoteMessage ? (
              <div
                style={{
                  marginBottom: 8,
                  padding: "6px 10px",
                  borderRadius: RADIUS_SM,
                  background: t.fill.tertiary,
                  border: `1px solid ${t.stroke.secondary}`,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <Text style={{ fontSize: 12, color: t.text.secondary, flex: 1, minWidth: 0 }}>
                  Ответ на: {quoteMessage.text.slice(0, 120)}
                  {quoteMessage.text.length > 120 ? "…" : ""}
                </Text>
                <Button variant="ghost" size="sm" onClick={() => setQuoteMessage(null)}>
                  ✕
                </Button>
              </div>
            ) : null}
            {pendingAttachment && !composerLocked ? (
              <div
                style={{
                  marginBottom: 8,
                  padding: "6px 10px",
                  borderRadius: RADIUS_SM,
                  background: t.fill.tertiary,
                  border: `1px solid ${t.stroke.secondary}`,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <Text style={{ fontSize: 12, color: t.text.secondary, flex: 1, minWidth: 0 }}>
                  📎 {pendingAttachment.name}
                </Text>
                <Button variant="ghost" size="sm" onClick={() => setPendingAttachment(null)}>
                  ✕
                </Button>
              </div>
            ) : null}
            <div style={{ position: "relative", opacity: composerLocked ? 0.55 : 1 }} data-chat-composer="true">
              <Stack gap={8}>
                <div style={{ position: "relative" }}>
                  <TextArea
                    placeholder={
                      isClientBlocked
                        ? "Клиент заблокирован — ответ недоступен"
                        : isSharedQueuePeek
                          ? "Общая очередь — только просмотр"
                          : pendingAttachment
                            ? "Добавьте текст к файлу (необязательно)…"
                            : "Введите ответ клиенту…"
                    }
                    style={{
                      width: "100%",
                      minHeight: 72,
                      overflow: "auto",
                      resize: "vertical",
                      paddingLeft: 36,
                      paddingTop: 10,
                      boxSizing: "border-box",
                    }}
                    rows={3}
                    value={reply}
                    onChange={(v) => {
                      onReplyChange(v);
                      setComposerNotice(null);
                      if (aiImproveModal && v !== aiImproveModal.original) {
                        setAiImproveModal(null);
                      }
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        if (voiceRecording) return;
                        if (!composerLocked) deliverReply("Сообщение отправлено.");
                      }
                    }}
                    disabled={composerLocked}
                  />
                  <IconButton
                    title="Прикрепить файл"
                    aria-label="Прикрепить файл"
                    disabled={composerLocked}
                    onClick={() => fileInputRef.current?.click()}
                    style={{
                      position: "absolute",
                      left: 6,
                      top: 6,
                      width: 28,
                      height: 28,
                      border: "none",
                      background: "transparent",
                    }}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                      <path
                        d="M21 12.5V17a5 5 0 0 1-10 0V7a3 3 0 1 1 6 0v9.5a1.5 1.5 0 0 1-3 0V8"
                        stroke="currentColor"
                        strokeWidth="2.4"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </IconButton>
                </div>
                <div style={{ position: "relative" }}>
                  {aiImproveModal && !composerLocked ? (
                    <AiImprovePopover
                      t={t}
                      scheme={scheme}
                      state={aiImproveModal}
                      onAccept={handleAcceptAiImprove}
                      onDismiss={handleDismissAiImprove}
                    />
                  ) : null}
                  <Row style={{ gap: 8, justifyContent: "flex-end", alignItems: "center" }}>
                    <Button
                      disabled={composerLocked || reply.trim().length === 0}
                      onClick={handleAiImprove}
                      style={{
                        background: scheme.accentWeak,
                        borderColor: scheme.accent,
                        color: scheme.accentControl,
                        fontWeight: 600,
                      }}
                    >
                      Улучшить с помощью AI
                    </Button>
                    <Button
                      variant="primary"
                      disabled={composerLocked || voiceRecording || (reply.trim().length === 0 && !pendingAttachment)}
                      onClick={() => deliverReply("Сообщение отправлено.")}
                    >
                      Отправить
                    </Button>
                    <VoiceInputButton
                      disabled={composerLocked}
                      currentText={reply}
                      onTranscript={(next) => {
                        onReplyChange(next);
                        setComposerNotice(null);
                      }}
                      onError={(message) => pushComposerNotice(message, "danger")}
                      onRecordingChange={setVoiceRecording}
                    />
                  </Row>
                </div>
              </Stack>
            </div>
          </div>
            </>
          )}
        </div>

        <ColumnResizeHandle
          t={t}
          label="Изменить ширину панели клиента и суфлёра"
          onMouseDown={(event) =>
            startColumnResize(
              event,
              boundedRightWidth,
              setRightWidth,
              ARM_RIGHT_WIDTH_MIN,
              ARM_RIGHT_WIDTH_MAX,
              true,
            )
          }
        />

        {/* Context + Sufler */}
        {rightPanelCollapsed ? (
          <div
            style={{
              width: 28,
              flexShrink: 0,
              ...panelStyle(t, { borderRadius: 0, borderLeft: "none" }),
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              paddingTop: 12,
            }}
          >
            <button
              type="button"
              title="Развернуть панель клиента и суфлёра"
              aria-label="Развернуть панель клиента и суфлёра"
              onClick={() => setRightPanelCollapsed(false)}
              style={{
                border: "none",
                background: "transparent",
                color: scheme.accentControl,
                fontSize: 12,
                cursor: "pointer",
                padding: "4px 2px",
                fontFamily: "inherit",
              }}
            >
              ««
            </button>
          </div>
        ) : (
        <div
          style={{
            width: boundedRightWidth,
            flexShrink: 0,
            minHeight: 0,
            alignSelf: "stretch",
            ...panelStyle(t, { borderRadius: 0, borderLeft: "none" }),
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "10px 12px 0", flexShrink: 0 }}>
            <Row style={{ justifyContent: "flex-end" }}>
              <button
                type="button"
                title="Свернуть панель клиента и суфлёра"
                aria-label="Свернуть панель клиента и суфлёра"
                onClick={() => setRightPanelCollapsed(true)}
                style={{
                  border: "none",
                  background: "transparent",
                  color: t.text.tertiary,
                  fontSize: 12,
                  cursor: "pointer",
                  padding: "2px 4px",
                  fontFamily: "inherit",
                }}
              >
                »»
              </button>
            </Row>
          </div>
          <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "0 12px 12px" }}>
          {viewOnly ? (
            <Callout tone="info" style={{ marginBottom: 12, fontSize: 12 }}>
              Просмотр АРМ оператора {operatorName}
            </Callout>
          ) : null}
          <H3 style={{ fontSize: 15, fontWeight: 700 }}>Summary клиента</H3>
          <ClientSummaryCard
            t={t}
            scheme={scheme}
            data={summaryHistory}
            isExpanded={expandedSummaryCard}
            onToggle={() => setExpandedSummaryCard((open) => !open)}
            disabled={isReadOnly}
          />

          <Divider style={{ margin: "12px 0" }} />
          <H3 style={{ fontSize: 15, fontWeight: 700 }}>Клиент</H3>
          <ClientInfoCard
            t={t}
            scheme={scheme}
            client={clientForCard}
            isExpanded={expandedClientCard}
            onToggle={() => setExpandedClientCard((open) => !open)}
            disabled={isReadOnly}
          />

          <Divider style={{ margin: "12px 0" }} />
          <Row style={{ justifyContent: "space-between", alignItems: "center" }}>
            <H3 style={{ fontSize: 15, fontWeight: 700 }}>Суфлёр</H3>
            <Pill
              tone={
                suflerLoading
                  ? "neutral"
                  : suflerReportVisible
                    ? "warning"
                    : suflerError
                      ? "neutral"
                      : "success"
              }
              size="sm"
            >
              {suflerLoading
                ? "загрузка…"
                : suflerReportVisible
                  ? "недоступен"
                  : suflerError
                    ? "нет ответа"
                    : "активен"}
            </Pill>
          </Row>
          {suflerSuggested && !suflerScenarioPath ? (
            <button
              type="button"
              data-testid="arm-scenario-lamp"
              onClick={() => {
                if (!active?.id) return;
                void enterSuflerScenario(suflerSuggested.code, {
                  sessionId: `chat:${active.id}`,
                  channel: "online_chat",
                }).then((result) => {
                  const usable = result.hints || [];
                  setLiveSuflerRaw(usable);
                  setLiveSuflerHints(usable.map(mapApiHintToCard));
                  if (result.scenario?.path?.length) {
                    setSuflerScenarioPath(
                      `${result.scenario.code} · ${result.scenario.path.join(" → ")}`,
                    );
                  }
                  setSuflerSuggested(null);
                  setSuflerError("");
                }).catch(() => {
                  setSuflerError("Не удалось войти в сценарий.");
                });
              }}
              style={{
                display: "grid",
                gap: 3,
                marginTop: 7,
                padding: "8px 10px",
                border: `1px solid color-mix(in srgb, #e3b341 55%, ${scheme.accent})`,
                borderRadius: 9,
                background: `color-mix(in srgb, #e3b341 16%, ${t.fill.secondary})`,
                textAlign: "left",
                cursor: "pointer",
                color: "inherit",
                font: "inherit",
              }}
            >
              <Text style={{ fontSize: 10, color: "#9a6d00", fontWeight: 700, textTransform: "uppercase" }}>
                Похожий сценарий
              </Text>
              <Text style={{ fontSize: 12, color: t.text.primary }}>
                {suflerSuggested.code} · {suflerSuggested.title}
              </Text>
            </button>
          ) : null}
          {suflerScenarioPath ? (
            <div
              data-testid="arm-scenario-path"
              style={{
                display: "grid",
                gap: 3,
                marginTop: 7,
                padding: "8px 10px",
                border: `1px solid ${scheme.accent}`,
                borderRadius: 9,
                background: `color-mix(in srgb, ${scheme.accent} 10%, ${t.fill.secondary})`,
              }}
            >
              <Text style={{ fontSize: 10, color: scheme.accent, fontWeight: 700, textTransform: "uppercase" }}>
                Активный сценарий
              </Text>
              <Text style={{ fontSize: 12, color: t.text.primary }}>
                {suflerScenarioPath}
              </Text>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  if (!active?.id) return;
                  void exitSuflerScenario(`chat:${active.id}`).then(() => {
                    setSuflerScenarioPath("");
                    setSuflerSuggested(null);
                    setLiveSuflerHints([]);
                    setLiveSuflerRaw([]);
                  });
                }}
              >
                Выйти из сценария
              </Button>
            </div>
          ) : null}
          <div style={{ marginTop: 8 }}>
            <KbPicker
              catalog={kb.catalog}
              selected={kb.selected}
              status={kb.status}
              allSelected={kb.allSelected}
              someSelected={kb.someSelected}
              onToggleAll={kb.toggleAll}
              onToggle={(id, checked) =>
                kb.setSelected((current) => ({ ...current, [id]: checked }))
              }
              compact
            />
          </div>
          {suflerError ? (
            <Callout
              tone={suflerReportVisible ? "warning" : "info"}
              style={{ marginTop: 8, fontSize: 12 }}
            >
              {suflerError}
              {suflerReportVisible ? (
                <div style={{ marginTop: 8 }}>
                  {suflerReportSent ? (
                    <Text style={{ fontSize: 12, color: t.text.secondary }}>
                      Уведомление отправлено супервизору и администратору.
                    </Text>
                  ) : (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={handleReportSuflerOutage}
                      disabled={isReadOnly}
                    >
                      Сообщить о проблеме
                    </Button>
                  )}
                </div>
              ) : null}
            </Callout>
          ) : null}

          <div style={{ position: "relative" }}>
            {liveSuflerHints.map((hint, index) => (
              <SuflerHintCard
                key={hint.id}
                t={t}
                scheme={scheme}
                hint={hint}
                isExpanded={!!expandedHintIds[hint.id]}
                onToggle={() =>
                  setExpandedHintIds((current) => ({
                    ...current,
                    [hint.id]: !current[hint.id],
                  }))
                }
                onInsert={onInsertSufler}
                disabled={isReadOnly}
                onFeedback={(choice) => {
                  const raw = liveSuflerRaw[index];
                  void submitSuflerHintFeedback({
                    dialog_id: active?.id,
                    operator_name: operatorName,
                    query: suflerQuery,
                    hint_rank: raw?.rank ?? index + 1,
                    hint_text: hint.answerText,
                    choice,
                    relevance_percent: raw?.relevance_percent,
                    citation_title: hint.suzTitle,
                    request_id: suflerRequestId,
                    source: "chat",
                  }).catch(() => {});
                }}
              />
            ))}
            {!suflerLoading && !suflerError && liveSuflerHints.length === 0 ? (
              <Text style={{ fontSize: 12, color: t.text.tertiary, marginTop: 8 }}>
                Подсказки появятся после сообщения клиента.
              </Text>
            ) : null}
          </div>
          </div>
        </div>
        )}
        </>
        )}
      </div>

      {!isArmWorkspaceModule(statsTab) ? (
      <div
        style={{
          padding: "6px 16px",
          fontSize: 11,
          color: t.text.tertiary,
          borderTop: `1px solid ${t.stroke.secondary}`,
          background: t.fill.secondary,
          flexShrink: 0,
        }}
      >
        Enter — отправить · Shift+Enter — новая строка · Пробел — голосовой ввод · D — отменить запись · Ctrl+K — шаблоны · F2 — следующий диалог
      </div>
      ) : null}

      {suflerOutageNotice && (armRole === "supervisor" || armRole === "admin") ? (
        <div
          role="alert"
          style={{
            position: "fixed",
            top: 16,
            right: 16,
            zIndex: 1000,
            maxWidth: 360,
            padding: "12px 14px",
            borderRadius: 10,
            background: "#7a1f1f",
            color: "#fff",
            boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
            fontSize: 13,
            lineHeight: 1.4,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 4 }}>Суфлёр недоступен</div>
          <div>
            {suflerOutageNotice.operatorName} сообщил(а) о проблеме с суфлёром.
            {suflerOutageNotice.query
              ? ` Запрос: «${suflerOutageNotice.query.slice(0, 80)}».`
              : ""}
          </div>
          <button
            type="button"
            onClick={() => setSuflerOutageNotice(null)}
            style={{
              marginTop: 8,
              background: "rgba(255,255,255,0.18)",
              color: "#fff",
              border: 0,
              borderRadius: 6,
              padding: "4px 10px",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Понятно
          </button>
        </div>
      ) : null}

      {closeDialogConfirmOpen ? (
        <ConfirmDialog
          t={t}
          titleId="close-dialog-title"
          title="Вы точно хотите закрыть данный диалог?"
          description={`Диалог будет завершён с тематикой «${closeTopic}» и исчезнет из очереди. Отменить закрытие после подтверждения будет нельзя.`}
          confirmLabel="Закрыть"
          onCancel={() => setCloseDialogConfirmOpen(false)}
          onConfirm={handleConfirmCloseDialog}
        />
      ) : null}

      {blockClientConfirmOpen ? (
        <ConfirmDialog
          t={t}
          titleId="block-client-title"
          title="Вы точно хотите заблокировать пользователя?"
          description="Клиент будет отмечен как заблокированный. Отправка сообщений в этом диалоге станет недоступна."
          confirmLabel="Заблокировать"
          onCancel={() => setBlockClientConfirmOpen(false)}
          onConfirm={handleConfirmBlockClient}
        />
      ) : null}

      {transferDialogOpen ? (
        <div
          role="presentation"
          style={{
            position: "absolute",
            inset: 0,
            background: "rgba(15, 28, 22, 0.45)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 40,
            padding: 24,
          }}
          onClick={() => setTransferDialogOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="transfer-dialog-title"
            style={{
              width: "100%",
              maxWidth: 460,
              background: t.bg.elevated,
              border: `1px solid ${t.stroke.secondary}`,
              borderRadius: 12,
              padding: "20px 22px",
              boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <Text
              id="transfer-dialog-title"
              weight="semibold"
              style={{ fontSize: 16, marginBottom: 8, color: t.text.primary }}
            >
              Перевести диалог
            </Text>
            <Text style={{ fontSize: 13, color: t.text.secondary, lineHeight: 1.45, marginBottom: 14 }}>
              Выберите получателя: оператор или супервизор.
            </Text>
            <Text style={{ fontSize: 12, color: t.text.secondary, marginBottom: 6 }}>
              Кому перевести
            </Text>
            <Select
              value={transferTargetKind}
              onChange={(value) => {
                const kind = value === "supervisor" ? "supervisor" : "operator";
                setTransferTargetKind(kind);
                if (kind === "supervisor") {
                  setTransferOperatorName(transferSupervisorsOnly[0]?.name ?? "Козлова Е.В.");
                } else {
                  const firstDept = transferDepartments[0]?.id ?? "";
                  setTransferDepartment(firstDept);
                  const first = transferOperatorsOnly.find((item) => {
                    const deptName = item.department_name?.trim() || "Без отдела";
                    const deptId = String(item.department_id ?? item.department ?? deptName);
                    return deptId === firstDept;
                  });
                  setTransferOperatorName(first?.name ?? "");
                }
              }}
              options={[
                { value: "operator", label: "Оператору" },
                { value: "supervisor", label: "Супервизору" },
              ]}
              style={{ marginBottom: 12 }}
            />
            {transferTargetKind === "operator" ? (
              <>
                <Text style={{ fontSize: 12, color: t.text.secondary, marginBottom: 6 }}>
                  Отдел
                </Text>
                {transferDepartments.length > 0 ? (
                  <Select
                    value={transferDepartment}
                    onChange={(value) => {
                      setTransferDepartment(value);
                      const first = transferOperatorsOnly.find((item) => {
                        const deptName = item.department_name?.trim() || "Без отдела";
                        const deptId = String(item.department_id ?? item.department ?? deptName);
                        return deptId === value;
                      });
                      setTransferOperatorName(first?.name ?? "");
                    }}
                    options={transferDepartments.map((item) => ({ value: item.id, label: item.name }))}
                    style={{ marginBottom: 12 }}
                  />
                ) : (
                  <Text style={{ fontSize: 13, color: t.text.tertiary, marginBottom: 12 }}>
                    Отделы не найдены — показан общий список операторов.
                  </Text>
                )}
                <Text style={{ fontSize: 12, color: t.text.secondary, marginBottom: 6 }}>
                  Оператор
                </Text>
              </>
            ) : (
              <Text style={{ fontSize: 12, color: t.text.secondary, marginBottom: 6 }}>
                Супервизор
              </Text>
            )}
            {transferOperatorOptions.length > 0 ? (
              <Select
                value={transferOperatorName}
                onChange={setTransferOperatorName}
                options={transferOperatorOptions}
                style={{ marginBottom: 16 }}
              />
            ) : (
              <Text style={{ fontSize: 13, color: t.text.tertiary, marginBottom: 16 }}>
                {transferTargetKind === "supervisor"
                  ? "Нет доступных супервизоров."
                  : "В выбранном отделе нет доступных операторов."}
              </Text>
            )}
            <Row style={{ gap: 8, justifyContent: "flex-end" }}>
              <Button variant="secondary" onClick={() => setTransferDialogOpen(false)}>
                Отмена
              </Button>
              <Button
                variant="primary"
                disabled={!transferOperatorName.trim()}
                onClick={handleConfirmTransferDialog}
              >
                Перевести
              </Button>
            </Row>
          </div>
        </div>
      ) : null}

      {editMessageTarget ? (
        <PromptDialog
          t={t}
          scheme={scheme}
          titleId="edit-message-title"
          title="Редактировать сообщение"
          description={
            editMessageTarget.attachment_name
              ? `Можно изменить подпись к файлу «${editMessageTarget.attachment_name}». Сам файл останется прежним и будет доступен для скачивания.`
              : "Изменённый текст увидит клиент. Сообщение будет помечено как отредактированное."
          }
          label={editMessageTarget.attachment_name ? "Подпись к файлу" : "Текст сообщения"}
          value={editMessageText}
          confirmLabel="Сохранить"
          multiline
          onChange={setEditMessageText}
          onCancel={() => setEditMessageTarget(null)}
          onConfirm={handleConfirmEditMessage}
        />
      ) : null}

      {deleteMessageTarget ? (
        <ConfirmDialog
          t={t}
          titleId="delete-message-title"
          title="Удалить сообщение?"
          description="Сообщение будет скрыто в переписке для обеих сторон. Отменить удаление нельзя."
          confirmLabel="Удалить"
          onCancel={() => setDeleteMessageTarget(null)}
          onConfirm={handleConfirmDeleteMessage}
        />
      ) : null}
    </div>
  );
}
