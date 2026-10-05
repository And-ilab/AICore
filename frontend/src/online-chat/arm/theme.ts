import type { CSSProperties } from 'react'

export type ThemeKind = 'light' | 'dark'

export type ArmTheme = {
  kind: ThemeKind
  accent: { primary: string; control: string }
  fill: { secondary: string; tertiary: string; quaternary: string }
  stroke: { secondary: string; tertiary: string }
  text: { primary: string; secondary: string; tertiary: string; onAccent: string }
  bg: { elevated: string; editor: string }
  palette: { diffStripRemoved: string; diffStripAdded: string }
  diff: { insertedLine: string; stripAdded: string }
}

export const ARM_THEME_LIGHT: ArmTheme = {
  kind: 'light',
  accent: { primary: '#007A43', control: '#00663A' },
  fill: { secondary: '#F0F5F2', tertiary: '#E7F0EB', quaternary: '#DDE8E2' },
  stroke: { secondary: '#C9D8CF', tertiary: '#D9E5DD' },
  text: { primary: '#1F2A24', secondary: '#5A6B62', tertiary: '#7A8A82', onAccent: '#FFFFFF' },
  bg: { elevated: '#FFFFFF', editor: '#FFFFFF' },
  palette: { diffStripRemoved: '#C62828', diffStripAdded: '#2E7D32' },
  diff: { insertedLine: '#E8F5E9', stripAdded: '#2E7D32' },
}

export const ARM_THEME_DARK: ArmTheme = {
  kind: 'dark',
  accent: { primary: '#6FD4A0', control: '#8EE0B4' },
  fill: { secondary: '#1A3028', tertiary: '#214035', quaternary: '#152822' },
  stroke: { secondary: '#2F4A3C', tertiary: '#274034' },
  text: { primary: '#E8F5EE', secondary: '#9AB5A6', tertiary: '#7A9488', onAccent: '#0A1A12' },
  bg: { elevated: '#173028', editor: '#12261F' },
  palette: { diffStripRemoved: '#EF5350', diffStripAdded: '#52B896' },
  diff: { insertedLine: '#1F8A6524', stripAdded: '#52B896' },
}

export type { CSSProperties }
