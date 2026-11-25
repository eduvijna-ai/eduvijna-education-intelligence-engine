import { useEffect, useMemo, useState, type ReactNode } from 'react'

import { resolveCapabilities } from '../../capability/readiness'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { FailClosedAction } from '../../components/FailClosedAction'
import { StemRenderer } from '../../components/StemRenderer'
import {
  EMPTY_SCOPE,
  optionsForLevel,
  resetDependents,
  SCOPE_LEVEL_ORDER,
  type CurriculumSelections,
  type ScopeLevel,
} from '../../fixtures/curriculumScope'
import {
  EXAM_PACK_FIXTURES,
  EXAM_SECTIONS,
  EXAM_SUBJECTS,
  EXAM_VERSIONS,
  SYNTHETIC_PAPER_PREVIEW,
  TWO_PAPER_CONTRACT,
  paperModeForPack,
} from '../../fixtures/exams'
import { STATIC_JOB_FIXTURES } from '../../fixtures/jobs'
import {
  BLOOM_LEVELS,
  SYNTHETIC_COMPETENCY_CODES,
  TEACHER_QUESTION_FIXTURES,
} from '../../fixtures/questions-teacher'
import {
  buildJsonExport,
  buildPrintableHtml,
  triggerBlobDownload,
} from '../../lib/exportPrint'
import { validatePositiveIntegerInput } from '../../lib/positiveInteger'

const LEVEL_LABELS: Record<ScopeLevel, string> = {
  framework: 'Framework',
  academicVersion: 'Academic version',
  grade: 'Grade',
  medium: 'Medium',
  subject: 'Subject',
  unit: 'Unit',
  chapter: 'Chapter',
  topic: 'Topic',
  concept: 'Concept',
}

export function QuestionStudioPage() {
  const studio = resolveCapabilities().question_studio
  const [scope, setScope] = useState<CurriculumSelections>({ ...EMPTY_SCOPE })
  const [countRaw, setCountRaw] = useState('')
  const [countError, setCountError] = useState<string | null>(null)
  const [qType, setQType] = useState<'mcq' | 'multiselect' | 'numerical' | 'descriptive'>('mcq')
  const [difficulty, setDifficulty] = useState('foundation')
  const [bloom, setBloom] = useState<(typeof BLOOM_LEVELS)[number]>('Understand')
  const [competency, setCompetency] = useState<(typeof SYNTHETIC_COMPETENCY_CODES)[number]>(
    SYNTHETIC_COMPETENCY_CODES[0],
  )
  const [examPack, setExamPack] = useState<string>(EXAM_PACK_FIXTURES[0].packId)
  const [examVersion, setExamVersion] = useState('')
  const [examSubject, setExamSubject] = useState('')
  const [examSection, setExamSection] = useState('')
  const [blockReason, setBlockReason] = useState<string | null>(null)
  const [previewId, setPreviewId] = useState(TEACHER_QUESTION_FIXTURES[0]?.id ?? '')
  const paper = SYNTHETIC_PAPER_PREVIEW
  const paperMode = paperModeForPack(examPack)

  const versions = EXAM_VERSIONS[examPack] ?? []
  const subjects = examVersion ? (EXAM_SUBJECTS[examVersion] ?? []) : []
  const sections = examSubject ? (EXAM_SECTIONS[examSubject] ?? []) : []

  useEffect(() => {
    const firstVersion = versions[0]?.id ?? ''
    setExamVersion(firstVersion)
    setExamSubject('')
    setExamSection('')
  }, [examPack, versions])

  useEffect(() => {
    const firstSubject = subjects[0]?.id ?? ''
    setExamSubject(firstSubject)
    setExamSection('')
  }, [examVersion, subjects])

  useEffect(() => {
    setExamSection(sections[0]?.id ?? '')
  }, [examSubject, sections])

  const preview = TEACHER_QUESTION_FIXTURES.find((q) => q.id === previewId) ?? TEACHER_QUESTION_FIXTURES[0]

  const validateCount = (raw: string) => {
    const result = validatePositiveIntegerInput(raw)
    setCountError(result.valid ? null : result.message)
    return result
  }

  const onCountChange = (raw: string) => {
    setCountRaw(raw)
    validateCount(raw)
  }

  const onScopeChange = (level: ScopeLevel, value: string) => {
    setScope((prev) => resetDependents({ ...prev, [level]: value }, level))
  }

  const scopeComplete = useMemo(
    () => SCOPE_LEVEL_ORDER.every((level) => scope[level] !== ''),
    [scope],
  )

  const onExportJson = () => {
    const json = buildJsonExport(paper)
    triggerBlobDownload(json, 'synthetic-paper-demo.json', 'application/json')
  }

  const onPrintPreview = () => {
    const html = buildPrintableHtml(paper)
    triggerBlobDownload(html, 'synthetic-paper-demo.html', 'text/html;charset=utf-8')
  }

  return (
    <section className="panel studio">
      <header className="page-header">
        <h2>Question &amp; assessment studio</h2>
        <CapabilityBadge state={studio.readiness} />
      </header>
      <p className="muted">
        Teacher-oriented configuration preview — synthetic fixtures; generation and repair disabled.
      </p>

      <div className="studio-grid">
        <fieldset data-testid="curriculum-cascade">
          <legend>Curriculum scope (cascading, synthetic)</legend>
          {SCOPE_LEVEL_ORDER.map((level) => {
            const options = optionsForLevel(level, scope)
            return (
              <ScopeRow key={level}>
                <label htmlFor={`scope-${level}`}>{LEVEL_LABELS[level]}</label>
                <select
                  id={`scope-${level}`}
                  value={scope[level]}
                  disabled={options.length === 0}
                  onChange={(e) => onScopeChange(level, e.target.value)}
                  data-testid={`scope-${level}`}
                >
                  <option value="">Select…</option>
                  {options.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </ScopeRow>
            )
          })}
          <p className="muted" data-testid="scope-complete">
            Scope complete: {scopeComplete ? 'yes' : 'no'}
          </p>
        </fieldset>

        <fieldset>
          <legend>Exact count validation</legend>
          <label htmlFor="question-count">Question count</label>
          <input
            id="question-count"
            inputMode="numeric"
            value={countRaw}
            onChange={(e) => onCountChange(e.target.value)}
            aria-invalid={countError ? true : undefined}
            aria-describedby={countError ? 'count-error' : undefined}
            data-testid="question-count"
            placeholder="Required positive integer"
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
          <select
            id="q-type"
            value={qType}
            onChange={(e) => setQType(e.target.value as typeof qType)}
          >
            <option value="mcq">MCQ</option>
            <option value="multiselect">Multiple select</option>
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
          <select
            id="bloom"
            value={bloom}
            onChange={(e) => setBloom(e.target.value as (typeof BLOOM_LEVELS)[number])}
          >
            {BLOOM_LEVELS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
          <label htmlFor="competency">Competency (synthetic code)</label>
          <select
            id="competency"
            value={competency}
            onChange={(e) =>
              setCompetency(e.target.value as (typeof SYNTHETIC_COMPETENCY_CODES)[number])
            }
          >
            {SYNTHETIC_COMPETENCY_CODES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </fieldset>

        <fieldset data-testid="exam-selection">
          <legend>Exam pack (not official)</legend>
          <label htmlFor="exam-pack">Pack</label>
          <select
            id="exam-pack"
            value={examPack}
            onChange={(e) => setExamPack(e.target.value)}
          >
            {EXAM_PACK_FIXTURES.map((p) => (
              <option key={p.packId} value={p.packId}>
                {p.label}
              </option>
            ))}
          </select>
          <label htmlFor="exam-version">Version</label>
          <select
            id="exam-version"
            value={examVersion}
            onChange={(e) => setExamVersion(e.target.value)}
          >
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
          <label htmlFor="exam-subject">Subject</label>
          <select
            id="exam-subject"
            value={examSubject}
            onChange={(e) => setExamSubject(e.target.value)}
          >
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <label htmlFor="exam-section">Section</label>
          <select
            id="exam-section"
            value={examSection}
            onChange={(e) => setExamSection(e.target.value)}
          >
            {sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <p className="muted">
            Paper mode: {paperMode === 'two_paper' ? 'Two-paper contract' : 'Single paper'} (not
            issuance)
          </p>
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
      {blockReason ? (
        <p className="error-copy" role="status" data-testid="blocked-reason">
          {blockReason}
        </p>
      ) : null}

      <section aria-labelledby="teacher-preview">
        <h3 id="teacher-preview">Teacher preview (metadata only — no answer keys in bundle)</h3>
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
                <dt>Difficulty</dt>
                <dd>{preview.difficulty}</dd>
              </div>
              <div>
                <dt>Bloom</dt>
                <dd>{preview.bloom}</dd>
              </div>
              <div>
                <dt>Competency</dt>
                <dd>{preview.competency}</dd>
              </div>
              <div>
                <dt>Learning outcome</dt>
                <dd>{preview.learningOutcome}</dd>
              </div>
              <div>
                <dt>Prerequisite</dt>
                <dd>{preview.prerequisite}</dd>
              </div>
              <div>
                <dt>Rubric</dt>
                <dd>{preview.rubric}</dd>
              </div>
              <div>
                <dt>Answer metadata</dt>
                <dd data-testid="answer-metadata-status">{preview.answerMetadataStatus}</dd>
              </div>
              <div>
                <dt>Provenance revision</dt>
                <dd>{preview.provenanceRevision}</dd>
              </div>
              <div>
                <dt>Provenance locator</dt>
                <dd>{preview.provenanceLocator}</dd>
              </div>
              <div>
                <dt>Evidence</dt>
                <dd>{preview.evidenceStatus}</dd>
              </div>
            </dl>
          </article>
        ) : null}
      </section>

      <section aria-labelledby="validation-panel">
        <h3 id="validation-panel">Validation &amp; repair (contract)</h3>
        <p>Verdict: NOT_RUN — no backend validation. Repair actions fail closed.</p>
        <FailClosedAction feature="question_studio" actionLabel="Run repair" onBlockedAttempt={setBlockReason} />
      </section>

      <section aria-labelledby="job-panel">
        <h3 id="job-panel">Async job states (static examples — not live)</h3>
        <ul>
          {STATIC_JOB_FIXTURES.map((j) => (
            <li key={j.jobId}>
              {j.label} — <code>{j.state}</code> (example)
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="paper-panel">
        <h3 id="paper-panel">Paper preview (configuration vs delivery)</h3>
        <p>
          Duration: {paper.durationMinutes} min · Total marks (planned): {paper.totalMarks} ·
          Negative marking: {paper.negativeMarking}
        </p>
        <p>
          Planned total: {paper.plannedTotal} · Delivered actual: {paper.deliveredActual} ·
          Illustrative samples: {paper.illustrativeSampleCount}
        </p>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Section</th>
              <th scope="col">Planned</th>
              <th scope="col">Delivered actual</th>
              <th scope="col">Samples</th>
              <th scope="col">Marks</th>
            </tr>
          </thead>
          <tbody>
            {paper.sections.map((s) => (
              <tr key={s.title}>
                <td>{s.title}</td>
                <td>{s.plannedCount}</td>
                <td>{s.deliveredActual}</td>
                <td>{s.illustrativeSamples}</td>
                <td>{s.sectionMarks}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="action-row">
          <button type="button" className="btn" onClick={onPrintPreview} data-testid="print-export">
            Download printable HTML
          </button>
          <button type="button" className="btn" onClick={onExportJson} data-testid="json-export">
            Export JSON (watermarked)
          </button>
        </p>
      </section>
    </section>
  )
}

function ScopeRow({ children }: { children: ReactNode }) {
  return <div className="scope-row">{children}</div>
}