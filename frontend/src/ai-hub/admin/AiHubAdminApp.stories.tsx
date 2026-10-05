import type { Meta, StoryObj } from '@storybook/react-vite'
import { AiHubAdminApp } from './AiHubAdminApp'

const meta = {
  title: 'AI Hub/Admin Shell',
  component: AiHubAdminApp,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    roles: ['software_administrator'],
    initialScreen: 'llm_config_assistant',
    demoRoleSwitcher: true,
    skipSessionBootstrap: true,
  },
} satisfies Meta<typeof AiHubAdminApp>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const ModelParameters: Story = {
  args: {
    initialScreen: 'model_params',
    initialProfile: 'assistant',
    initialModelParams: {
      profile: 'assistant_bank',
      slot: 'llm_assistant_bank',
      generation: {
        temperature: 0.35,
        top_p: 0.9,
        max_tokens: 1200,
        response_chars_max: 1200,
        preset: 'standard',
      },
      rag: {
        chunk_size_tokens: 512,
        chunk_overlap_tokens: 64,
        context_inclusion: 0.72,
        deterministic_answer: 0.95,
      },
      read_only: {
        dev_model: 'stub:assistant_bank',
        prod_candidate: null,
        status: 'approved_dev',
        context_window: '≥8200',
        llm_model_label: 'assist-v2',
      },
      presets: {
        short: { label: 'Краткий', values: { temperature: 0.2, response_chars_max: 600 } },
        standard: { label: 'По умолчанию', values: { temperature: 0.35, response_chars_max: 1200 } },
        long: { label: 'Подробнее', values: { temperature: 0.5, response_chars_max: 2000 } },
      },
      platform_defaults: {
        temperature: 0.35,
        top_p: 0.9,
        max_tokens: 1200,
        response_chars_max: 1200,
        preset: 'standard',
        chunk_size_tokens: 512,
        chunk_overlap_tokens: 64,
        context_inclusion_threshold: 0.72,
        deterministic_answer_threshold: 0.95,
      },
      constraints: {
        temperature: { min: 0, max: 1, step: 0.01 },
        top_p: { min: 0.01, max: 1, step: 0.01 },
        max_tokens: { min: 1, max: 32768 },
        response_chars_max: { min: 10, max: 4000 },
      },
      revision: 1,
      updated_at: '2026-07-20T12:00:00Z',
      updated_by: 'admin',
    },
  },
}

export const QuPreview: Story = {
  args: {
    initialScreen: 'qu_admin',
  },
}

export const KnowledgeBases: Story = {
  args: {
    initialScreen: 'kb_admin',
    roles: ['llm_knowledge_base_administrator'],
  },
}

export const PromptsAssistant: Story = {
  args: {
    initialScreen: 'prompts_assistant',
    roles: ['ai_assistant_module_administrator'],
  },
}

export const CapabilitiesRegistry: Story = {
  args: {
    initialScreen: 'capabilities',
    roles: ['ai_assistant_module_administrator'],
  },
}

export const ReadOnlyAudit: Story = {
  args: {
    initialScreen: 'audit',
  },
  play: async ({ canvasElement }) => {
    const select = canvasElement.querySelector<HTMLSelectElement>('select')
    if (select) {
      select.value = 'auditor'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    }
  },
}
