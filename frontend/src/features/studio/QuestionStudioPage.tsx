import { useMemo, useState, type ReactNode } from 'react'

import { resolveCapabilities } from '../../capability/readiness'
import { CapabilityBadge } from '../../components/CapabilityBadge'
import { FailClosedAction } from '../../components/FailClosedAction'
import { SafeStemTable } from '../../components/SafeStemTable'
import { StemRenderer } from '../../components/StemRenderer'
import {
  EMPTY_SCOPE,
  isScopeValid,
  optionsForLevel,
  resetDependents,
  SCOPE_LEVEL_ORDER,
  type CurriculumSelections,
  type ScopeLevel,
} from '../../fixtures/curriculumScope'
import {
  countContractForPack,
  EXAM_PACK_FIXTURES,
  EXAM_SECTIONS,
  EXAM_SUBJECTS,
  EXAM_VERSIONS,
  examSectionKey,
  examSubjectKey,
  SYNTHETIC_PAPER_PREVIEW,
  TWO_PAPER_CONTRACT,
  paperModeForPack,
} from '../../fixtures/exams'
import { STATIC_JOB_FIXTURES } from '../../fixtures/jobs'
import {
  ARIV_COMPETENCY_LABELS,
  BLOOM_LEVELS,
  TEACHER_QUESTION_FIXTURES,
} from '../../fixtures/questions-teacher'
import { buildJsonExport, buildPrintableHtml, triggerBlobDownload } from '../../lib/exportPrint'
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

const initialPack = EXAM_PACK_FIXTURES[0].packId
const initialVersion = EXAM_VERSIONS[initialPack]?.[0]?.id ?? ''
const initialSubjectKey = initialVersion ? examSubjectKey(initialPack, initialVersion) : ''
const initialSubject = initialSubjectKey ? (EXAM_SUBJECTS[initialSubjectKey]?.[0]?.id ?? '') : ''
const initialSectionKey =
  initialSubject && initialVersion
    ? examSectionKey(initialPack, initialVersion, initialSubject)
    : ''
const initialSection = initialSectionKey ? (EXAM_SECTIONS[initialSectionKey]?.[0]?.id ?? '') : ''

export function QuestionStudioPage() {
  const studio = resolveCapabilities().question_studio
  const [scope, setScope] = useState<CurriculumSelections>({ ...EMPTY_SCOPE })
  const [countRaw, setCountRaw] = useState('')
  const [countError, setCountError] = useState<string | null>(null)
  const [qType, setQType] = useState<'mcq' | 'multiselect' | 'numerical' | 'descriptive'>('mcq')
  const [difficulty, setDifficulty] = useState('foundation')
  const [bloom, setBloom] = useState<(typeof BLOOM_LEVELS)[number]>('Understand')
  const [competency, setCompetency] = useState<(typeof ARIV_COMPETENCY_LABELS)[number]>(
    ARIV_COMPETENCY_LABELS[0],
  )
  const [examPack, setExamPack] = useState<string>(initialPack)
  const [examVersion, setExamVersion] = useState(initialVersion)
  const [examSubject, setExamSubject] = useState(initialSubject)
  const [examSection, setExamSection] = useState(initialSection)
  const [blockReason, setBlockReason] = useState<string | null>(null)
  const [previewId, setPreviewId] = useState(TEACHER_QUESTION_FIXTURES[0]?.id ?? '')
  const paper = SYNTHETIC_PAPER_PREVIEW
  const paperMode = paperModeForPack(examPack)
  const countContract = countContractForPack(examPack)

  const subjectKey = examVersion ? examSubjectKey(examPack, examVersion) : ''
  const subjects = subjectKey ? (EXAM_SUBJECTS[subjectKey] ?? []) : []
  const sectionKey =
    examSubject && examVersion ? examSectionKey(examPack, examVersion, examSubject) : ''
  const sections = sectionKey ? (EXAM_SECTIONS[sectionKey] ?? []) : []
  const versions = EXAM_VERSIONS[examPack] ?? []

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

  const scopeComplete = useMemo(() => isScopeValid(scope), [scope])

  const onExamPackChange = (packId: string) => {
    setExamPack(packId)
    const version = EXAM_VERSIONS[packId]?.[0]?.id ?? ''
    setExamVersion(version)
    const sk = version ? examSubjectKey(packId, version) : ''
    const subject = sk ? (EXAM_SUBJECTS[sk]?.[0]?.id ?? '') : ''
    setExamSubject(subject)
    const sek = subject && version ? examSectionKey(packId, version, subject) : ''
    setExamSection(sek ? (EXAM_SECTIONS[sek]?.[0]?.id ?? '') : '')
  }

  const onExamVersionChange = (versionId: string) => {
    setExamVersion(versionId)
    const sk = versionId ? examSubjectKey(examPack, versionId) : ''
    const subject = sk ? (EXAM_SUBJECTS[sk]?.[0]?.id ?? '') : ''
    setExamSubject(subject)
    const sek = subject && versionId ? examSectionKey(examPack, versionId, subject) : ''
    setExamSection(sek ? (EXAM_SECTIONS[sek]?.[0]?.id ?? '') : '')
  }

  const onExamSubjectChange = (subjectId: string) => {
    setExamSubject(subjectId)
    const sek = subjectId && examVersion ? examSectionKey(examPack, examVersion, subjectId) : ''
    setExamSection(sek ? (EXAM_SECTIONS[sek]?.[0]?.id ?? '') : '')
  }

  const onExportJson = () => {
    triggerBlobDownload(buildJsonExport(), 'synthetic-paper-demo.json', 'application/json')
  }

  const onPrintPreview = () => {
    triggerBlobDownload(buildPrintableHtml(), 'synthetic-paper-demo.html', 'text/html;charset=utf-8')
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
            Scope valid: {scopeComplete ? 'yes' : 'no'}
          </p>
        </fieldset>

        <fieldset>
          <legend>Exact count validation ({countContract.replace('_', ' ')})</legend>
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
          <label htmlFor="competency">ARIV competency (synthetic mapping)</label>
          <select
            id="competency"
            value={competency}
            onChange={(e) =>
              setCompetency(e.target.value as (typeof ARIV_COMPETENCY_LABELS)[number])
            }
          >
            {ARIV_COMPETENCY_LABELS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </fieldset>

        <fieldset data-testid="exam-selection">
          <legend>Exam pack (not official)</legend>
          <label htmlFor="exam-pack">Pack</label>
          <select id="exam-pack" value={examPack} onChange={(e) => onExamPackChange(e.target.value)}>
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
            onChange={(e) => onExamVersionChange(e.target.value)}
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
            onChange={(e) => onExamSubjectChange(e.target.value)}
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
            {preview.stemTable ? (
              <SafeStemTable
                caption={preview.stemTable.caption}
                headers={preview.stemTable.headers}
                rows={preview.stemTable.rows}
              />
            ) : null}
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
                <dd>
                  {preview.competency} ({preview.competencyMappingStatus})
                </dd>
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
        <h3 id="paper-panel">Paper preview (fixed fixture — independent of studio selections)</h3>
        <p>
          Duration: {paper.durationMinutes} min · Planned total marks: {paper.plannedTotalMarksStatus}{' '}
          · Illustrative sample marks total: {paper.illustrativeSampleMarksTotal} · Negative marking:{' '}
          {paper.negativeMarking}
        </p>
        <p>
          Planned items: {paper.plannedTotal} · Delivered actual: {paper.deliveredActual} ·
          Illustrative samples: {paper.illustrativeSampleCount}
        </p>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Section</th>
              <th scope="col">Planned</th>
              <th scope="col">Delivered actual</th>
              <th scope="col">Samples</th>
              <th scope="col">Sample marks</th>
            </tr>
          </thead>
          <tbody>
            {paper.sections.map((s) => (
              <tr key={s.title}>
                <td>{s.title}</td>
                <td>{s.plannedCount}</td>
                <td>{s.deliveredActual}</td>
                <td>{s.illustrativeSamples}</td>
                <td>{s.illustrativeSampleMarks}</td>
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