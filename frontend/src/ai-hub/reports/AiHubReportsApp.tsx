import { CcReportsScreen } from './CcReportsScreen'
import { LiveOpsScreen } from './LiveOpsScreen'
import { AsrQaScreen } from './AsrQaScreen'
import './ReportsTheme.css'

export type ReportsSection = 'chat' | 'sufler' | 'live' | 'asr-qa'

interface AiHubReportsAppProps {
  username?: string
  section?: ReportsSection
}

function resolveSection(pathname: string, explicit?: ReportsSection): ReportsSection {
  if (explicit && (explicit === 'chat' || explicit === 'live')) return explicit
  if (pathname.includes('/live')) return 'live'
  return 'chat'
}

const TABS: { id: ReportsSection; label: string; path: string; title: string }[] = [
  {
    id: 'chat',
    label: 'Онлайн-чат',
    path: '/ai-hub/reports/chat',
    title: 'Аналитика онлайн-чата',
  },
  {
    id: 'live',
    label: 'Оперативная панель',
    path: '/ai-hub/reports/live',
    title: 'Оперативная панель',
  },
]

export function AiHubReportsApp({
  section,
}: AiHubReportsAppProps) {
  const active = resolveSection(window.location.pathname, section)

  const go = (next: ReportsSection) => {
    const target = TABS.find((item) => item.id === next) || TABS[0]
    window.location.assign(target.path)
  }

  return (
    <main className="rpt-app" data-testid="reports-app" data-scheme="belarusbank_emerald">
      <div className="rpt-frame">
        <header className="rpt-header">
          <a
            className="rpt-header__logo"
            href="/"
            title="На портал"
            aria-label="На портал"
          >
            <img src="/assets/belarusbank-logo.png" alt="" />
          </a>
          <div className="rpt-header__titles">
            <h1>Аналитика контакт-центра</h1>
          </div>
        </header>

        <nav className="rpt-tabs" aria-label="Разделы">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`rpt-tab${active === item.id ? ' is-active' : ''}`}
              onClick={() => go(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        {active === 'chat' || active === 'sufler' ? (
          <CcReportsScreen
            domain={active}
            initialPanel={
              window.location.pathname.includes('/builder')
              || window.location.search.includes('builder')
                ? 'builder'
                : 'reports'
            }
          />
        ) : null}
        {active === 'live' ? <LiveOpsScreen /> : null}
        {active === 'asr-qa' ? <AsrQaScreen /> : null}
      </div>
    </main>
  )
}
