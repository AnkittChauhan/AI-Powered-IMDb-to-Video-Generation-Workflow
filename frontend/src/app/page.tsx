const stages = [
  'Metadata',
  'Script',
  'Voiceover',
  'Assets',
  'Composition',
  'Export',
]

export default function HomePage() {
  return (
    <main className="min-h-screen px-6 py-10">
      <section className="mx-auto flex max-w-5xl flex-col gap-10">
        <div className="flex flex-col gap-4">
          <p className="text-sm uppercase tracking-wide text-amber-300">Phase 1 Foundation</p>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-white">
            AI-Powered IMDb-to-Video Generation Workflow
          </h1>
          <p className="max-w-2xl text-base leading-7 text-zinc-300">
            The production workflow shell is ready: submit an IMDb URL, track a queued job, and
            evolve the backend pipeline stage by stage.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {stages.map((stage, index) => (
            <div key={stage} className="rounded-lg border border-zinc-800 bg-zinc-950 p-5">
              <p className="text-sm text-zinc-500">Stage {index + 1}</p>
              <h2 className="mt-2 text-lg font-medium text-zinc-100">{stage}</h2>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}
