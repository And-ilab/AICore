import type { Meta, StoryObj } from '@storybook/react-vite'
import { AsrQaScreen } from './AsrQaScreen'

const meta = {
  title: 'AI Hub/Reports/AsrQaScreen',
  component: AsrQaScreen,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof AsrQaScreen>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}
