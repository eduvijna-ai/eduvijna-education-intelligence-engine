import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const API_ORIGIN = process.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const ALLOWED_API_PATHS = new Set(['/health', '/ready', '/api/v1/system/info'])

function parsePermittedApiRequest(url: string, method: string): boolean {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return false
  }
  if (parsed.origin !== new URL(API_ORIGIN).origin) return true
  if (method !== 'GET') return false
  if (parsed.search || parsed.hash) return false
  return ALLOWED_API_PATHS.has(parsed.pathname)
}

const PRODUCT_ROUTES = [
  '/',
  '/studio',
  '/student',
  '/results',
  '/remediation',
  '/knowledge',
  '/sources',
  '/policy',
  '/auth-design',
]

test.describe('Day 18 product surfaces', () => {
  test('shell shows non-authoritative banner and navigation', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('non-authoritative-banner')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Question studio' })).toBeVisible()
  })

  test('positive integer validation on input change', async ({ page }) => {
    await page.goto('/studio')
    const count = page.getByTestId('question-count')
    await count.fill('3.5')
    await expect(page.getByRole('alert')).toContainText('whole positive')
    await count.fill('1e2')
    await expect(page.getByRole('alert')).toBeVisible()
    await count.fill('12')
    await expect(page.getByRole('alert')).toHaveCount(0)
  })

  test('blocked generation uses disabled control and explain handler', async ({ page }) => {
    await page.goto('/studio')
    await expect(page.getByTestId('question-count')).toBeVisible({ timeout: 15_000 })
    const primary = page.getByTestId('action-blocked-question_studio').first()
    await expect(primary).toBeDisabled()
    await page.getByTestId('explain-blocked-question_studio').first().click()
    await expect(page.getByTestId('blocked-reason')).toContainText('blocked', { timeout: 5_000 })
  })

  test('curriculum cascade resets dependents', async ({ page }) => {
    await page.goto('/studio')
    await page.getByTestId('scope-framework').selectOption('ncf-demo')
    await page.getByTestId('scope-academicVersion').selectOption('acad-v2024-demo')
    await page.getByTestId('scope-grade').selectOption('grade-10')
    await page.getByTestId('scope-framework').selectOption('')
    await expect(page.getByTestId('scope-grade')).toHaveValue('')
  })

  test('student bundle route has no answer metadata in built assets', async ({ page }) => {
    const assetsDir = path.join(process.cwd(), 'dist', 'assets')
    test.skip(!fs.existsSync(assetsDir), 'production build required — run npm run build first')
    const files = fs.readdirSync(assetsDir).filter((f) => f.endsWith('.js'))
    expect(files.length).toBeGreaterThan(0)
    const forbidden = ['correctAnswer', 'answerKey', 'isCorrect']
    for (const file of files) {
      const text = fs.readFileSync(path.join(assetsDir, file), 'utf8')
      for (const needle of forbidden) {
        expect(text).not.toContain(needle)
      }
    }
    await page.goto('/student')
    await expect(page.getByTestId('answer-metadata-status')).toHaveCount(0)
    await page.goto('/studio')
    await page.getByLabel('Fixture item').selectOption('t-q-stem-table-01')
    await expect(page.locator('.stem-table')).toBeVisible()
  })

  test('student runner exercises all four response formats', async ({ page }) => {
    await page.goto('/student')
    await expect(page.getByTestId('student-question')).toBeVisible()
    await page.getByRole('radio', { name: 'Displacement' }).check()
    await page.getByRole('button', { name: 'Next' }).click()
    await page.getByRole('checkbox', { name: 'Length' }).check()
    await page.getByRole('button', { name: 'Next' }).click()
    await page.locator('#num-answer').fill('9.8')
    await page.getByRole('button', { name: 'Next' }).click()
    await page.locator('#desc-answer').fill('When motion stays along one line without reversal.')
    await page.getByTestId('explain-blocked-student_runner').click()
    await expect(page.getByTestId('blocked-reason')).toContainText('blocked')
  })

  test('URL and storage tampering does not elevate capabilities', async ({ page }) => {
    await page.goto('/')
    const baseline = await page.evaluate(() => ({
      ls: [...Object.keys(localStorage)].sort(),
      ss: [...Object.keys(sessionStorage)].sort(),
    }))
    await page.addInitScript(() => {
      localStorage.setItem('eduvijna_privilege', 'admin')
      sessionStorage.setItem('mock', '1')
    })
    await page.goto('/?mock=1&role=admin&privilege=1')
    await expect(page.getByTestId('capability-diagnostic_only').first()).toBeVisible()
    await expect(page.getByTestId('capability-connection_only')).toBeVisible()
    const after = await page.evaluate(() => ({
      ls: [...Object.keys(localStorage)].sort(),
      ss: [...Object.keys(sessionStorage)].sort(),
    }))
    const newLs = after.ls.filter((k) => !baseline.ls.includes(k))
    const newSs = after.ss.filter((k) => !baseline.ss.includes(k))
    expect(newLs).toEqual(['eduvijna_privilege'])
    expect(newSs).toEqual(['mock'])
  })

  test('network requests stay on allowlisted health routes across routes', async ({ page }) => {
    for (const route of PRODUCT_ROUTES) {
      const observed: { url: string; method: string }[] = []
      const handler = (req: { url: () => string; method: () => string }) => {
        observed.push({ url: req.url(), method: req.method() })
      }
      page.on('request', handler)
      await page.goto(route)
      await page.waitForTimeout(300)
      page.off('request', handler)
      for (const { url, method } of observed) {
        if (url.includes('/@vite') || url.includes('/src/') || url.includes('/node_modules')) continue
        if (url.endsWith('.css') || url.endsWith('.js') || url.includes('/assets/')) continue
        expect(parsePermittedApiRequest(url, method)).toBeTruthy()
      }
    }
  })

  test('export downloads watermarked JSON with stems', async ({ page }) => {
    await page.goto('/studio')
    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('json-export').click()
    const download = await downloadPromise
    const content = fs.readFileSync(await download.path(), 'utf8')
    const parsed = JSON.parse(content) as {
      deliveredActual: number
      illustrativeSampleMarksTotal: number
      plannedTotalMarksStatus: string
    }
    expect(content).toContain('SYNTHETIC DEMO')
    expect(parsed.deliveredActual).toBe(0)
    expect(parsed.illustrativeSampleMarksTotal).toBe(9)
    expect(parsed.plannedTotalMarksStatus).toBe('unknown_synthetic')
    expect(content).not.toContain('correctAnswer')
  })

  test('export downloads printable HTML without window.open', async ({ page }) => {
    await page.goto('/studio')
    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('print-export').click()
    const download = await downloadPromise
    const content = fs.readFileSync(await download.path(), 'utf8')
    expect(content).toContain('SYNTHETIC DEMO')
    expect(content).toContain('<!DOCTYPE html>')
    expect(content).toContain('Illustrative sample marks total: 9')
  })

  test('keyboard tab reaches first nav link', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      const active = document.activeElement
      if (active && active instanceof HTMLElement) active.blur()
    })
    await page.keyboard.press('Tab')
    const focused = await page.evaluate(() => {
      const el = document.activeElement
      if (!el || !(el instanceof HTMLElement)) return null
      return { tag: el.tagName, text: el.textContent?.trim() ?? '' }
    })
    expect(focused?.tag).toBe('A')
    expect(focused?.text).toContain('Foundation')
  })

  test('responsive layout avoids horizontal overflow', async ({ page }) => {
    for (const width of [390, 768, 1280]) {
      await page.setViewportSize({ width, height: 800 })
      await page.goto('/')
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 2,
      )
      expect(overflow).toBeTruthy()
      await expect(page.getByRole('link', { name: 'Question studio' })).toBeVisible()
    }
  })

  test('admin routes show blocked actions', async ({ page }) => {
    await page.goto('/sources')
    await expect(page.getByTestId('action-blocked-source_admin').first()).toBeDisabled()
    await page.getByTestId('explain-blocked-source_admin').first().click()
    await expect(page.getByTestId('blocked-reason')).toContainText('blocked')
    await page.goto('/policy')
    await expect(page.getByTestId('capability-unavailable')).toBeVisible()
  })

  test('unknown route fallback', async ({ page }) => {
    await page.goto('/definitely-not-a-route')
    await expect(page.getByTestId('unknown-route')).toBeVisible()
  })
})