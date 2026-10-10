// ③ 동아리 찾기. 검색 → 결과 카드 고르기 → 내 역할. 참여 모드에서만 보인다.
// 못 찾았을 때 막다른 길이 되지 않게 「동아리 새로 만들기」를 함께 둔다.
import { Field } from '@/features/auth/components/AuthShell'
import type { ClubSearchResult } from '@/features/auth/types'
import { EXECUTIVE_ROLES } from '@/features/auth/types'
import { cn } from '@/shared/lib/cn'
import { Avatar } from '@/shared/ui/Avatar'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { Input } from '@/shared/ui/Input'

interface ClubSearchFieldProps {
  query: string
  onQueryChange: (value: string) => void
  results: ClubSearchResult[]
  selected?: ClubSearchResult
  onSelect: (club: ClubSearchResult) => void
  role: string
  onRoleChange: (role: string) => void
  onCreateInstead: () => void
}

export function ClubSearchField({
  query,
  onQueryChange,
  results,
  selected,
  onSelect,
  role,
  onRoleChange,
  onCreateInstead,
}: ClubSearchFieldProps) {
  // 검색어를 넣었는데 결과가 없을 때만 「없어요」를 보인다. 비어 있으면 아직 안 찾은 것이다.
  const searched = query.trim().length > 0
  const notFound = searched && results.length === 0

  return (
    <div className="flex flex-col gap-[14px]">
      <Field label="동아리 찾기">
        <Input
          placeholder="동아리 이름을 입력하세요"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
        />
      </Field>

      {!searched && <p className="text-[11.5px] text-mute">동아리 이름을 검색해 주세요</p>}

      {results.map((club) => {
        const picked = club.id === selected?.id
        return (
          <button
            key={club.id}
            type="button"
            onClick={() => onSelect(club)}
            className={cn(
              'flex items-center gap-[12px] rounded-[12px] border px-[14px] py-[12px] text-left',
              picked ? 'border-blue-600 bg-blue-50' : 'border-line bg-card hover:bg-bg',
            )}
          >
            <Avatar name={club.name} size={32} />
            <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
              <span className="truncate text-[13px] font-bold text-ink">{club.name}</span>
              <span className="text-[10.5px] text-mute">
                {club.field} · 대표 {club.ownerName} · 임원 {club.executiveCount}명
              </span>
            </span>
            {picked && (
              <Chip tone="approved" size="sm">
                선택됨
              </Chip>
            )}
          </button>
        )
      })}

      {notFound && (
        <div className="flex flex-col items-start gap-[10px] rounded-[12px] border border-line bg-bg px-[14px] py-[14px]">
          <p className="text-[11.5px] text-mute">“{query}”로 찾은 동아리가 없어요</p>
          <Button type="button" variant="soft" size="sm" onClick={onCreateInstead}>
            동아리 새로 만들기
          </Button>
        </div>
      )}

      {selected && (
        <div className="flex flex-col gap-[7px]">
          <Field label="내 역할" required>
            <select
              value={role}
              onChange={(e) => onRoleChange(e.target.value)}
              className="w-full rounded-[11px] border border-soft bg-bg px-[15px] py-[12px] text-[13.5px] text-ink outline-none focus:border-blue-600 focus:bg-card"
            >
              {EXECUTIVE_ROLES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>
          <p className="text-[10.5px] text-mute">
            임원만 계정을 만듭니다. 일반 동아리원은 명단에만 등록돼요.
          </p>
        </div>
      )}
    </div>
  )
}
