import type { BudgetChartData } from '@/features/dashboard/types'

const WIDTH = 700
const HEIGHT = 220
const PAD_LEFT = 60
const PAD_RIGHT = 50
const PAD_TOP = 20
const PAD_BOTTOM = 30
const PLOT_WIDTH = WIDTH - PAD_LEFT - PAD_RIGHT
const PLOT_HEIGHT = HEIGHT - PAD_TOP - PAD_BOTTOM
const BAR_WIDTH = 32

function toManwon(value: number): string {
  return `${Math.round(value / 10000)}만`
}

function points(values: (number | null)[], xOf: (i: number) => number, yOf: (v: number) => number): string {
  return values
    .map((v, i) => (v == null ? null : `${xOf(i)},${yOf(v)}`))
    .filter((p): p is string => p !== null)
    .join(' ')
}

export function BudgetChart({ data, todayIndex }: { data: BudgetChartData; todayIndex: number }) {
  const { labels, actualBalances, planLine, historicalLine } = data
  const allValues = [...actualBalances, ...planLine, ...historicalLine].filter(
    (v): v is number => v !== null,
  )
  const max = Math.max(...allValues)
  const min = Math.min(...allValues)
  const domainPadding = (max - min) * 0.25 || max * 0.1
  const domainMax = max + domainPadding
  const domainMin = Math.max(0, min - domainPadding)

  const xOf = (i: number) => PAD_LEFT + (i / (labels.length - 1)) * PLOT_WIDTH
  const yOf = (v: number) => PAD_TOP + (1 - (v - domainMin) / (domainMax - domainMin)) * PLOT_HEIGHT

  const ticks = [domainMax, (domainMax + domainMin) / 2, domainMin]
  const planPoints = points(planLine, xOf, yOf)
  const historicalPoints = points(historicalLine, xOf, yOf)

  const lastPlanIndex = planLine.reduce<number>((acc, v, i) => (v != null ? i : acc), -1)
  const lastHistoricalIndex = historicalLine.reduce<number>((acc, v, i) => (v != null ? i : acc), -1)
  const lastPlanValue = lastPlanIndex >= 0 ? planLine[lastPlanIndex] : null
  const lastHistoricalValue = lastHistoricalIndex >= 0 ? historicalLine[lastHistoricalIndex] : null

  return (
    <div className="flex flex-1 flex-col gap-[10px]">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT + 30}`} className="w-full" role="img" aria-label="예산 전망 차트">
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD_LEFT}
              x2={WIDTH - PAD_RIGHT + 16}
              y1={yOf(tick)}
              y2={yOf(tick)}
              stroke="#ededed"
              strokeWidth={1}
            />
            <text x={PAD_LEFT - 8} y={yOf(tick) + 4} textAnchor="end" fontSize={10} fill="#8c8c8c">
              {toManwon(tick)}
            </text>
          </g>
        ))}

        <line
          x1={xOf(todayIndex)}
          x2={xOf(todayIndex)}
          y1={PAD_TOP - 14}
          y2={PAD_TOP + PLOT_HEIGHT}
          stroke="#ccc"
          strokeWidth={1}
        />
        <rect x={xOf(todayIndex) - 19} y={PAD_TOP - 24} width={38} height={20} rx={5} fill="white" stroke="#d9d9d9" />
        <text x={xOf(todayIndex)} y={PAD_TOP - 10} textAnchor="middle" fontSize={10} fill="#595959">
          오늘
        </text>

        {actualBalances.map((value, i) =>
          value == null ? null : (
            <g key={i}>
              <rect
                x={xOf(i) - BAR_WIDTH / 2}
                y={yOf(value)}
                width={BAR_WIDTH}
                height={PAD_TOP + PLOT_HEIGHT - yOf(value)}
                rx={5}
                fill="#383838"
              />
              <text x={xOf(i)} y={yOf(value) - 8} textAnchor="middle" fontSize={9.5} fill="#4d4d4d" fontWeight={500}>
                {toManwon(value)}
              </text>
            </g>
          ),
        )}

        {historicalPoints && <polyline points={historicalPoints} fill="none" stroke="#949494" strokeWidth={2} strokeDasharray="5 4" />}
        {planPoints && <polyline points={planPoints} fill="none" stroke="#333" strokeWidth={2} />}

        {planLine.map((value, i) =>
          value == null || i < todayIndex + 1 ? null : (
            <circle key={`plan-${i}`} cx={xOf(i)} cy={yOf(value)} r={4} fill="#333" />
          ),
        )}
        {historicalLine.map((value, i) =>
          value == null || i < todayIndex + 1 ? null : (
            <circle key={`hist-${i}`} cx={xOf(i)} cy={yOf(value)} r={4} fill="#949494" />
          ),
        )}

        {lastPlanValue != null && (
          <text x={xOf(lastPlanIndex) + 12} y={yOf(lastPlanValue) - 4} fontSize={10} fill="#2e2e2e" fontWeight={700}>
            {toManwon(lastPlanValue)}
          </text>
        )}
        {lastHistoricalValue != null && (
          <text x={xOf(lastHistoricalIndex) + 12} y={yOf(lastHistoricalValue) + 14} fontSize={10} fill="#808080">
            {toManwon(lastHistoricalValue)}
          </text>
        )}

        {labels.map((label, i) => (
          <text
            key={label}
            x={xOf(i)}
            y={PAD_TOP + PLOT_HEIGHT + 20}
            textAnchor="middle"
            fontSize={10}
            fill={i === todayIndex ? '#404040' : '#808080'}
            fontWeight={i === todayIndex ? 500 : 400}
          >
            {label}
          </text>
        ))}
      </svg>

      <div className="flex items-center gap-[18px] pl-[60px]">
        <span className="flex items-center gap-[6px]">
          <span className="size-[11px] rounded-[3px] bg-[#383838]" />
          <span className="text-[10.5px] text-[#666]">실제 잔고 (확정)</span>
        </span>
        <span className="flex items-center gap-[6px]">
          <span className="h-[3px] w-[18px] bg-[#949494]" style={{ backgroundImage: 'repeating-linear-gradient(to right, #949494 0 4px, transparent 4px 7px)' }} />
          <span className="text-[10.5px] text-[#666]">과거 평균 기준 예측</span>
        </span>
        <span className="flex items-center gap-[6px]">
          <span className="h-[3px] w-[18px] bg-[#333]" />
          <span className="text-[10.5px] text-[#666]">현재 계획 기준 예상</span>
        </span>
      </div>
    </div>
  )
}
