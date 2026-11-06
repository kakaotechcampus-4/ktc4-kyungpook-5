// 화면이 크게 바뀌는 순간을 브라우저의 View Transitions로 잇는다.
// 브라우저가 바뀌기 전 화면을 찍어 두고, 같은 view-transition-name이 붙은 요소를
// 앞 위치에서 뒤 위치로 옮기며 나머지는 겹쳐 바꾼다. 움직임 모양은 styles/index.css에 있다.
//
// 지원하지 않는 브라우저에서는 그냥 바로 바꾼다. 움직임 줄이기 설정의 처리도 CSS가 맡는다.
import { flushSync } from 'react-dom'

export function withViewTransition(update: () => void) {
  if (typeof document === 'undefined' || typeof document.startViewTransition !== 'function') {
    update()
    return
  }
  // 바뀐 화면을 찍으려면 React가 이 콜백 안에서 그려야 한다.
  document.startViewTransition(() => flushSync(update))
}
