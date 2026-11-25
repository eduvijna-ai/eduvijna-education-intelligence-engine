import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const assetsDir = path.join(__dirname, '..', 'dist', 'assets')

const forbidden = ['correctAnswer', 'answerKey', 'isCorrect', '"explanation":']

if (!fs.existsSync(assetsDir)) {
  console.error('Bundle verify: dist/assets missing — run npm run build first')
  process.exit(2)
}

const jsFiles = fs.readdirSync(assetsDir).filter((f) => f.endsWith('.js'))
if (jsFiles.length === 0) {
  console.error('Bundle verify: dist/assets has no JavaScript chunks')
  process.exit(2)
}

const issues = []
for (const file of jsFiles) {
  const text = fs.readFileSync(path.join(assetsDir, file), 'utf8')
  for (const needle of forbidden) {
    if (text.includes(needle)) {
      issues.push(`${file}:${needle}`)
    }
  }
}

if (issues.length > 0) {
  console.error('Bundle verify failed:', issues.join(', '))
  process.exit(1)
}

console.log('Bundle verify: ok', `(${jsFiles.length} chunks)`)