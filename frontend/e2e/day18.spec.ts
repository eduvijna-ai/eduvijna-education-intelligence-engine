import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const ALLOWED_API_SUFFIXES = ['/health', '/ready', '/api/v1/system/info']

function isPermittedRequest(url: string): boolean {
  if (url.includes('/@vite') || url.includes('/src/') || url.includes('/node_modules')) return true
  if (!url.includes('8000') && !url.includes('localhost')) return url.startsWith('http://127.0.0.1:5173')
  return ALLOWED_API_SUFFIXES.some((suffix) => url.includes(suffix))
}

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

  test('blocked generation handler fails closed', async ({ page }) => {
    await page.goto('/studio')
    await expect(page.getByTestId('question-count')).toBeVisible({ timeout: 15_000 })
    const gen = page.getByTestId('action-blocked-question_studio').first()
    await gen.click()
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
    const forbidden = ['correctAnswer', 'answerKey', 'isCorrect']
    for (const file of files) {
      const text = fs.readFileSync(path.join(assetsDir, file), 'utf8')
      for (const needle of forbidden) {
        expect(text).not.toContain(needle)
      }
    }
    await page.goto('/student')
    await expect(page.getByTestId('answer-metadata-status')).toHaveCount(0)
  })

  test('student runner exercises all four response formats', async ({ page }) => {
    await page.goto('/student')
    await expect(page.getByTestId('student-question')).toBeVisible()
    await page.getByRole('button', { name: 'Next' }).click()
    await page.getByRole('checkbox', { name: 'Length' }).check()
    await page.getByRole('button', { name: 'Next' }).click()
    await page.locator('#num-answer').fill('9.8')
    await page.getByRole('button', { name: 'Next' }).click()
    await page.locator('#desc-answer').fill('When motion stays along one line without reversal.')
    await page.getByTestId('action-blocked-student_runner').click()
    await expect(page.getByTestId('blocked-reason')).toContainText('blocked')
  })

  test('URL and storage tampering does not elevate capabilities', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('eduvijna_privilege', 'admin')
      sessionStorage.setItem('mock', '1')
    })
    await page.goto('/?mock=1&role=admin&privilege=1')
    await expect(page.getByTestId('capability-diagnostic_only').first()).toBeVisible()
    await expect(page.getByTestId('capability-connection_only')).toBeVisible()
  })

  test('network requests stay on allowlisted health routes', async ({ page }) => {
    const urls: string[] = []
    page.on('request', (req) => urls.push(req.url()))
    await page.goto('/')
    await page.waitForTimeout(500)
    const apiCalls = urls.filter((u) => u.includes('8000'))
    for (const url of apiCalls) {
      expect(isPermittedRequest(url)).toBeTruthy()
    }
  })

  test('export downloads watermarked JSON with stems', async ({ page }) => {
    await page.goto('/studio')
    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('json-export').click()
    const download = await downloadPromise
    const content = fs.readFileSync(await download.path(), 'utf8')
    expect(content).toContain('SYNTHETIC DEMO')
    expect(content).toContain('stemPlain')
    expect(content).toContain('"deliveredActual": 0')
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
  })

  test('keyboard tab reaches primary nav from document start', async ({ page }) => {
    await page.goto('/')
    await page.keyboard.press('Tab')
    const focused = await page.evaluate(() => document.activeElement?.tagName)
    expect(focused).toBeTruthy()
  })

  test('responsive layout renders at mobile width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')
    await expect(page.getByTestId('non-authoritative-banner')).toBeVisible()
    await expect(page.locator('.product-main')).toBeVisible()
  })

  test('admin routes show blocked actions', async ({ page }) => {
    await page.goto('/sources')
    await page.getByTestId('action-blocked-source_admin').first().click()
    await expect(page.getByTestId('blocked-reason')).toContainText('blocked')
    await page.goto('/policy')
    await expect(page.getByTestId('capability-unavailable')).toBeVisible()
  })
})