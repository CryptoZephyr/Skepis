import React, { useState } from 'react'
import { Check, Copy } from '@phosphor-icons/react'

interface CodeBlockProps {
  code: string
  language?: string
  filename?: string
}

export const CodeBlock: React.FC<CodeBlockProps> = ({
  code,
  language = 'bash',
  filename,
}) => {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code.trim())
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }

  return (
    <div className="my-5 rounded-lg border border-stone-200/90 bg-[#1e232a] text-stone-200 shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-stone-800 bg-[#181c22] text-xs font-mono">
        <div className="flex items-center gap-2 text-stone-400">
          {filename ? (
            <span className="text-stone-300 font-semibold">{filename}</span>
          ) : (
            <span className="uppercase text-[11px] tracking-wider text-stone-400">{language}</span>
          )}
        </div>
        <button
          onClick={handleCopy}
          type="button"
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-mono text-stone-400 hover:text-stone-100 hover:bg-stone-800/80 transition-colors"
          aria-label="Copy code to clipboard"
        >
          {copied ? (
            <>
              <Check size={13} weight="bold" className="text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy size={13} weight="bold" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        <pre className="font-mono text-xs leading-relaxed text-stone-200 whitespace-pre">
          <code>{code.trim()}</code>
        </pre>
      </div>
    </div>
  )
}
