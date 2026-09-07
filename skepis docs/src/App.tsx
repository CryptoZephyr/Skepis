import { useState, useEffect } from 'react'
import { Navbar } from './components/Navbar'
import { Hero } from './components/Hero'
import { SponsorSection } from './components/SponsorSection'
import { ArchitectureSection } from './components/ArchitectureSection'
import { DocsLayout } from './docs/DocsLayout'
import { DocsSearchModal } from './docs/DocsSearchModal'
import { Footer } from './components/Footer'
import { DOCS_CONTENT } from './docs/docs-content'

export function App() {
  const [currentView, setCurrentView] = useState<'landing' | 'docs'>('landing')
  const [currentSlug, setCurrentSlug] = useState<string>('start/introduction')
  const [isSearchOpen, setIsSearchOpen] = useState(false)

  // Listen to hash changes for deep linking
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '')
      if (hash.startsWith('docs/')) {
        const slug = hash.replace('docs/', '')
        if (DOCS_CONTENT[slug]) {
          setCurrentView('docs')
          setCurrentSlug(slug)
        }
      } else if (DOCS_CONTENT[hash]) {
        setCurrentView('docs')
        setCurrentSlug(hash)
      } else if (hash === 'landing' || hash === '') {
        setCurrentView('landing')
      }
    }

    handleHashChange()
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const handleNavigate = (view: 'landing' | 'docs', slug?: string) => {
    setCurrentView(view)
    if (slug) {
      setCurrentSlug(slug)
      window.location.hash = `docs/${slug}`
    } else if (view === 'docs') {
      window.location.hash = `docs/${currentSlug}`
    } else {
      window.location.hash = 'landing'
    }
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleSelectSlug = (slug: string) => {
    setCurrentView('docs')
    setCurrentSlug(slug)
    window.location.hash = `docs/${slug}`
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleScrollToTerminal = () => {
    if (currentView !== 'landing') {
      setCurrentView('landing')
      setTimeout(() => {
        document.getElementById('interactive-suite')?.scrollIntoView({ behavior: 'smooth' })
      }, 50)
    } else {
      document.getElementById('interactive-suite')?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="min-h-screen bg-[#fbf9f5] text-stone-900 selection:bg-emerald-700/20 selection:text-emerald-950 font-body">
      {/* Fixed Header */}
      <Navbar
        currentView={currentView}
        onNavigate={handleNavigate}
        onOpenSearch={() => setIsSearchOpen(true)}
      />

      {/* Main Content Area */}
      <main className="transition-opacity duration-200">
        {currentView === 'landing' ? (
          <div>
            <Hero
              onNavigateToDocs={(slug) => handleNavigate('docs', slug)}
              onScrollToTerminal={handleScrollToTerminal}
            />
            <SponsorSection
              onNavigateToDocs={(slug) => handleNavigate('docs', slug)}
            />
            <ArchitectureSection />
          </div>
        ) : (
          <DocsLayout
            currentSlug={currentSlug}
            onSelectSlug={handleSelectSlug}
          />
        )}
      </main>

      {/* Footer */}
      <Footer onNavigateToDocs={handleSelectSlug} />

      {/* Global Cmd+K Search Dialog */}
      <DocsSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelectSlug={handleSelectSlug}
      />
    </div>
  )
}

export default App
