import type { Meta, StoryObj } from '@storybook/react-vite'
import { PortalLauncher } from './PortalLauncher'

const meta = {
  title: 'Portal/Launcher',
  component: PortalLauncher,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    roles: ['contact_center_telephony_operator'],
    initialMenuOpen: true,
  },
} satisfies Meta<typeof PortalLauncher>

export default meta
type Story = StoryObj<typeof meta>

export const MenuOpen: Story = {}

export const BothWindows: Story = {
  args: {
    roles: ['software_administrator'],
    initialMenuOpen: false,
    initialWindows: ['sufler', 'assistant'],
  },
}

export const Unauthorized: Story = {
  args: {
    roles: ['document_recognition_analyst'],
    initialMenuOpen: true,
  },
}

export const CompactMenu: Story = {
  args: {
    roles: ['contact_center_telephony_operator'],
    menuVariant: 'compact',
    initialMenuOpen: true,
    roleLabel: 'Оператор канала телефония Контакт-центра',
    username: 'Иванова М.П.',
  },
}
