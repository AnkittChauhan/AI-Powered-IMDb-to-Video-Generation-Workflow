import type { JobStage } from '@/types/jobs'

export type StageInfo = {
  key: JobStage
  label: string
  shortLabel: string
}

export const PIPELINE_STAGES: StageInfo[] = [
  { key: 'metadata_extraction', label: 'Research Desk', shortLabel: 'Metadata' },
  { key: 'script_generation', label: "Writer's Room", shortLabel: 'Script' },
  { key: 'tts_subtitles', label: 'Recording Booth', shortLabel: 'Voiceover' },
  { key: 'asset_gathering', label: 'Art Department', shortLabel: 'Assets' },
  { key: 'video_composition', label: 'Editing Room', shortLabel: 'Composition' },
  { key: 'export', label: 'Export Bay', shortLabel: 'Export' },
]

export const STAGE_LABELS: Record<JobStage, string> = {
  pending: 'Reception Desk',
  metadata_extraction: 'Research Desk',
  script_generation: "Writer's Room",
  tts_subtitles: 'Recording Booth',
  asset_gathering: 'Art Department',
  video_composition: 'Editing Room',
  export: 'Export Bay',
  completed: 'Pickup Counter',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export function getStageState(stage: JobStage, currentStage: JobStage): 'done' | 'active' | 'waiting' {
  if (currentStage === 'completed') return 'done'
  if (currentStage === 'failed' || currentStage === 'cancelled') return 'waiting'

  const currentIndex = PIPELINE_STAGES.findIndex((item) => item.key === currentStage)
  const stageIndex = PIPELINE_STAGES.findIndex((item) => item.key === stage)

  if (stageIndex < currentIndex) return 'done'
  if (stageIndex === currentIndex) return 'active'
  return 'waiting'
}
