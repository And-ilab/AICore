import type { Meta, StoryObj } from '@storybook/react-vite'
import { SuflerPhoneApp } from './SuflerPhoneApp'

const meta = {
  title: 'Sufler/Phone Window',
  component: SuflerPhoneApp,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    demoMode: true,
    operatorName: 'Иванова А.С.',
  },
} satisfies Meta<typeof SuflerPhoneApp>

export default meta
type Story = StoryObj<typeof meta>

export const ActiveCall: Story = {}

export const WaitingTranscript: Story = {
  args: {
    demoLines: [],
  },
}
