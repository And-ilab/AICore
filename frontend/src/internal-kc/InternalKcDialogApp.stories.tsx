import type { Meta, StoryObj } from '@storybook/react-vite'
import { InternalKcDialogApp } from './InternalKcDialogApp'

const meta = {
  title: 'Internal KC/Test Dialog',
  component: InternalKcDialogApp,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    demoMode: true,
    username: 'Внутренний пользователь КЦ',
    initiallyOpen: true,
  },
  decorators: [
    (Story) => (
      <div style={{ width: 900, height: 700, overflow: 'hidden' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof InternalKcDialogApp>

export default meta
type Story = StoryObj<typeof meta>

/** II.3.5.5 / II-KC — canvas internal-user-kc-mockup layout. */
export const PromptHarness: Story = {}

export const ClosedWindow: Story = {
  args: {
    initiallyOpen: false,
  },
}
