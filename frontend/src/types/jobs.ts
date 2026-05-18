export type JobStage =
  | 'pending'
  | 'metadata_extraction'
  | 'script_generation'
  | 'tts_subtitles'
  | 'asset_gathering'
  | 'video_composition'
  | 'export'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type JobSubmitResponse = {
  job_id: string
  status: JobStage
  created_at: string
  poll_url?: string
}

export type JobProgressDetail = {
  current_stage: JobStage
  overall_progress: number
  stage_progress?: number
  elapsed_seconds: number
  estimated_remaining_seconds?: number
}

export type JobErrorDetail = {
  message: string
  stage?: JobStage
  retry_count?: number
  error_code?: string
}

export type VideoResultDetail = {
  video_url: string
  display_name?: string
  file_size_mb?: number
  duration_seconds?: number
}

export type JobProgressResponse = {
  job_id: string
  status: JobStage
  overall_progress: number
  current_stage: JobStage
  created_at: string
  started_at?: string
  updated_at?: string
  progress?: JobProgressDetail
  error?: JobErrorDetail
  result?: VideoResultDetail
}

export type ApiError = {
  error_code?: string
  message: string
}
