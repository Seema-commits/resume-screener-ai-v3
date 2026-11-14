import clsx from 'clsx'
import { FileText, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'

/** Drag-and-drop or click-to-pick file area. Checks happen in the caller. */
export function FileDrop({ accept, multiple = true, label, files, onAdd, onRemove }: {
  accept: string
  multiple?: boolean
  label: string
  files: File[]
  onAdd: (files: File[]) => void
  onRemove: (file: File) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  return (
    <div className="space-y-2">
      <button type="button"
        onClick={() => input.current?.click()}
        onDragOver={e => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={e => { e.preventDefault(); setOver(false); onAdd(Array.from(e.dataTransfer.files)) }}
        className={clsx('flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed p-6 text-sm',
          over ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 bg-white hover:bg-slate-50')}>
        <Upload className="size-6 text-slate-400" aria-hidden />
        <span className="font-medium text-slate-700">{label}</span>
        <span className="text-xs text-slate-500">Drop files here or click to browse</span>
      </button>
      <input ref={input} type="file" accept={accept} multiple={multiple} hidden
             onChange={e => { onAdd(Array.from(e.target.files ?? [])); e.target.value = '' }} />
      {files.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white text-sm">
          {files.map(f => (
            <li key={`${f.name}:${f.size}`} className="flex items-center gap-2 px-3 py-2">
              <FileText className="size-4 text-slate-400" aria-hidden />
              <span className="flex-1 truncate">{f.name}</span>
              <span className="text-xs text-slate-400">{Math.ceil(f.size / 1024)} KB</span>
              <button type="button" onClick={() => onRemove(f)} aria-label={`Remove ${f.name}`}
                      className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
                <X className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
