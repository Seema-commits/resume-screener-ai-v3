// Fails the build if anyone adds a way for resume/LLM text to run as
// HTML or code. All text must go through React's escaping.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const BANNED = [/dangerouslySetInnerHTML/, /\.innerHTML\b/, /\.outerHTML\b/, /\beval\s*\(/,
                /new Function\s*\(/, /document\.write/, /localStorage/, /sessionStorage/]

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return name === 'test' ? [] : sourceFiles(path)
    return /\.(ts|tsx)$/.test(name) ? [path] : []
  })
}

test.each(sourceFiles(join(import.meta.dirname, '..')))('%s has no unsafe HTML, eval or browser storage', path => {
  const text = readFileSync(path, 'utf8')
  for (const pattern of BANNED) expect(text).not.toMatch(pattern)
})
