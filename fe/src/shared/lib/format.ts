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
