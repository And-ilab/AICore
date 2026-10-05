import type { Meta, StoryObj } from '@storybook/react-vite'
import { AssistantWindowApp } from './AssistantWindowApp'

const meta = {
  title: 'Assistant/Window',
  component: AssistantWindowApp,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    demoMode: true,
    username: 'Сидоров П.К. · Пользователь ИИ-ассистента',
    initiallyOpen: true,
  },
  decorators: [
    (Story) => (
      <div style={{ width: 900, height: 720, overflow: 'hidden' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof AssistantWindowApp>

export default meta
type Story = StoryObj<typeof meta>

/** Part III.3 — chat lenta, streaming, tools, feedback (canvas ai-assistant-ui-mockup). */
export const ChatWithSources: Story = {}

export const CompactStreamingDemo: Story = {
  args: {
    username: 'Demo streaming',
  },
}
