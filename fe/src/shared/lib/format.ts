// formatCurrency, formatDate
export function formatCurrency(amount: number): string {
  return `${amount.toLocaleString('ko-KR')}원`
}

export function formatSignedCurrency(amount: number): string {
  const sign = amount > 0 ? '+' : amount < 0 ? '−' : ''
  return `${sign}${Math.abs(amount).toLocaleString('ko-KR')}`
}

// "3/21–3/22" 처럼 짧게 표기한다. 종료일이 없거나 시작일과 같으면 "3/27".
export function formatDateRange(startDate: string | null, endDate: string | null): string {
  if (!startDate) return '일정 미정'
  const short = (iso: string) => {
    const [, month, day] = iso.split('-')
    return `${Number(month)}/${Number(day)}`
  }
  return endDate && endDate !== startDate
    ? `${short(startDate)}–${short(endDate)}`
    : short(startDate)
}

// 서버는 시각을 ISO UTC로 주는데 화면 문구는 한국 기준이다. 표시 시점에만 KST로 바꾼다.
const MONTH_DAY = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Seoul',
  month: 'numeric',
  day: 'numeric',
})
const MONTH_DAY_TIME = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Seoul',
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

// "2026-03-12T14:59:00Z" → "3/12"
export function formatMonthDay(iso: string): string {
  return MONTH_DAY.format(new Date(iso))
}

// "2026-03-08T08:02:00Z" → "3/8 17:02"
export function formatDateTime(iso: string): string {
  return MONTH_DAY_TIME.format(new Date(iso)).replace(',', '')
}

// "2026-03-01T02:00:00Z" → "2026. 3. 1." (ko-KR medium이 정확히 이 모양이다)
const DOT_DATE = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'medium' })

export function formatDotDate(iso: string): string {
  return DOT_DATE.format(new Date(iso))
}
