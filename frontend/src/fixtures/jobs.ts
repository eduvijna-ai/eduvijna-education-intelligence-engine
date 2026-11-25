import type { JobLifecycleState } from '../contracts/day17-inert'

export type StaticJobFixture = {
  jobId: string
  state: JobLifecycleState
  label: string
  operational: false
}

export const STATIC_JOB_FIXTURES: StaticJobFixture[] = [
  { jobId: 'demo-job-queued', state: 'queued', label: 'Queued (synthetic)', operational: false },
  {
    jobId: 'demo-job-generating',
    state: 'generating',
    label: 'Generating (synthetic)',
    operational: false,
  },
  {
    jobId: 'demo-job-failed',
    state: 'failed',
    label: 'Failed validation (synthetic)',
    operational: false,
  },
]