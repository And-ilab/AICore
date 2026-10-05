import type { Meta, StoryObj } from '@storybook/react-vite'
import { Sidebar } from './Sidebar'

const meta = {
  title: 'Foundation/Sidebar',
  component: Sidebar,
  parameters: { layout: 'fullscreen' },
  args: {
    items: [
      { label: 'Диалоги', href: '#dialogs', active: true },
      { label: 'Подсказки', href: '#hints' },
      { label: 'Отчёты', href: '#reports' },
    ],
    style: { minHeight: 420 },
  },
} satisfies Meta<typeof Sidebar>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}
