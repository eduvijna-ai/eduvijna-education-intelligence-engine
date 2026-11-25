export type PositiveIntegerValidation =
  | { valid: true; value: number }
  | { valid: false; code: string; message: string }

/** Strict positive integer validation (D18-11) — no silent defaults or clamping. */
export function validatePositiveIntegerInput(raw: string): PositiveIntegerValidation {
  const trimmed = raw.trim()
  if (trimmed === '') {
    return { valid: false, code: 'BLANK', message: 'Count is required.' }
  }
  if (/[eE]/.test(trimmed) || trimmed.includes('.')) {
    return { valid: false, code: 'NON_INTEGER', message: 'Use a whole positive number only.' }
  }
  if (trimmed.startsWith('-') || trimmed.startsWith('+')) {
    return { valid: false, code: 'SIGNED', message: 'Negative or signed values are not allowed.' }
  }
  if (!/^\d+$/.test(trimmed)) {
    return { valid: false, code: 'INVALID_CHARS', message: 'Only digits 0-9 are allowed.' }
  }
  const value = Number(trimmed)
  if (!Number.isSafeInteger(value) || value <= 0) {
    return { valid: false, code: 'NON_POSITIVE', message: 'Count must be a positive integer.' }
  }
  if (value > 500) {
    return { valid: false, code: 'OVERFLOW', message: 'Count exceeds supported demo maximum (500).' }
  }
  return { valid: true, value }
}