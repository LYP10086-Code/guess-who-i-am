import axios, { AxiosError } from 'axios'
import type { ErrorEnvelope, ErrorCodeValue } from '../types/api'

export class ApiError extends Error {
  code: ErrorCodeValue
  details: Record<string, unknown>
  requestId: string
  status: number

  constructor(
    code: ErrorCodeValue,
    message: string,
    details: Record<string, unknown>,
    requestId: string,
    status: number,
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.details = details
    this.requestId = requestId
    this.status = status
  }
}

// 唯一策略：相对路径 /api/v1，跨域由 Vite proxy 解决
export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 60_000,
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ErrorEnvelope>) => {
    if (error.response?.data?.error) {
      const envelope = error.response.data
      return Promise.reject(
        new ApiError(
          envelope.error.code,
          envelope.error.message,
          envelope.error.details ?? {},
          envelope.request_id,
          error.response.status,
        ),
      )
    }
    return Promise.reject(
      new ApiError(
        'INTERNAL_ERROR',
        '网络异常，请稍后重试。',
        {},
        '',
        error.response?.status ?? 0,
      ),
    )
  },
)
