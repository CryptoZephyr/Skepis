import React, { useState, useEffect } from 'react'
import { MagnifyingGlass, X, ArrowRight } from '@phosphor-icons/react'
import { DOCS_SECTIONS, type DocItem } from './docs-navigation'

interface DocsSearchModalProps {
  isOpen: boolean
  onClose: () => void
  onSelectSlug: (slug: string) => void
}

// Flatten items with section title
const ALL_ITEMS: (DocItem & { sectionTitle: string })[] = DOCS_SECTIONS.flatMap((sec) =>
  sec.items.map((item) => ({ ...item, sectionTitle: sec.title }))
)

export const DocsSearchModal: React.FC<DocsSearchModalProps> = ({
  isOpen,
  onClose,
  onSelectSlug,
}) => {
  const [query, setQuery] = useState('')

  const results = query.trim()
    ? ALL_ITEMS.filter(
        (item) =>
          item.title.toLowerCase().includes(query.toLowerCase()) ||
          item.description.toLowerCase().includes(query.toLowerCase()) ||
          item.slug.toLowerCase().includes(query.toLowerCase())
      )
    : ALL_ITEMS.slice(0, 8)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        if (isOpen) onClose()
        else onSelectSlug(ALL_ITEMS[0].slug)
      }
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, onSelectSlug])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-stone-900/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="relative w-full max-w-lg bg-white rounded-xl border border-stone-300 shadow-2xl overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-stone-200">
          <MagnifyingGlass size={18} className="text-stone-400" />
          <input
            type="text"
            placeholder="Search Skepis documentation (e.g. eval, Sibyl, MCP)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            className="w-full text-xs font-body text-stone-900 placeholder:text-stone-400 focus:outline-none bg-transparent"
          />
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-stone-400 hover:text-stone-700 hover:bg-stone-100"
          >
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-2 space-y-1">
          {results.map((item) => (
            <button
              key={item.slug}
              type="button"
              onClick={() => {
                onSelectSlug(item.slug)
                onClose()
              }}
              className="w-full text-left p-2.5 rounded-lg hover:bg-[#f4f1eb] text-xs font-body transition-colors flex items-start justify-between group"
            >
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-stone-900 group-hover:text-emerald-800 transition-colors">
                    {item.title}
                  </span>
                  <span className="text-[10px] font-mono text-stone-400 uppercase">
                    {item.sectionTitle}
                  </span>
                </div>
                <p className="text-[11px] text-stone-500 line-clamp-1">
                  {item.description}
                </p>
              </div>
              <ArrowRight size={14} className="text-stone-300 group-hover:text-emerald-700 shrink-0 mt-1 transition-colors" />
            </button>
          ))}

          {results.length === 0 && (
            <div className="p-6 text-center text-xs text-stone-400">
              No results found for &ldquo;{query}&rdquo;.
            </div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-stone-100 bg-[#fbf9f5] text-[10px] font-mono text-stone-400 flex items-center justify-between">
          <span>Navigate with mouse or touch</span>
          <span>ESC to close</span>
        </div>
      </div>
    </div>
  )
}
