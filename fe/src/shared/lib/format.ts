// formatCurrency, formatDate
export function formatCurrency(amount: number): string {
  return `${amount.toLocaleString('ko-KR')}원`
}

export function formatSignedCurrency(amount: number): string {
  const sign = amount > 0 ? '+' : amount < 0 ? '−' : ''
  return `${sign}${Math.abs(amount).toLocaleString('ko-KR')}`
}
