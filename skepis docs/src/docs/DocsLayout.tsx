import { useState } from 'react'
import { DocsSidebar } from './DocsSidebar'
import { DocsOnThisPage } from './DocsOnThisPage'
import { DOCS_CONTENT } from './docs-content'
import { DOCS_SECTIONS } from './docs-navigation'
import { List, X, CaretLeft, CaretRight } from '@phosphor-icons/react'

interface DocsLayoutProps {
  currentSlug: string
  onSelectSlug: (slug: string) => void
}

export const DocsLayout: React.FC<DocsLayoutProps> = ({
  currentSlug,
  onSelectSlug,
}) => {
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)

  const doc = DOCS_CONTENT[currentSlug] || DOCS_CONTENT['start/introduction']

  // Flatten items to compute previous & next pages
  const flatItems = DOCS_SECTIONS.flatMap((sec) => sec.items)
  const currentIndex = flatItems.findIndex((item) => item.slug === currentSlug)
  const prevItem = currentIndex > 0 ? flatItems[currentIndex - 1] : null
  const nextItem = currentIndex < flatItems.length - 1 ? flatItems[currentIndex + 1] : null

  return (
    <div className="max-w-7xl mx-auto pt-20 px-3 sm:px-6 pb-20">
      {/* Mobile Drawer Button */}
      <div className="lg:hidden flex items-center justify-between p-3 mb-4 rounded-lg bg-white border border-stone-200/90 shadow-xs min-h-[44px]">
        <button
          type="button"
          onClick={() => setMobileDrawerOpen(true)}
          className="inline-flex items-center gap-2 text-xs font-semibold text-stone-800"
        >
          <List size={16} weight="bold" className="text-emerald-700" />
          <span>Documentation Menu</span>
        </button>
        <span className="text-[11px] font-mono text-stone-500">
          {doc.category.split('/')[1]?.trim() || doc.category}
        </span>
      </div>

      {/* Mobile Drawer Overlay */}
      {mobileDrawerOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-stone-900/40 backdrop-blur-xs"
            onClick={() => setMobileDrawerOpen(false)}
          />
          <div className="relative w-72 max-w-[85vw] h-full bg-[#fbf9f5] z-10 shadow-2xl flex flex-col">
            <div className="flex items-center justify-between p-3 border-b border-stone-200 bg-white">
              <span className="font-heading text-sm font-bold text-stone-900">
                Documentation Navigation
              </span>
              <button
                type="button"
                onClick={() => setMobileDrawerOpen(false)}
                className="p-1 rounded text-stone-500 hover:text-stone-900"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <DocsSidebar
                currentSlug={currentSlug}
                onSelectSlug={(slug) => {
                  onSelectSlug(slug)
                  setMobileDrawerOpen(false)
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Main 3-Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Fixed Sidebar Desktop */}
        <div className="hidden lg:block lg:col-span-3 sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto rounded-xl border border-stone-200/80 bg-white/70 shadow-xs backdrop-blur-md">
          <DocsSidebar
            currentSlug={currentSlug}
            onSelectSlug={onSelectSlug}
          />
        </div>

        {/* Center Column: Main Reading Content */}
        <article className="lg:col-span-6 bg-white/85 rounded-xl border border-stone-200/80 p-4 sm:p-6 md:p-8 shadow-xs backdrop-blur-sm min-h-[500px]">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 text-xs font-mono text-stone-500 mb-3">
            <span>Docs</span>
            <span>/</span>
            <span className="text-emerald-800 font-semibold">{doc.category}</span>
          </div>

          {/* Heading */}
          <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-stone-900 tracking-tight mb-6 pb-4 border-b border-stone-200 text-balance">
            {doc.title}
          </h1>

          {/* Content Body */}
          <div className="doc-content-wrapper">
            {doc.content}
          </div>

          {/* Previous / Next Footer Nav */}
          <div className="mt-12 pt-6 border-t border-stone-200 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 font-body">
            {prevItem ? (
              <button
                type="button"
                onClick={() => {
                  onSelectSlug(prevItem.slug)
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
                className="group text-left p-3 rounded-lg border border-stone-200 hover:border-stone-400 bg-[#fbf9f5] transition-all flex items-center gap-2 w-full sm:max-w-[48%]"
              >
                <CaretLeft size={16} className="text-stone-400 group-hover:text-stone-900 shrink-0" />
                <div className="min-w-0">
                  <span className="text-[10px] font-mono uppercase text-stone-400 block">Previous</span>
                  <span className="text-xs font-semibold text-stone-800 group-hover:text-emerald-800 truncate block">
                    {prevItem.title}
                  </span>
                </div>
              </button>
            ) : <div />}

            {nextItem ? (
              <button
                type="button"
                onClick={() => {
                  onSelectSlug(nextItem.slug)
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
                className="group text-right p-3 rounded-lg border border-stone-200 hover:border-stone-400 bg-[#fbf9f5] transition-all flex items-center justify-end gap-2 w-full sm:max-w-[48%] ml-auto"
              >
                <div className="min-w-0">
                  <span className="text-[10px] font-mono uppercase text-stone-400 block">Next</span>
                  <span className="text-xs font-semibold text-stone-800 group-hover:text-emerald-800 truncate block">
                    {nextItem.title}
                  </span>
                </div>
                <CaretRight size={16} className="text-stone-400 group-hover:text-stone-900 shrink-0" />
              </button>
            ) : null}
          </div>
        </article>

        {/* Right Column: On This Page Table of Contents */}
        <div className="hidden lg:block lg:col-span-3">
          <DocsOnThisPage headings={doc.onThisPage} />
        </div>
      </div>
    </div>
  )
}
