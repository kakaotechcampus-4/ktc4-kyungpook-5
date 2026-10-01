// 공통 응답·에러 타입
export interface ApiMeta {
  page: number
  size: number
  totalCount: number
}

// meta는 목록마다 모양이 다르다(페이지네이션이 있으면 ApiMeta, GET /records는 집계값).
// 기본값을 ApiMeta로 둬서 기존 호출부는 그대로 둔다.
export interface ApiSuccess<T, M = ApiMeta> {
  data: T
  meta: M | null
}

export interface ApiErrorBody {
  code: string
  message: string
  fields?: Record<string, string>
}

export class ApiError extends Error {
  code: string
  fields?: Record<string, string>

  constructor(body: ApiErrorBody) {
    super(body.message)
    this.code = body.code
    this.fields = body.fields
  }
}
