// 마이 페이지 서버 상태 훅. ?demo면 부르지 않고 화면이 예시(mock.ts)를 쓴다.
import { useQuery } from '@tanstack/react-query'
import { getMembers, type MemberOut } from '@/features/mypage/api'
import type { Member } from '@/features/mypage/types'
import { useAuthStore } from '@/shared/auth/store'
import { formatDateTime } from '@/shared/lib/format'

// accountAt은 계정 있음이면 최근 로그인, 초대함이면 초대 보낸 시각이다(문구는 FE가 꾸민다).
function toMember(row: MemberOut): Member {
  const at = row.accountAt ? formatDateTime(row.accountAt) : ''
  return {
    id: row.id,
    name: row.name,
    group: row.group,
    subtitle: row.subtitle,
    contact: row.contact ?? undefined,
    account: row.account,
    // 시각이 없으면 undefined로 둬야 화면이 「명단에만 있음」으로 넘어간다('' 는 ??를 통과하지 못한다).
    accountNote: at ? (row.account === 'INVITED' ? `${at} 초대` : `최근 접속 ${at}`) : undefined,
  }
}

export function useMembers(demo: boolean) {
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['mypage', 'members', clubId],
    queryFn: async (): Promise<Member[]> =>
      clubId ? (await getMembers(clubId)).map(toMember) : [],
    enabled: !demo,
  })
}
