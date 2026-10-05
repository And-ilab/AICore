import type { Meta, StoryObj } from '@storybook/react-vite'
import { HintCard } from './HintCard'

const content =
  'Для оформления карты потребуется паспорт. Заявку можно подать в отделении или через интернет-банкинг. Срок выпуска зависит от выбранного продукта и региона обслуживания.'

const meta = {
  title: 'Foundation/HintCard',
  component: HintCard,
  args: {
    title: 'Рекомендуемый ответ',
    relevance: 'Релевантность 96%',
    children: content,
    style: { width: 520 },
  },
} satisfies Meta<typeof HintCard>

export default meta
type Story = StoryObj<typeof meta>

export const Compact: Story = { args: { defaultExpanded: false } }
export const Expanded: Story = {
  args: {
    defaultExpanded: true,
    relevance: '96%',
    relevancePercent: 96,
    relevanceStatus: 'success',
    suzLink: {
      title: 'Оформление банковской карты',
      href: 'https://suz.local/articles/101',
    },
  },
}

export const KnowledgeBaseWithMore: Story = {
  args: {
    defaultExpanded: true,
    title: 'Переводы в РФ — лимиты',
    relevance: '92%',
    relevancePercent: 92,
    showMore: true,
    detailText:
      'Перевод в РФ доступен через «Платежи» → «За рубеж» в мобильном банке или интернет-банке. Перед отправкой проверьте суточный лимит клиента, статус карты и разрешение на международные операции. Актуальные комиссии сверяйте в статье СУЗ.',
    suzLink: {
      title: 'Переводы в РФ — лимиты',
      href: 'https://suz.local/articles/201',
    },
    children:
      'Перевод в РФ доступен через «Платежи» → «За рубеж». Проверьте суточный лимит клиента и статус карты.',
  },
}

export const WithFeedbackAndShades: Story = {
  args: {
    defaultExpanded: true,
    title: 'Переводы в РФ — лимиты',
    relevance: '92%',
    relevancePercent: 92,
    showFeedback: true,
    hintIndex: 1,
    hintTotal: 3,
    suzLink: {
      title: 'Переводы в РФ — лимиты',
      href: 'https://suz.local/articles/201',
    },
    children:
      'Перевод в РФ доступен через «Платежи» → «За рубеж». Проверьте суточный лимит клиента и статус карты.',
  },
}
