import type { Meta, StoryObj } from '@storybook/react-vite'
import { KbAdminScreen } from './KbAdminScreen'

const meta = {
  title: 'AI Hub/KB Admin',
  component: KbAdminScreen,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof KbAdminScreen>

export default meta
type Story = StoryObj<typeof meta>

export const WebsiteReady: Story = {
  args: {
    canEdit: true,
    demoKb: {
      key: 'assistant:7',
      kind: 'assistant',
      id: 7,
      name: 'Сайт belarusbank.by',
      description: 'Публичные страницы банка',
      source: 'website',
      source_label: 'Сайт',
      module_label: 'Ассистент',
      status: 'ready',
      status_message: 'Индекс актуален',
      document_count: 2,
      index_percent: 100,
      webhook_status: 'IDLE',
      webhook_label: '—',
      start_url: 'https://docs.example.com/',
      crawl_depth: 3,
      max_pages: 200,
      ignore_robots: false,
      allowed_hosts: ['docs.example.com'],
      latest_job: {
        id: 1,
        status: 'ready',
        status_message: 'Индекс актуален',
        pages_ok: 2,
        pages_4xx: 0,
        pages_5xx: 0,
        pages_skipped: 0,
        started_at: '2026-09-08T10:00:00Z',
        finished_at: '2026-09-08T10:01:00Z',
        elapsed_seconds: 60,
        created_by: 'admin',
        created_at: '2026-09-08T10:00:00Z',
      },
      documents: [
        {
          id: 1,
          filename: 'Главная',
          size_bytes: 1200,
          status: 'indexed',
          index_percent: 100,
          source_label: 'Сайт',
          url: 'https://docs.example.com/',
        },
        {
          id: 2,
          filename: 'О банке',
          size_bytes: 800,
          status: 'indexed',
          index_percent: 100,
          source_label: 'Сайт',
          url: 'https://docs.example.com/about',
        },
      ],
    },
  },
}
