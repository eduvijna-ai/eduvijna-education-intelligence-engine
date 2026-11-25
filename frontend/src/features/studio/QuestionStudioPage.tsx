import { useMemo, useState } from 'react'

import { resolveCapabilities } from '../../capability/readiness'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { FailClosedAction } from '../../components/FailClosedAction'
import { StemRenderer } from '../../components/StemRenderer'
import {
  CURRICULUM_FIXTURE,
  flattenSelectablePaths,
} from '../../fixtures/curriculum'
import {
  EXAM_PACK_FIXTURES,
  SYNTHETIC_PAPER_PREVIEW,
  TWO_PAPER_CONTRACT,
} from '../../fixtures/exams'
import { STATIC_JOB_FIXTURES } from '../../fixtures/jobs'
import { TEACHER_QUESTION_FIXTURES } from '../../fixtures/questions-teacher'
import { buildJsonExport, buildPrintableHtml } from '../../lib/exportPrint'
import { validatePositiveIntegerInput } from '../../lib/positiveInteger'

export function QuestionStudioPage() {
  const studio = resolveCapabilities().question_studio
  const paths = useMemo(() => flattenSelectablePaths(CURRICULUM_FIXTURE), [])
  const [scopePath, setScopePath] = useState(paths[0]?.label ?? '')
  const [countRaw, setCountRaw] = useState('10')
  const [countError, setCountError] = useState<string | null>(null)
  const [qType, setQType] = useState('mcq')
  const [difficulty, setDifficulty] = useState('foundation')
  const [bloom, setBloom] = useState('Understand')
  const [competency, setCompetency] = useState('synthetic-competency')
  const [examPack, setExamPack] = useState(EXAM_PACK_FIXTURES[0]?.packId ?? '')
  const [paperMode, setPaperMode] = useState<'single' | 'two_paper'>('single')
  const [blockReason, setBlockReason] = useState<string | null>(null)
  const [previewId, setPreviewId] = useState(TEACHER_QUESTION_FIXTURES[0]?.id ?? '')

  const preview = TEACHER_QUESTION_FIXTURES.find((q) => q.id === previewId) ?? TEACHER_QUESTION_FIXTURES[0]

  const onCountBlur = () => {
    const result = validatePositiveIntegerInput(countRaw)
    setCountError(result.valid ? null : result.message)
  }

  const onExportJson = () => {
    const json = buildJsonExport(SYNTHETIC_PAPER_PREVIEW)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'synthetic-paper-demo.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  const onPrintPreview = () => {
    const html = buildPrintableHtml(SYNTHETIC_PAPER_PREVIEW)
    const w = window.open('', '_blank', 'noopener,noreferrer')
    if (w) {
      w.document.write(html)
      w.document.close()
    }
  }

  return (
    <section className="panel studio">
      <header className="page-header">
        <h2>Question &amp; assessment studio</h2>
        <CapabilityBadge state={studio.readiness} />
      </header>
      <p className="muted">Teacher-oriented workspace — synthetic fixtures; generation and repair disabled.</p>

      <div className="studio-grid">
        <fieldset>
          <legend>Curriculum scope (synthetic)</legend>
          <label htmlFor="scope-select">Hierarchy</label>
          <select
            id="scope-select"
            value={scopePath}
            onChange={(e) => setScopePath(e.target.value)}
            data-testid="curriculum-select"
          >
            {paths.map((p) => (
              <option key={p.label} value={p.label}>
                {p.label}
              </option>
            ))}
          </select>
        </fieldset>

        <fieldset>
          <legend>Exact count validation</legend>
          <label htmlFor="question-count">Question count</label>
          <input
            id="question-count"
            inputMode="numeric"
            value={countRaw}
            onChange={(e) => setCountRaw(e.target.value)}
            onBlur={onCountBlur}
            aria-invalid={countError ? true : undefined}
            aria-describedby={countError ? 'count-error' : undefined}
            data-testid="question-count"
          />
          {countError ? (
            <p id="count-error" className="error-copy" role="alert">
              {countError}
            </p>
          ) : null}
        </fieldset>

        <fieldset>
          <legend>Controls</legend>
          <label htmlFor="q-type">Question type</label>
          <select id="q-type" value={qType} onChange={(e) => setQType(e.target.value)}>
            <option value="mcq">MCQ</option>
            <option value="numerical">Numerical</option>
            <option value="descriptive">Descriptive</option>
          </select>
          <label htmlFor="difficulty">Difficulty</label>
          <select id="difficulty" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            <option value="foundation">Foundation</option>
            <option value="moderate">Moderate</option>
            <option value="stretch">Stretch</option>
          </select>
          <label htmlFor="bloom">Bloom level</label>
          <select id="bloom" value={bloom} onChange={(e) => setBloom(e.target.value)}>
            {['Remember', 'Understand', 'Apply', 'Analyze'].map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
          <label htmlFor="competency">Competency (synthetic code)</label>
          <input id="competency" value={competency} onChange={(e) => setCompetency(e.target.value)} />
        </fieldset>

        <fieldset>
          <legend>Exam pack (not official)</legend>
          <label htmlFor="exam-pack">Pack</label>
          <select id="exam-pack" value={examPack} onChange={(e) => setExamPack(e.target.value)}>
            {EXAM_PACK_FIXTURES.map((p) => (
              <option key={p.packId} value={p.packId}>
                {p.label}
              </option>
            ))}
          </select>
          <label htmlFor="paper-mode">Paper configuration</label>
          <select
            id="paper-mode"
            value={paperMode}
            onChange={(e) => setPaperMode(e.target.value as 'single' | 'two_paper')}
          >
            <option value="single">Single paper</option>
            <option value="two_paper">Two-paper contract</option>
          </select>
          {paperMode === 'two_paper' ? (
            <p className="muted">
              {TWO_PAPER_CONTRACT.paperOneLabel} / {TWO_PAPER_CONTRACT.paperTwoLabel} — issuance{' '}
              {TWO_PAPER_CONTRACT.issuance}
            </p>
          ) : null}
        </fieldset>
      </div>

      <p className="action-row">
        <FailClosedAction
          feature="question_studio"
          actionLabel="Generate questions"
          onBlockedAttempt={setBlockReason}
        />
        <FailClosedAction feature="generation_jobs" actionLabel="Create async job" onBlockedAttempt={setBlockReason} />
      </p>
      {blockReason ? <p className="error-copy" role="status">{blockReason}</p> : null}

      <section aria-labelledby="teacher-preview">
        <h3 id="teacher-preview">Teacher preview (includes answer metadata)</h3>
        <label htmlFor="preview-select">Fixture item</label>
        <select id="preview-select" value={previewId} onChange={(e) => setPreviewId(e.target.value)}>
          {TEACHER_QUESTION_FIXTURES.map((q) => (
            <option key={q.id} value={q.id}>
              {q.id}
            </option>
          ))}
        </select>
        {preview ? (
          <article className="question-card" data-testid="teacher-preview-card">
            <StemRenderer source={preview.stem} className="stem" />
            {preview.options ? (
              <ul>
                {preview.options.map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            ) : null}
            <dl className="meta-dl">
              <div>
                <dt>Correct answer (teacher only)</dt>
                <dd>{preview.correctAnswer}</dd>
              </div>
              <div>
                <dt>Explanation</dt>
                <dd>{preview.explanation}</dd>
              </div>
              <div>
                <dt>Evidence</dt>
                <dd>{preview.evidenceStatus}</dd>
              </div>
            </dl>
          </article>
        ) : null}
      </section>

      <section aria-labelledby="provenance-panel">
        <h3 id="provenance-panel">Provenance</h3>
        <p>Source: {preview?.provenance ?? '—'} · Trust: synthetic_fixture · Activation: blocked</p>
      </section>

      <section aria-labelledby="validation-panel">
        <h3 id="validation-panel">Validation &amp; repair (contract)</h3>
        <p>Verdict: NOT_RUN — no backend validation. Repair actions fail closed.</p>
        <FailClosedAction feature="question_studio" actionLabel="Run repair" onBlockedAttempt={setBlockReason} />
      </section>

      <section aria-labelledby="job-panel">
        <h3 id="job-panel">Async job states (static)</h3>
        <ul>
          {STATIC_JOB_FIXTURES.map((j) => (
            <li key={j.jobId}>
              {j.label} — <code>{j.state}</code>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="paper-panel">
        <h3 id="paper-panel">Paper preview</h3>
        <p>
          Planned total: {SYNTHETIC_PAPER_PREVIEW.plannedTotal} · Delivered (demo):{' '}
          {SYNTHETIC_PAPER_PREVIEW.deliveredTotal}
        </p>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Section</th>
              <th scope="col">Planned</th>
              <th scope="col">Delivered</th>
            </tr>
          </thead>
          <tbody>
            {SYNTHETIC_PAPER_PREVIEW.sections.map((s) => (
              <tr key={s.title}>
                <td>{s.title}</td>
                <td>{s.plannedCount}</td>
                <td>{s.deliveredCount}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="action-row">
          <button type="button" className="btn" onClick={onPrintPreview} data-testid="print-export">
            Open printable HTML
          </button>
          <button type="button" className="btn" onClick={onExportJson} data-testid="json-export">
            Export JSON (watermarked)
          </button>
        </p>
      </section>

      <section aria-labelledby="stem-table">
        <h3 id="stem-table">STEM table &amp; diagram (fixture)</h3>
        <table className="data-table">
          <caption className="sr-only">Sample kinematics values</caption>
          <thead>
            <tr>
              <th scope="col">t (s)</th>
              <th scope="col">s (m)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>0</td>
              <td>0</td>
            </tr>
            <tr>
              <td>2</td>
              <td>8</td>
            </tr>
          </tbody>
        </table>
        <figure className="diagram-fixture" aria-label="Velocity-time sketch (static SVG fixture)">
          <svg viewBox="0 0 120 60" width="200" height="100" role="img">
            <title>Demo velocity-time line</title>
            <line x1="10" y1="50" x2="110" y2="50" stroke="#526071" />
            <line x1="10" y1="50" x2="10" y2="10" stroke="#526071" />
            <line x1="10" y1="30" x2="90" y2="20" stroke="#157347" strokeWidth="2" />
          </svg>
        </figure>
      </section>
    </section>
  )
}