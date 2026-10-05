import type { TestDialogPromptResult, TestDialogTurn } from './api/testDialog'

export const SEED_TURNS: TestDialogTurn[] = [
  {
    id: 'turn-1',
    userText: 'Какой срок действия вклада «Стройсбережения»?',
    userTime: '10:14',
    llmText:
      'Срок вклада «Стройсбережения» определяется договором; минимальный срок — 12 месяцев. Досрочное расторжение — по регламенту продукта.',
    relevance: '91%',
    relevanceTone: 'success',
    sources: [{ title: 'Вклады · Стройсбережения', scenario: 'CC-SCR-008', permalink: 'https://suz.local/articles/deposit-stroysberezheniya' }],
    etalon: 'Срок вклада «Стройсбережения»',
  },
  {
    id: 'turn-2',
    userText: 'На какой период можно открыть вклад «Стройсбережения»?',
    userTime: '10:15',
    llmText:
      'Вклад «Стройсбережения» открывается на срок от 12 до 36 месяцев. Конкретный срок указывается в договоре вклада при оформлении.',
    relevance: '88%',
    relevanceTone: 'success',
    sources: [{ title: 'Вклады · Стройсбережения', scenario: 'CC-SCR-008', permalink: 'https://suz.local/articles/deposit-stroysberezheniya' }],
    etalon: 'Срок вклада «Стройсбережения»',
  },
  {
    id: 'turn-3',
    userText: 'Можно ли закрыть вклад досрочно без потери процентов?',
    userTime: '10:16',
    llmText:
      'При досрочном расторжении вклада «Стройсбережения» проценты пересчитываются по ставке вклада «до востребования» на дату расторжения. Полное сохранение начисленных процентов при досрочном закрытии не предусмотрено.',
    relevance: '76%',
    relevanceTone: 'warning',
    sources: [{ title: 'Вклады · досрочное расторжение', scenario: 'CC-SCR-008', permalink: 'https://suz.local/articles/deposit-early' }],
  },
]

const SCENARIO_META: Record<
  string,
  { title: string; etalon: string; permalink: string }
> = {
  'CC-SCR-008': {
    title: 'Вклады · Стройсбережения',
    etalon: 'Срок вклада «Стройсбережения»',
    permalink: 'https://suz.local/articles/deposit-stroysberezheniya',
  },
  'CC-SCR-003': {
    title: 'Переводы · лимиты',
    etalon: 'Лимиты перевода между счетами',
    permalink: 'https://suz.local/articles/transfers-limits',
  },
  'CC-SCR-001': {
    title: 'Карты · оформление',
    etalon: 'Как оформить банковскую карту',
    permalink: 'https://suz.local/articles/card-issue',
  },
}

function toneFor(percent: number): TestDialogPromptResult['relevance_tone'] {
  if (percent >= 85) return 'success'
  if (percent >= 70) return 'warning'
  return 'danger'
}

/** Deterministic demo answer for Storybook / offline harness. */
export function buildDemoPromptResult(
  text: string,
  scenarioId: string,
): TestDialogPromptResult {
  const meta = SCENARIO_META[scenarioId] ?? SCENARIO_META['CC-SCR-008']
  const lowered = text.toLocaleLowerCase('ru-RU')
  let percent = 68
  let llmText =
    `По сценарию ${scenarioId}: ответ сформирован в test-dialog harness. ` +
    'Уточните формулировку ближе к эталону QU для повышения релевантности.'

  if (lowered.includes('досроч') || lowered.includes('закрыть')) {
    percent = 76
    llmText =
      'При досрочном расторжении проценты пересчитываются по ставке вклада «до востребования». Полное сохранение процентов не предусмотрено.'
  } else if (lowered.includes('документ')) {
    percent = 89
    llmText =
      'Для открытия вклада нужны паспорт и заявление. Дополнительный пакет документов зависит от продукта.'
  } else if (lowered.includes('вклад') || lowered.includes('стройсбереж')) {
    percent = 91
    llmText =
      'Срок вклада определяется договором; минимальный срок — 12 месяцев. Конкретный срок указывается при оформлении.'
  }

  return {
    query: text,
    scenario_id: scenarioId,
    prompt_profile: 'sufler_cc',
    llm_text: llmText,
    relevance_percent: percent,
    relevance_tone: toneFor(percent),
    sources: [
      {
        title: meta.title,
        scenario: scenarioId,
        permalink: meta.permalink,
      },
    ],
    etalon: meta.etalon,
    stub: true,
    request_id: 'demo-test-dialog',
  }
}

export function nowTimeLabel(): string {
  return new Date().toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function resultToTurn(
  result: TestDialogPromptResult,
  id: string,
): TestDialogTurn {
  return {
    id,
    userText: result.query,
    userTime: nowTimeLabel(),
    llmText: result.llm_text,
    relevance: `${result.relevance_percent}%`,
    relevanceTone: result.relevance_tone,
    sources: result.sources,
    etalon: result.etalon,
  }
}
