"""생성 모델이 보내는 계획 JSON 조각에서 단계 코드가 끝나는 순간을 찾는다(#389).

모델은 {"steps":[{"code":"ASSIGN_ROLES","purpose":"…",…},{"code":"RESEARCH_VENUE",…},…],"excluded_steps":[…],…}
를 수백 조각으로 나눠 보낸다. 조각은 키·값 중간에서 끊길 수 있다.

    조각 1: {"steps":[{"co
    조각 2: de":"ASSIGN_ROL
    조각 3: ES","purpose":"역할을 \\"code\\" 기준으로 나눠요 {임시}"   ← 문자열 안의 "code"·{ 는 무시한다
    조각 4: ,…},{"code":"RESEARCH_VENUE",
    → feed(조각 3) == [(0, "ASSIGN_ROLES")]   0번째 단계의 code 값이 닫는 따옴표로 끝났다
    → feed(조각 4) == [(1, "RESEARCH_VENUE")]

문자열 검색으로는 purpose 글 속의 "code"나 excluded_steps의 code와 구분할 수 없어서,
따옴표·이스케이프·괄호 깊이를 한 글자씩 따라간다. 읽는 위치가 최상위 객체의 "steps" 배열 안,
단계 객체의 "code" 키 값일 때만 코드를 돌려준다. 나머지 글은 모으지 않고 지나간다.

검증 전 글이므로 여기서 찾은 코드는 진행 표시에만 쓴다. 형식이 깨진 글을 받아도 예외를 내지 않는다.
최종 판단은 지금처럼 다 받은 뒤의 형식 검사와 validate_plan이 한다.
"""


class StepCodeReader:
    def __init__(self) -> None:
        # 열린 객체·배열. 객체는 [키, 값 차례인가], 배열은 None.
        self._frames: list[list | None] = []
        self._in_string = False
        self._escape = False
        self._is_key = False
        self._chars: list[str] | None = None  # 키이거나 단계 code 값일 때만 글자를 모은다
        self._steps_opened = 0  # steps 배열 안에서 연 단계 객체 수 = 다음 단계의 위치
        self._last_found = -1  # 이미 돌려준 마지막 단계 위치. 한 단계에 code 키가 두 번 와도 한 번만 알린다

    def feed(self, text: str) -> list[tuple[int, str]]:
        """새 조각을 읽고, 이 조각에서 값이 끝난 단계 코드를 (위치, 코드) 순서대로 돌려준다."""
        found: list[tuple[int, str]] = []
        for char in text:
            if self._in_string:
                self._read_string_char(char, found)
            elif char == '"':
                self._start_string()
            elif char == ':':
                if self._top_object():
                    self._frames[-1][1] = True
            elif char == ',':
                if self._top_object():
                    self._frames[-1][1] = False
            elif char in '{[':
                if char == '{' and self._in_steps_array():
                    self._steps_opened += 1
                self._frames.append([None, False] if char == '{' else None)
            elif char in '}]':
                if self._frames:
                    self._frames.pop()
        return found

    def _read_string_char(self, char: str, found: list[tuple[int, str]]) -> None:
        if self._escape:
            self._escape = False
            if self._chars is not None:
                self._chars.append(char)
        elif char == '\\':
            self._escape = True
        elif char == '"':
            self._in_string = False
            self._end_string(found)
        elif self._chars is not None:
            self._chars.append(char)

    def _start_string(self) -> None:
        self._in_string = True
        top = self._frames[-1] if self._frames else None
        # 객체 안에서 콜론 앞이면 키, 그 밖은 값이다.
        self._is_key = top is not None and not top[1]
        self._chars = [] if self._is_key or self._at_step_code() else None

    def _end_string(self, found: list[tuple[int, str]]) -> None:
        if self._is_key:
            self._frames[-1][0] = ''.join(self._chars or ())
        elif self._chars is not None and self._steps_opened - 1 > self._last_found:
            # 닫는 따옴표가 온 순간이 "이 단계의 코드를 다 썼다"이다.
            self._last_found = self._steps_opened - 1
            found.append((self._last_found, ''.join(self._chars)))
        self._chars = None

    def _top_object(self) -> bool:
        return bool(self._frames) and self._frames[-1] is not None

    def _in_steps_array(self) -> bool:
        # 깊이 1: 최상위 객체의 지금 키가 "steps" / 깊이 2: 그 값인 배열
        frames = self._frames
        return len(frames) == 2 and frames[0] is not None and frames[0][0] == 'steps' and frames[1] is None

    def _at_step_code(self) -> bool:
        # 깊이 3: steps 배열 안 단계 객체에서 "code" 키의 값 자리
        frames = self._frames
        return (len(frames) == 3 and frames[0] is not None and frames[0][0] == 'steps' and frames[1] is None
                and frames[2] is not None and frames[2][0] == 'code' and frames[2][1])
