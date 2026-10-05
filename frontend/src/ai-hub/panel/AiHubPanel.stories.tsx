import type { Meta, StoryObj } from '@storybook/react-vite'
import { AiHubPanelHost } from './AiHubPanel'

const meta = {
  title: 'AI Hub/Panel',
  component: AiHubPanelHost,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    roles: ['software_administrator'],
    username: 'Козлов Д.В. · Администратор',
    initialOpen: true,
    initialTab: 'assistant',
  },
} satisfies Meta<typeof AiHubPanelHost>

export default meta
type Story = StoryObj<typeof meta>

export const DefaultAssistant: Story = {}

export const DocumentsOnly: Story = {
  args: {
    roles: ['document_recognition_user'],
    username: 'Петрова А.С. · Верификатор',
    initialTab: 'documents',
  },
}

export const DocumentsUploadFlow: Story = {
  args: {
    roles: ['document_recognition_user'],
    username: 'Петрова А.С. · Верификатор',
    initialTab: 'documents',
    initialDocumentSubTab: 'upload',
    initialPinned: true,
  },
}

export const ActiveCall: Story = {
  args: {
    roles: ['contact_center_telephony_operator'],
    username: 'Иванов И.И. · Оператор КЦ',
    callActive: true,
    initialTab: 'sufler',
  },
}

export const FabClosed: Story = {
  args: {
    roles: ['ai_assistant_user'],
    initialOpen: false,
  },
}
