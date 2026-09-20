// 공통 응답·에러 타입
export interface ApiMeta {
  page: number
  size: number
  totalCount: number
}

export interface ApiSuccess<T> {
  data: T
  meta: ApiMeta | null
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
