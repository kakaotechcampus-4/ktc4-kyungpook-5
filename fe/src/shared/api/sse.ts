// SSE(text/event-stream) 본문을 이벤트로 나눈다. 네트워크와 무관한 순수 함수다.
//
// 서버는 이벤트마다 아래처럼 보내고 빈 줄로 끝낸다. ':'로 시작하는 줄은 주석(heartbeat)이다.
//   event: reply_delta
//   data: {"text":"예상 인원을 "}
//
// 네트워크 조각은 줄·글자 중간에서 잘려 올 수 있어, 빈 줄이 올 때까지 모아 둔다.

export interface SseEvent {
  event: string
  data: string
}

export function createSseParser(onEvent: (event: SseEvent) => void) {
  let buffer = ''
  let event = 'message'
  let data: string[] = []

  const line = (text: string) => {
    if (text === '') {
      if (data.length) onEvent({ event, data: data.join('\n') })
      event = 'message'
      data = []
      return
    }
    if (text.startsWith(':')) return
    const colon = text.indexOf(':')
    const field = colon < 0 ? text : text.slice(0, colon)
    let value = colon < 0 ? '' : text.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }

  return {
    push(chunk: string) {
      buffer += chunk
      const lines = buffer.split(/\r\n|\r|\n/)
      // 마지막 조각은 아직 줄이 끝나지 않았을 수 있다.
      buffer = lines.pop() ?? ''
      for (const text of lines) line(text)
    },
    // 스트림이 끝났을 때 남은 줄을 처리한다. 빈 줄 없이 끝난 이벤트는 완성되지 않은 것이라 버린다.
    end() {
      if (buffer) line(buffer)
      buffer = ''
      event = 'message'
      data = []
    },
  }
}
