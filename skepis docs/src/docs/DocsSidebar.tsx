import React, { useState, useMemo } from 'react'
import { DOCS_SECTIONS, type DocSection, type DocItem } from './docs-navigation'
import { MagnifyingGlass, CaretDown, CaretRight } from '@phosphor-icons/react'

interface DocsSidebarProps {
  currentSlug: string
  onSelectSlug: (slug: string) => void
  onCloseMobile?: () => void
}

export const DocsSidebar: React.FC<DocsSidebarProps> = ({
  currentSlug,
  onSelectSlug,
  onCloseMobile,
}) => {
  const [searchQuery, setSearchQuery] = useState('')
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({})

  const toggleSection = (id: string) => {
    setCollapsedSections((prev) => ({
      ...prev,
      [id]: !prev[id],
    }))
  }

  // Filtered sections based on search query
  const filteredSections = useMemo(() => {
    if (!searchQuery.trim()) return DOCS_SECTIONS
    const q = searchQuery.toLowerCase()
    return DOCS_SECTIONS.map((sec) => ({
      ...sec,
      items: sec.items.filter(
        (item) =>
          item.title.toLowerCase().includes(q) ||
          item.description.toLowerCase().includes(q) ||
          item.slug.toLowerCase().includes(q)
      ),
    })).filter((sec) => sec.items.length > 0)
  }, [searchQuery])

  return (
    <aside className="w-full h-full flex flex-col font-body text-xs text-stone-700 bg-[#fbf9f5] border-r border-stone-200/90 select-none">
      {/* Search Header */}
      <div className="p-3 border-b border-stone-200/80 bg-white/50">
        <div className="relative">
          <MagnifyingGlass
            size={14}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400"
          />
          <input
            type="text"
            placeholder="Filter documentation..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 rounded-md border border-stone-300/80 bg-white text-xs text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
          />
        </div>
      </div>

      {/* Navigation Tree */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {filteredSections.map((section: DocSection) => {
          const isCollapsed = collapsedSections[section.id] && !searchQuery

          return (
            <div key={section.id} className="space-y-1">
              <button
                type="button"
                onClick={() => toggleSection(section.id)}
                className="w-full flex items-center justify-between px-2 py-1 rounded text-stone-500 hover:text-stone-900 font-mono text-[11px] font-semibold uppercase tracking-wider transition-colors"
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-emerald-700 font-bold">{section.number}</span>
                  <span>{section.title}</span>
                </div>
                {isCollapsed ? <CaretRight size={12} /> : <CaretDown size={12} />}
              </button>

              {!isCollapsed && (
                <div className="space-y-0.5 pl-2 border-l border-stone-200 ml-2">
                  {section.items.map((item: DocItem) => {
                    const isActive = currentSlug === item.slug

                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          onSelectSlug(item.slug)
                          if (onCloseMobile) onCloseMobile()
                        }}
                        className={`w-full text-left px-2.5 py-1.5 rounded-md text-xs font-body transition-all flex items-center justify-between ${
                          isActive
                            ? 'bg-emerald-800 text-white font-semibold shadow-xs'
                            : 'text-stone-700 hover:text-stone-950 hover:bg-stone-200/60'
                        }`}
                      >
                        <span className="truncate">{item.title}</span>
                        {item.badge && (
                          <span
                            className={`text-[9px] font-mono px-1.5 py-0.2 rounded font-medium ${
                              isActive
                                ? 'bg-emerald-950 text-emerald-200'
                                : 'bg-stone-200 text-stone-700'
                            }`}
                          >
                            {item.badge}
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}

        {filteredSections.length === 0 && (
          <div className="p-4 text-center text-stone-400 text-xs">
            No matching documentation found.
          </div>
        )}
      </div>

      {/* Footer Info */}
      <div className="p-3 border-t border-stone-200/80 bg-white/60 text-[11px] font-mono text-stone-500 space-y-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <img src="/skepis_logo_dark.png" alt="Skepis logo" className="w-5 h-5 object-contain" />
            <span>Skepis Docs v0.1.4</span>
          </div>
          <span className="text-emerald-800 font-semibold">Verified</span>
        </div>
        <div className="flex items-center justify-between text-[10px] text-stone-400 pt-1 border-t border-stone-200/60">
          <span>Memory Partner</span>
          <button
            type="button"
            onClick={() => onSelectSlug('concepts/state-model')}
            className="text-emerald-800 font-semibold hover:underline"
          >
            Sibyl Labs
          </button>
        </div>
      </div>
    </aside>
  )
}
