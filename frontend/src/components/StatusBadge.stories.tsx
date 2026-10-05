import type { Meta, StoryObj } from '@storybook/react-vite'
import { StatusBadge } from './StatusBadge'

const meta = {
  title: 'Foundation/StatusBadge',
  component: StatusBadge,
  args: { status: 'success', children: 'В сети' },
} satisfies Meta<typeof StatusBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Success: Story = {}
export const Warning: Story = { args: { status: 'warning', children: 'Перерыв' } }
export const Danger: Story = { args: { status: 'danger', children: 'Ошибка' } }
