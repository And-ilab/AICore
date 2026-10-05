import type { Meta, StoryObj } from '@storybook/react-vite'
import { Fab } from './Fab'

const meta = {
  title: 'Foundation/Fab',
  component: Fab,
  args: { 'aria-label': 'Открыть чат', children: '💬', badge: 3 },
} satisfies Meta<typeof Fab>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}
