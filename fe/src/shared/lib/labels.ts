// 서버가 내려주는 enum 코드값 → 화면 문구. 여러 feature가 같은 코드를 쓰므로 여기 둔다.
// 키를 string으로 둔 건 모르는 코드가 와도 화면이 죽지 않게 하려는 것이다(`?? code`로 폴백).
export const ACTION_TYPE_LABEL: Record<string, string> = {
  EXTERNAL_SEND: '외부 발송',
  TRANSFER: '이체',
  EXPENSE: '지출',
  CONTRACT: '계약',
  NOTICE: '공지',
  CONFIRMATION: '확인 요청',
}

export const MEMBER_ROLE_LABEL: Record<string, string> = {
  OWNER: '회장',
  MANAGER: '총무',
  MEMBER: '회원',
}
