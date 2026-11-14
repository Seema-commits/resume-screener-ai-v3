// The same limits the API enforces (backend/routers/scans.py) - checked
// here first so users get an instant message; the API still decides.

export const MAX_RESUMES = 20
export const MAX_FILE_BYTES = 5 * 1024 * 1024
export const RESUME_TYPES = ['.pdf', '.docx']

/** Adds new files (skipping exact duplicates); returns any problems. */
export function addFiles(current: File[], incoming: File[]): { files: File[]; errors: string[] } {
  const errors: string[] = []
  const files = [...current]
  const key = (f: File) => `${f.name}:${f.size}`
  const seen = new Set(files.map(key))

  for (const file of incoming) {
    const name = file.name.toLowerCase()
    if (!RESUME_TYPES.some(type => name.endsWith(type))) {
      errors.push(`${file.name}: only PDF and DOCX files are accepted.`)
    } else if (file.size > MAX_FILE_BYTES) {
      errors.push(`${file.name} is larger than 5 MB.`)
    } else if (files.length >= MAX_RESUMES) {
      errors.push(`You can screen up to ${MAX_RESUMES} resumes at once.`)
      break
    } else if (!seen.has(key(file))) {
      seen.add(key(file))
      files.push(file)
    }
  }
  return { files, errors }
}
