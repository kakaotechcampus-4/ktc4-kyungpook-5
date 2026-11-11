export function demoNavigationPath(pathname: string, search: string, hash = ''): string | null {
  const params = new URLSearchParams(search)
  if (!params.has('demo')) return null
  params.delete('demo')
  const query = params.toString()
  return `${pathname}${query ? `?${query}` : ''}${hash}`
}

export function supportsDemoPath(pathname: string): boolean {
  return ['/dashboard', '/planning', '/events', '/mypage'].some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  )
}
