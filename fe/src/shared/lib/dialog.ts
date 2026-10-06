// 모달(<dialog>)이 열리면 그 바깥은 가려지고 고르거나 누를 수도 없다(inert).
// 토스트 · 복사용 입력칸처럼 화면에 잠깐 붙이는 것은 맨 위 모달 안에, 없으면 body에 붙인다.
// ponytail: 나중에 연 모달이 문서에서도 뒤에 있다고 본다. 앞쪽에 그려 놓고 나중에 여는 모달이 생기면 열린 순서를 따로 센다.
export function topModalOrBody(): Element {
  const open = document.querySelectorAll('dialog[open]')
  return open[open.length - 1] ?? document.body
}
