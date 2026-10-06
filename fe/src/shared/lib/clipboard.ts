// 글자를 클립보드에 복사한다. 성공하면 true.
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // navigator.clipboard는 HTTPS(또는 localhost)에서만 있고, 권한이 막혀도 실패한다.
    // 그때는 숨긴 입력칸에 넣고 골라서 복사한다.
    const el = document.createElement('textarea')
    el.value = text
    el.style.position = 'fixed'
    el.style.opacity = '0'
    // 모달(<dialog>)이 열려 있으면 그 바깥은 고를 수 없어서 모달 안에 붙인다
    const host = document.querySelector('dialog[open]') ?? document.body
    host.append(el)
    el.select()
    const ok = document.execCommand('copy')
    el.remove()
    return ok
  }
}
