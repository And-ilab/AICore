/** Brand color schemes from canvases/online-chat-mockups (light + dark). */

export type ColorSchemeId =
  | 'default'
  | 'belarusbank_classic'
  | 'belarusbank_soft'
  | 'belarusbank_emerald'
  | 'belarusbank_night'

export const COLOR_SCHEME_ORDER: ColorSchemeId[] = [
  'default',
  'belarusbank_classic',
  'belarusbank_soft',
  'belarusbank_emerald',
  'belarusbank_night',
]

export const COLOR_SCHEME_LABELS: Record<ColorSchemeId, string> = {
  default: 'Текущая',
  belarusbank_classic: 'Classic',
  belarusbank_soft: 'Soft',
  belarusbank_emerald: 'Emerald',
  belarusbank_night: 'Night',
}

export type SchemePalette = {
  accent: string
  accentWeak: string
  accentControl: string
  headerBg: string
  panelBg: string
  badge: string
  surface: string
  surfaceMuted: string
  border: string
  text: string
  textMuted: string
  onAccent: string
}

const LIGHT: Record<Exclude<ColorSchemeId, 'default'>, SchemePalette> = {
  belarusbank_classic: {
    accent: '#0C4DA2',
    accentWeak: '#BFD3F3',
    accentControl: '#0A3F87',
    headerBg: 'linear-gradient(135deg, #EAF2FF 0%, #DCEAFF 55%, #F4F8FF 100%)',
    panelBg: 'linear-gradient(180deg, #F7FAFF 0%, #EDF4FF 100%)',
    badge: '#C62828',
    surface: '#FFFFFF',
    surfaceMuted: '#F0F5FF',
    border: '#C5D4EE',
    text: '#14233D',
    textMuted: '#5D6C89',
    onAccent: '#FFFFFF',
  },
  belarusbank_soft: {
    accent: '#2E5AAC',
    accentWeak: '#C8D6EF',
    accentControl: '#2A4F93',
    headerBg: 'linear-gradient(135deg, #F3F7FF 0%, #EAF1FF 58%, #FDFEFF 100%)',
    panelBg: 'linear-gradient(180deg, #FAFCFF 0%, #F1F6FF 100%)',
    badge: '#D46A6A',
    surface: '#FFFFFF',
    surfaceMuted: '#F5F8FF',
    border: '#D0DBEF',
    text: '#1A2740',
    textMuted: '#5D6C89',
    onAccent: '#FFFFFF',
  },
  belarusbank_emerald: {
    accent: '#007A43',
    accentWeak: '#BEE8D5',
    accentControl: '#00663A',
    headerBg: 'linear-gradient(135deg, #EAF8F1 0%, #DCF3E8 58%, #F2FBF6 100%)',
    panelBg: 'linear-gradient(180deg, #F5FCF8 0%, #EAF7F1 100%)',
    badge: '#0B9E5E',
    surface: '#FFFFFF',
    surfaceMuted: '#EFF9F3',
    border: '#B8DCC8',
    text: '#143024',
    textMuted: '#4A6B58',
    onAccent: '#FFFFFF',
  },
  belarusbank_night: {
    accent: '#0D5C86',
    accentWeak: '#C5D9E6',
    accentControl: '#0A4D70',
    headerBg: 'linear-gradient(135deg, #E8F1F8 0%, #D8E8F4 60%, #EFF6FB 100%)',
    panelBg: 'linear-gradient(180deg, #F3F8FC 0%, #E6F1F8 100%)',
    badge: '#2D7FB8',
    surface: '#FFFFFF',
    surfaceMuted: '#EEF5FA',
    border: '#C0D4E4',
    text: '#142830',
    textMuted: '#4A6575',
    onAccent: '#FFFFFF',
  },
}

/** Lighter emerald (and peers) for dark host — from canvas v1.4.74. */
const DARK: Record<Exclude<ColorSchemeId, 'default'>, SchemePalette> = {
  belarusbank_classic: {
    accent: '#6AA8F0',
    accentWeak: '#2A4570',
    accentControl: '#8BBCF5',
    headerBg: 'linear-gradient(135deg, #15253D 0%, #1A2F4A 55%, #182433 100%)',
    panelBg: 'linear-gradient(180deg, #121A28 0%, #152235 100%)',
    badge: '#EF5350',
    surface: '#1A2436',
    surfaceMuted: '#152033',
    border: '#2A4570',
    text: '#E8EEF8',
    textMuted: '#9AABC4',
    onAccent: '#0A1628',
  },
  belarusbank_soft: {
    accent: '#8AA8E0',
    accentWeak: '#2C3A58',
    accentControl: '#A4BAE8',
    headerBg: 'linear-gradient(135deg, #1A2233 0%, #1F2A40 58%, #181F2C 100%)',
    panelBg: 'linear-gradient(180deg, #141A26 0%, #1A2434 100%)',
    badge: '#E08080',
    surface: '#1C2434',
    surfaceMuted: '#171E2C',
    border: '#2C3A58',
    text: '#E8ECF5',
    textMuted: '#9AA6BC',
    onAccent: '#121820',
  },
  belarusbank_emerald: {
    accent: '#6FD4A0',
    accentWeak: '#244A38',
    accentControl: '#8EE0B4',
    headerBg: 'linear-gradient(135deg, #1A3428 0%, #214835 58%, #1C3A2C 100%)',
    panelBg: 'linear-gradient(180deg, #173028 0%, #1E3C30 100%)',
    badge: '#52B896',
    surface: '#1A3228',
    surfaceMuted: '#152A22',
    border: '#2A5640',
    text: '#E6F5EC',
    textMuted: '#9ABDAA',
    onAccent: '#0C1A14',
  },
  belarusbank_night: {
    accent: '#5BA4D4',
    accentWeak: '#1A3344',
    accentControl: '#7AB8DE',
    headerBg: 'linear-gradient(135deg, #122430 0%, #173040 60%, #142028 100%)',
    panelBg: 'linear-gradient(180deg, #0F1C24 0%, #152A36 100%)',
    badge: '#4A9AD0',
    surface: '#152830',
    surfaceMuted: '#112028',
    border: '#1A3344',
    text: '#E4F0F6',
    textMuted: '#96B0C0',
    onAccent: '#0A141A',
  },
}

export function resolveSchemePalette(
  scheme: ColorSchemeId,
  prefersDark: boolean,
): SchemePalette | null {
  if (scheme === 'default') return null
  return prefersDark ? DARK[scheme] : LIGHT[scheme]
}

export function schemeCssVars(palette: SchemePalette | null): Record<string, string> {
  if (!palette) return {}
  return {
    '--arm-accent': palette.accent,
    '--arm-accent-weak': palette.accentWeak,
    '--arm-accent-control': palette.accentControl,
    '--arm-header-bg': palette.headerBg,
    '--arm-panel-bg': palette.panelBg,
    '--arm-badge': palette.badge,
    '--arm-surface': palette.surface,
    '--arm-surface-muted': palette.surfaceMuted,
    '--arm-border': palette.border,
    '--arm-text': palette.text,
    '--arm-text-muted': palette.textMuted,
    '--arm-on-accent': palette.onAccent,
  }
}
