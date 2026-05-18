'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { getJob, getVideoUrl, submitJob } from '@/lib/api'
import { PIPELINE_STAGES, STAGE_LABELS, getStageState } from '@/lib/stages'
import type { ApiError, JobProgressResponse, JobStage } from '@/types/jobs'

const SAMPLE_URL = 'https://www.imdb.com/title/tt0111161/'
const TERMINAL_STAGES: JobStage[] = ['completed', 'failed', 'cancelled']

export function JobDashboard() {
  const [imdbUrl, setImdbUrl] = useState(SAMPLE_URL)
  const [job, setJob] = useState<JobProgressResponse | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null)

  const isTerminal = job ? TERMINAL_STAGES.includes(job.status) : false
  const progress = job?.progress?.overall_progress ?? job?.overall_progress ?? 0
  const currentLabel = job ? STAGE_LABELS[job.status] : 'Ready'
  const videoUrl = job?.result?.video_url ? getVideoUrl(job.result.video_url) : null

  const statusTone = useMemo(() => {
    if (!job) return 'border-zinc-800 bg-zinc-950 text-zinc-300'
    if (job.status === 'completed') return 'border-emerald-800 bg-emerald-950 text-emerald-100'
    if (job.status === 'failed' || job.status === 'cancelled') return 'border-red-900 bg-red-950 text-red-100'
    return 'border-amber-800 bg-amber-950 text-amber-100'
  }, [job])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setJob(null)
    setJobId(null)
    setIsSubmitting(true)

    try {
      const response = await submitJob(imdbUrl.trim())
      setJobId(response.job_id)
      const initialStatus = await getJob(response.job_id)
      setJob(initialStatus)
      setLastCheckedAt(new Date().toLocaleTimeString())
    } catch (caughtError) {
      const apiError = caughtError as ApiError
      setError(apiError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  useEffect(() => {
    if (!jobId || isTerminal) return

    let cancelled = false
    const intervalId = window.setInterval(async () => {
      try {
        const nextJob = await getJob(jobId)
        if (!cancelled) {
          setJob(nextJob)
          setLastCheckedAt(new Date().toLocaleTimeString())
          setError(null)
        }
      } catch (caughtError) {
        const apiError = caughtError as ApiError
        if (!cancelled) setError(apiError.message)
      }
    }, 2500)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [jobId, isTerminal])

  return (
    <main className="min-h-screen bg-[#101114] px-4 py-6 text-zinc-100 sm:px-6 lg:px-8">
      <section className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[minmax(340px,420px)_1fr]">
        <aside className="flex flex-col gap-5">
          <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-5">
            <div className="mb-5">
              <p className="text-xs font-medium uppercase tracking-wide text-amber-300">Movie Factory</p>
              <h1 className="mt-2 text-2xl font-semibold leading-tight text-white">
                IMDb to cinematic video
              </h1>
              <p className="mt-3 text-sm leading-6 text-zinc-400">
                Submit a movie URL and track the backend pipeline as it moves through each
                production station.
              </p>
            </div>

            <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
              <label className="text-sm font-medium text-zinc-200" htmlFor="imdb-url">
                IMDb movie URL
              </label>
              <input
                id="imdb-url"
                className="h-11 rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-white outline-none transition focus:border-amber-400 focus:ring-2 focus:ring-amber-400/20"
                value={imdbUrl}
                onChange={(event) => setImdbUrl(event.target.value)}
                placeholder={SAMPLE_URL}
                type="url"
              />
              <button
                className="mt-2 h-11 rounded-md bg-amber-300 px-4 text-sm font-semibold text-zinc-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
                disabled={isSubmitting || !imdbUrl.trim()}
                type="submit"
              >
                {isSubmitting ? 'Submitting job...' : 'Start generation'}
              </button>
            </form>

            {error ? (
              <div className="mt-4 rounded-md border border-red-900 bg-red-950 px-3 py-3 text-sm text-red-100">
                {error}
              </div>
            ) : null}
          </div>

          <div className={clsx('rounded-lg border p-5', statusTone)}>
            <p className="text-xs font-medium uppercase tracking-wide opacity-75">Current station</p>
            <div className="mt-3 flex items-end justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold">{currentLabel}</h2>
                <p className="mt-1 text-xs opacity-75">{job?.job_id ?? 'No active job'}</p>
              </div>
              <p className="text-3xl font-semibold">{Math.round(progress)}%</p>
            </div>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-black/30">
              <div
                className="h-full rounded-full bg-current transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
              />
            </div>
            <p className="mt-3 text-xs opacity-75">
              {lastCheckedAt ? `Last checked ${lastCheckedAt}` : 'Waiting for first job'}
            </p>
          </div>
        </aside>

        <section className="flex flex-col gap-6">
          <PipelineBoard currentStage={job?.status ?? 'pending'} />

          <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
            <ResultPanel job={job} videoUrl={videoUrl} />
            <DebugPanel job={job} />
          </div>
        </section>
      </section>
    </main>
  )
}

function PipelineBoard({ currentStage }: { currentStage: JobStage }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Pipeline stations</h2>
          <p className="mt-1 text-sm text-zinc-400">Each station owns one backend stage.</p>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {PIPELINE_STAGES.map((stage, index) => {
          const state = getStageState(stage.key, currentStage)
          return (
            <div
              key={stage.key}
              className={clsx(
                'min-h-[116px] rounded-lg border p-4 transition',
                state === 'done' && 'border-emerald-800 bg-emerald-950/60',
                state === 'active' && 'border-amber-600 bg-amber-950/70',
                state === 'waiting' && 'border-zinc-800 bg-zinc-900/60',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-xs text-zinc-500">Stage {index + 1}</p>
                <span
                  className={clsx(
                    'rounded-full px-2 py-1 text-xs',
                    state === 'done' && 'bg-emerald-300 text-emerald-950',
                    state === 'active' && 'bg-amber-300 text-amber-950',
                    state === 'waiting' && 'bg-zinc-800 text-zinc-400',
                  )}
                >
                  {state}
                </span>
              </div>
              <h3 className="mt-3 text-base font-semibold text-white">{stage.label}</h3>
              <p className="mt-1 text-sm text-zinc-400">{stage.shortLabel}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ResultPanel({
  job,
  videoUrl,
}: {
  job: JobProgressResponse | null
  videoUrl: string | null
}) {
  if (!job) {
    return (
      <div className="flex min-h-[340px] items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950 p-6 text-center">
        <div>
          <h2 className="text-lg font-semibold text-white">No job running</h2>
          <p className="mt-2 max-w-md text-sm leading-6 text-zinc-400">
            Submit an IMDb URL to start the backend workflow and watch each station light up.
          </p>
        </div>
      </div>
    )
  }

  if (job.status === 'failed') {
    return (
      <div className="rounded-lg border border-red-900 bg-red-950 p-6">
        <h2 className="text-lg font-semibold text-red-100">Job failed</h2>
        <p className="mt-2 text-sm leading-6 text-red-100/80">
          {job.error?.message ?? 'The backend reported a failure.'}
        </p>
        <p className="mt-4 text-xs text-red-100/60">
          Stage: {job.error?.stage ? STAGE_LABELS[job.error.stage] : STAGE_LABELS[job.status]}
        </p>
      </div>
    )
  }

  if (job.status === 'completed' && videoUrl) {
    return (
      <div className="rounded-lg border border-emerald-800 bg-zinc-950 p-5">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Final video ready</h2>
            <p className="mt-1 text-sm text-zinc-400">{job.result?.display_name ?? job.job_id}</p>
          </div>
          <a
            className="rounded-md bg-emerald-300 px-4 py-2 text-sm font-semibold text-emerald-950 transition hover:bg-emerald-200"
            href={videoUrl}
          >
            Download MP4
          </a>
        </div>
        <video className="aspect-video w-full rounded-md bg-black" controls src={videoUrl} />
      </div>
    )
  }

  return (
    <div className="flex min-h-[340px] items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950 p-6 text-center">
      <div>
        <h2 className="text-lg font-semibold text-white">Production in progress</h2>
        <p className="mt-2 max-w-md text-sm leading-6 text-zinc-400">
          Current station: {STAGE_LABELS[job.status]}. The preview unlocks when export completes.
        </p>
      </div>
    </div>
  )
}

function DebugPanel({ job }: { job: JobProgressResponse | null }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-5">
      <h2 className="text-lg font-semibold text-white">Job details</h2>
      <dl className="mt-4 grid gap-3 text-sm">
        <DetailRow label="Job ID" value={job?.job_id ?? '-'} />
        <DetailRow label="Status" value={job?.status ?? 'idle'} />
        <DetailRow label="Created" value={job?.created_at ? formatDate(job.created_at) : '-'} />
        <DetailRow label="Elapsed" value={formatSeconds(job?.progress?.elapsed_seconds)} />
        <DetailRow
          label="ETA"
          value={
            job?.progress?.estimated_remaining_seconds
              ? formatSeconds(job.progress.estimated_remaining_seconds)
              : '-'
          }
        />
      </dl>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-h-8 items-center justify-between gap-3 border-b border-zinc-900 pb-2">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="max-w-[210px] truncate text-right text-zinc-200" title={value}>
        {value}
      </dd>
    </div>
  )
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function formatSeconds(value?: number): string {
  if (value === undefined || value === null) return '-'
  if (value < 60) return `${value}s`
  const minutes = Math.floor(value / 60)
  const seconds = value % 60
  return `${minutes}m ${seconds}s`
}
