import { useMemo, useState } from 'react'

const TONE_COLOR: Record<string, string> = {
  success: '#2e7d32',
  warning: '#c47f17',
  danger: '#c62828',
  info: '#0c4da2',
  neutral: '#7a8a82',
}

export interface PieSlice {
  label: string
  value: number
  tone?: string
  pct?: number
}

export function BarChartView({
  categories,
  series,
  valueSuffix = '',
}: {
  categories: string[]
  series: { name: string; data: number[]; tone?: string }[]
  valueSuffix?: string
}) {
  const [zoom, setZoom] = useState(1)
  const [hovered, setHovered] = useState<number | null>(null)

  const max = Math.max(1, ...series.flatMap((item) => item.data))
  const colWidth = Math.min(72, Math.max(28, 48 * zoom))
  const chartWidth = Math.max(categories.length * (colWidth + 12), 140)

  return (
    <div className="rpt-chart-wrap">
      <div className="rpt-chart-toolbar">
        <button type="button" className="rpt-btn rpt-btn--ghost" onClick={() => setZoom((z) => Math.min(z + 0.25, 2.5))} aria-label="Увеличить">
          +
        </button>
        <button type="button" className="rpt-btn rpt-btn--ghost" onClick={() => setZoom((z) => Math.max(z - 0.25, 0.5))} aria-label="Уменьшить">
          −
        </button>
      </div>
      <div className="rpt-bars-scroll">
        <div
          className={`rpt-bars${hovered != null ? ' has-hover' : ''}`}
          style={{ width: chartWidth, margin: categories.length <= 2 ? '0 auto' : undefined }}
        >
          {categories.map((category, index) => {
            const isHovered = hovered === index
            const isDimmed = hovered != null && !isHovered
            return (
              <div
                key={`${category}-${index}`}
                className={`rpt-bars__col${isHovered ? ' is-hovered' : ''}${isDimmed ? ' is-dimmed' : ''}`}
                style={{ width: colWidth, maxWidth: 96, flex: categories.length <= 2 ? '0 0 auto' : undefined }}
                onMouseEnter={() => setHovered(index)}
                onMouseLeave={() => setHovered(null)}
              >
                <div className="rpt-bars__plot">
                  {series.map((item, seriesIndex) => {
                    const value = item.data[index] ?? 0
                    const heightPct = (value / max) * 100
                    return (
                      <div
                        key={item.name}
                        className={`rpt-bars__bar${seriesIndex > 0 ? ' rpt-bars__bar--alt' : ''}`}
                        style={{
                          height: `${heightPct}%`,
                          background: item.tone === 'success' ? TONE_COLOR.success : undefined,
                        }}
                        title={`${item.name}: ${value}${valueSuffix}`}
                      />
                    )
                  })}
                </div>
                <span className="rpt-bars__value">
                  {series.map((item) => item.data[index]).filter((v) => v != null).join(' / ')}
                  {valueSuffix}
                </span>
                <span className="rpt-bars__label">{category}</span>
              </div>
            )
          })}
        </div>
      </div>
      <div className="rpt-row" style={{ marginTop: 10 }}>
        {series.map((item, index) => (
          <span key={item.name} className="rpt-muted">
            <span
              className="rpt-pie__dot"
              style={{
                display: 'inline-block',
                marginRight: 6,
                background: index === 0 ? 'var(--rpt-accent)' : '#52b896',
              }}
            />
            {item.name}
          </span>
        ))}
      </div>
      {hovered != null ? (
        <div className="rpt-chart-tooltip">
          {categories[hovered]}: {series.map((item) => item.data[hovered]).join(' / ')}
          {valueSuffix}
        </div>
      ) : null}
    </div>
  )
}

export function PieChartView({
  data,
  onSelect,
}: {
  data: PieSlice[]
  onSelect?: (label: string) => void
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const total = useMemo(() => data.reduce((sum, item) => sum + item.value, 0) || 1, [data])

  const size = 200
  const cx = size / 2
  const cy = size / 2
  const outer = 82
  const inner = 42

  const slices = useMemo(() => {
    let angle = -Math.PI / 2
    return data.map((item, index) => {
      const share = item.value / total
      const start = angle
      const end = angle + share * Math.PI * 2
      angle = end
      const large = end - start > Math.PI ? 1 : 0
      const color = TONE_COLOR[item.tone || 'info'] || 'var(--rpt-accent)'
      const mid = (start + end) / 2
      const ox = Math.cos(start) * outer
      const oy = Math.sin(start) * outer
      const ex = Math.cos(end) * outer
      const ey = Math.sin(end) * outer
      const ix = Math.cos(end) * inner
      const iy = Math.sin(end) * inner
      const jx = Math.cos(start) * inner
      const jy = Math.sin(start) * inner
      const d = [
        `M ${cx + ox} ${cy + oy}`,
        `A ${outer} ${outer} 0 ${large} 1 ${cx + ex} ${cy + ey}`,
        `L ${cx + ix} ${cy + iy}`,
        `A ${inner} ${inner} 0 ${large} 0 ${cx + jx} ${cy + jy}`,
        'Z',
      ].join(' ')
      return { ...item, index, color, d, mid, popX: Math.cos(mid) * 16, popY: Math.sin(mid) * 16 }
    })
  }, [cx, cy, data, inner, outer, total])

  return (
    <div className={`rpt-pie${hoveredIndex != null ? ' has-hover' : ''}`}>
      <div className="rpt-pie__stage">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="rpt-pie__svg">
          {slices.map((slice) => {
            const active = hoveredIndex === slice.index
            const dimmed = hoveredIndex != null && !active
            return (
              <path
                key={slice.label}
                d={slice.d}
                fill={slice.color}
                className={`rpt-pie__seg${active ? ' is-hovered' : ''}${dimmed ? ' is-dimmed' : ''}`}
                style={{
                  transform: active ? `translate(${slice.popX}px, ${slice.popY}px)` : undefined,
                  transformOrigin: `${cx}px ${cy}px`,
                }}
                onMouseEnter={() => setHoveredIndex(slice.index)}
                onMouseLeave={() => setHoveredIndex(null)}
              >
                <title>{`${slice.label}: ${slice.value}`}</title>
              </path>
            )
          })}
        </svg>
      </div>
      <div className="rpt-pie__legend">
        {data.map((item, index) => {
          const pct = item.pct ?? Math.round((item.value / total) * 100)
          const className = `rpt-pie__legend-item${hoveredIndex === index ? ' is-hovered' : ''}${hoveredIndex != null && hoveredIndex !== index ? ' is-dimmed' : ''}${onSelect ? ' rpt-pie__legend-item--btn' : ''}`
          const body = (
            <>
              <span
                className="rpt-pie__dot"
                style={{ background: TONE_COLOR[item.tone || 'info'] }}
              />
              <span>
                {item.label} — {item.value} ({pct}%)
              </span>
            </>
          )
          if (onSelect) {
            return (
              <button
                key={item.label}
                type="button"
                className={className}
                onMouseEnter={() => setHoveredIndex(index)}
                onMouseLeave={() => setHoveredIndex(null)}
                onClick={() => onSelect(item.label)}
              >
                {body}
              </button>
            )
          }
          return (
            <div
              key={item.label}
              className={className}
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              {body}
            </div>
          )
        })}
      </div>
      {hoveredIndex != null ? (
        <div className="rpt-chart-tooltip rpt-chart-tooltip--pie">
          {data[hoveredIndex].label}: {data[hoveredIndex].value} (
          {data[hoveredIndex].pct ?? Math.round((data[hoveredIndex].value / total) * 100)}%)
        </div>
      ) : null}
    </div>
  )
}

export function DataTable({
  headers,
  rows,
  onRowClick,
}: {
  headers: string[]
  rows: string[][]
  onRowClick?: (row: string[], index: number) => void
}) {
  return (
    <div className="rpt-table-wrap">
      <table className="rpt-table">
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={`${row[0]}-${index}`}
              onClick={onRowClick ? () => onRowClick(row, index) : undefined}
              style={onRowClick ? { cursor: 'pointer' } : undefined}
              title={onRowClick ? 'Открыть диалог' : undefined}
            >
              {row.map((cell, cellIndex) => (
                <td key={`${index}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
