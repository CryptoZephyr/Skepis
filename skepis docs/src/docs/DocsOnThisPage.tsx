import React, { useEffect, useState } from 'react'
import { List } from '@phosphor-icons/react'

interface OnThisPageProps {
  headings: { id: string; title: string }[]
}

export const DocsOnThisPage: React.FC<OnThisPageProps> = ({ headings }) => {
  const [activeId, setActiveId] = useState<string>(headings[0]?.id || '')

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id)
          }
        })
      },
      {
        rootMargin: '0px 0px -60% 0px',
        threshold: 0.1,
      }
    )

    headings.forEach((h) => {
      const el = document.getElementById(h.id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [headings])

  if (headings.length === 0) return null

  const scrollToHeading = (id: string) => {
    const el = document.getElementById(id)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setActiveId(id)
    }
  }

  return (
    <nav className="w-full text-xs font-body text-stone-600 select-none space-y-3 sticky top-24">
      <div className="flex items-center gap-1.5 text-stone-900 font-mono font-semibold uppercase text-[11px] tracking-wider pb-2 border-b border-stone-200/80">
        <List size={14} className="text-emerald-700" />
        <span>On This Page</span>
      </div>

      <ul className="space-y-1.5 text-xs pl-1">
        {headings.map((h) => {
          const isActive = activeId === h.id

          return (
            <li key={h.id}>
              <button
                type="button"
                onClick={() => scrollToHeading(h.id)}
                className={`text-left block w-full truncate py-1 px-1.5 rounded transition-all ${
                  isActive
                    ? 'text-emerald-900 font-bold border-l-2 border-emerald-700 pl-2 bg-emerald-50/60'
                    : 'text-stone-600 hover:text-stone-900 hover:bg-stone-100/60'
                }`}
              >
                {h.title}
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
