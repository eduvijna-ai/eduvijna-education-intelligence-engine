import { useEffect, useState } from 'react'

import { resolveCapabilities } from '../../capability/readiness'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { FailClosedAction } from '../../components/FailClosedAction'
import { StemRenderer } from '../../components/StemRenderer'
import { STUDENT_RUNNER_FIXTURES } from '../../fixtures/questions-student'

type Responses = Record<string, string | string[]>

export function StudentRunnerPage() {
  const runner = resolveCapabilities().student_runner
  const items = STUDENT_RUNNER_FIXTURES
  const [index, setIndex] = useState(0)
  const [responses, setResponses] = useState<Responses>({})
  const [seconds, setSeconds] = useState(0)
  const current = items[index]

  useEffect(() => {
    const id = window.setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => window.clearInterval(id)
  }, [])

  if (!current) return null

  const progress = `${index + 1} / ${items.length}`

  return (
    <section className="panel runner">
      <header className="page-header">
        <h2>Student runner (non-actionable demo)</h2>
        <CapabilityBadge state={runner.readiness} />
      </header>
      <div className="runner-meta" role="status">
        <span>Progress: {progress}</span>
        <span>Timer: {seconds}s (local only)</span>
      </div>
      <article className="question-card" data-testid="student-question">
        <StemRenderer source={current.stem} className="stem" />
        {current.type === 'mcq' && current.options ? (
          <fieldset>
            <legend className="sr-only">Options</legend>
            {current.options.map((opt) => (
              <label key={opt} className="option-label">
                <input
                  type="radio"
                  name={current.id}
                  value={opt}
                  checked={responses[current.id] === opt}
                  onChange={() => setResponses((r) => ({ ...r, [current.id]: opt }))}
                />
                {opt}
              </label>
            ))}
          </fieldset>
        ) : null}
        {current.type === 'multiselect' && current.options ? (
          <fieldset>
            <legend className="sr-only">Multi select</legend>
            {current.options.map((opt) => {
              const selected = Array.isArray(responses[current.id])
                ? (responses[current.id] as string[])
                : []
              return (
                <label key={opt} className="option-label">
                  <input
                    type="checkbox"
                    checked={selected.includes(opt)}
                    onChange={(e) => {
                      const next = e.target.checked
                        ? [...selected, opt]
                        : selected.filter((x) => x !== opt)
                      setResponses((r) => ({ ...r, [current.id]: next }))
                    }}
                  />
                  {opt}
                </label>
              )
            })}
          </fieldset>
        ) : null}
        {current.type === 'numerical' ? (
          <label htmlFor="num-answer">Numerical response (local)</label>
        ) : null}
        {current.type === 'numerical' ? (
          <input
            id="num-answer"
            inputMode="decimal"
            value={(responses[current.id] as string) ?? ''}
            onChange={(e) => setResponses((r) => ({ ...r, [current.id]: e.target.value }))}
          />
        ) : null}
        {current.type === 'descriptive' ? (
          <>
            <label htmlFor="desc-answer">Short response (local)</label>
            <textarea
              id="desc-answer"
              value={(responses[current.id] as string) ?? ''}
              onChange={(e) => setResponses((r) => ({ ...r, [current.id]: e.target.value }))}
            />
          </>
        ) : null}
      </article>
      <div className="action-row">
        <button
          type="button"
          className="btn"
          disabled={index === 0}
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
        >
          Previous
        </button>
        <button
          type="button"
          className="btn"
          disabled={index >= items.length - 1}
          onClick={() => setIndex((i) => Math.min(items.length - 1, i + 1))}
        >
          Next
        </button>
        <FailClosedAction feature="student_runner" actionLabel="Submit attempt" />
      </div>
      <p className="muted">Responses stay in memory only — no scoring, persistence, or correctness labels.</p>
    </section>
  )
}