import type { ApiError, JobProgressResponse, JobSubmitResponse } from '@/types/jobs'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

type BackendErrorPayload = {
  detail?: {
    error_code?: string
    message?: string
  }
  message?: string
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    let payload: BackendErrorPayload = {}
    try {
      payload = (await response.json()) as BackendErrorPayload
    } catch {
      payload = {}
    }

    const apiError: ApiError = {
      error_code: payload.detail?.error_code,
      message: payload.detail?.message ?? payload.message ?? `Request failed with ${response.status}`,
    }
    throw apiError
  }

  return (await response.json()) as T
}

export function submitJob(imdbUrl: string): Promise<JobSubmitResponse> {
  return requestJson<JobSubmitResponse>('/api/jobs', {
    method: 'POST',
    body: JSON.stringify({ imdb_url: imdbUrl }),
  })
}

export function getJob(jobId: string): Promise<JobProgressResponse> {
  return requestJson<JobProgressResponse>(`/api/jobs/${jobId}`)
}

export function getVideoUrl(videoPath: string): string {
  return `${API_BASE_URL}${videoPath}`
}
