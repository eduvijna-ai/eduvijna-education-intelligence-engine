import { test, expect } from '@playwright/test'

test.describe('Day 18 product surfaces', () => {
  test('shell shows non-authoritative banner and navigation', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('non-authoritative-banner')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Question studio' })).toBeVisible()
  })

  test('positive integer validation rejects invalid counts', async ({ page }) => {
    await page.goto('/studio')
    const count = page.getByTestId('question-count')
    await count.fill('3.5')
    await count.blur()
    await expect(page.getByRole('alert')).toContainText('whole positive')
    await count.fill('1e2')
    await count.blur()
    await expect(page.getByRole('alert')).toBeVisible()
    await count.fill('10')
    await count.blur()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })

  test('blocked generation actions stay disabled', async ({ page }) => {
    await page.goto('/studio')
    const gen = page.getByTestId('action-blocked-question_studio').first()
    await expect(gen).toBeDisabled()
    await expect(gen).toHaveAttribute('aria-disabled', 'true')
  })

  test('student runner fixture has no answer keys in DOM', async ({ page }) => {
    await page.goto('/student')
    const text = await page.locator('main').innerText()
    expect(text.toLowerCase()).not.toContain('correct answer')
    expect(text.toLowerCase()).not.toMatch(/option [a-d]:.*correct/)
  })

  test('URL mock flag does not change capability badges on home', async ({ page }) => {
    await page.goto('/?mock=1&role=admin&privilege=1')
    await expect(page.getByTestId('capability-diagnostic_only').first()).toBeVisible()
    await expect(page.getByTestId('capability-connection_only')).toBeVisible()
  })

  test('keyboard navigation reaches primary nav link', async ({ page }) => {
    await page.goto('/')
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    const studio = page.getByRole('link', { name: 'Question studio' })
    await studio.focus()
    await expect(studio).toBeFocused()
  })
})