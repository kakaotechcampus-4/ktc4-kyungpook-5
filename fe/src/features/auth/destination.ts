export function safeDestination(next: string | null): string {
  if (!next) return '/dashboard'
  try {
    const url = new URL(next, window.location.origin)
    const invite =
      url.pathname === '/signup' &&
      /^\/[a-zA-Z0-9_-]+$/.test(`/${url.searchParams.get('invite') ?? ''}`) &&
      [...url.searchParams.keys()].every((key) => key === 'invite') &&
      url.searchParams.getAll('invite').length === 1
    if (
      url.origin !== window.location.origin ||
      url.pathname.startsWith('//') ||
      url.pathname === '/login' ||
      url.pathname === '/auth/kakao/callback' ||
      (url.pathname === '/signup' && !invite)
    )
      return '/dashboard'
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return '/dashboard'
  }
}
