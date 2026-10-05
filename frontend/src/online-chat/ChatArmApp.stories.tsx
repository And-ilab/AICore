import type { Meta, StoryObj } from '@storybook/react-vite'
import { ChatArmApp } from './ChatArmApp'

const meta = {
  title: 'Online Chat/ARM',
  component: ChatArmApp,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    demoMode: true,
    operatorName: 'Иванов И.И.',
    initialPresence: 'online',
  },
  decorators: [
    (Story) => (
      <div style={{ width: 1280, height: 860, overflow: 'hidden' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ChatArmApp>

export default meta
type Story = StoryObj<typeof meta>

/** Canvas-identical operator ARM (online-chat-mockups · АРМ оператора). */
export const OperatorWorkspace: Story = {}

export const OnBreak: Story = {
  args: {
    initialPresence: 'break',
  },
}
