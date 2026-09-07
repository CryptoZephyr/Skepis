import React, { useState, useEffect } from 'react'
import { Box, Flex } from '@radix-ui/themes'
import { Tooltip } from '@base-ui-components/react/tooltip'
import { GithubLogo, TerminalWindow, MagnifyingGlass, List, X } from '@phosphor-icons/react'

interface NavbarProps {
  onOpenSearch?: () => void
  currentView: 'landing' | 'docs'
  onNavigate: (view: 'landing' | 'docs', slug?: string) => void
}

export const Navbar: React.FC<NavbarProps> = ({
  onOpenSearch,
  currentView,
  onNavigate,
}) => {
  const [scrolled, setScrolled] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const handleNavClick = (view: 'landing' | 'docs', slug?: string) => {
    onNavigate(view, slug)
    setMobileMenuOpen(false)
  }

  return (
    <header className="fixed top-0 left-0 right-0 z-50 transition-all duration-300 px-3 py-2.5 sm:px-6 sm:py-3">
      <Box
        className={`max-w-7xl mx-auto px-4 py-2 sm:px-5 sm:py-2.5 rounded-xl transition-all duration-300 ${
          scrolled || mobileMenuOpen
            ? 'glass-panel shadow-md backdrop-blur-xl border border-stone-200/80 bg-white/90'
            : 'bg-white/85 backdrop-blur-md border border-stone-200/60 shadow-xs'
        }`}
      >
        <Flex align="center" justify="between">
          {/* Brand */}
          <Flex align="center" gap="2.5">
            <button
              type="button"
              onClick={() => handleNavClick('landing')}
              className="flex items-center gap-2 font-heading text-lg sm:text-xl font-extrabold text-stone-900 tracking-tight hover:text-emerald-800 transition-colors group"
            >
              <img
                src="/skepis_logo_dark.png"
                alt="Skepis logo"
                className="w-7 h-7 sm:w-8 sm:h-8 object-contain shrink-0 group-hover:scale-105 transition-transform"
              />
              <span>skepis</span>
            </button>
            <span className="text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-stone-100 text-stone-600 border border-stone-200">
              v0.1.4
            </span>
          </Flex>

          {/* Desktop Nav Links */}
          <nav className="hidden md:flex items-center gap-6 text-xs font-body font-medium text-stone-600">
            <button
              type="button"
              onClick={() => handleNavClick('landing')}
              className={`hover:text-stone-900 transition-colors ${
                currentView === 'landing' ? 'text-emerald-800 font-semibold' : ''
              }`}
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => handleNavClick('docs', 'start/quickstart')}
              className={`hover:text-stone-900 transition-colors ${
                currentView === 'docs' ? 'text-emerald-800 font-semibold' : ''
              }`}
            >
              Documentation
            </button>
            <button
              type="button"
              onClick={() => handleNavClick('docs', 'start/how-it-works')}
              className="hover:text-stone-900 transition-colors"
            >
              Architecture
            </button>
            <button
              type="button"
              onClick={() => handleNavClick('docs', 'integrate/mcp-clients')}
              className="hover:text-stone-900 transition-colors"
            >
              MCP Clients
            </button>
            <button
              type="button"
              onClick={() => handleNavClick('docs', 'reference/cli-commands')}
              className="hover:text-stone-900 transition-colors"
            >
              CLI Reference
            </button>
          </nav>

          {/* Right Actions */}
          <Flex align="center" gap="2">
            {/* Quick Search Button */}
            {onOpenSearch && (
              <button
                type="button"
                onClick={onOpenSearch}
                className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-stone-300/80 bg-stone-50 hover:bg-white text-stone-500 hover:text-stone-900 text-xs transition-colors"
                aria-label="Search documentation"
              >
                <MagnifyingGlass size={13} />
                <span className="text-[11px] text-stone-400">Search docs</span>
                <kbd className="text-[10px] font-mono bg-stone-200/80 px-1 py-0.2 rounded text-stone-600">⌘K</kbd>
              </button>
            )}

            {/* GitHub Desktop Tooltip */}
            <Tooltip.Root>
              <Tooltip.Trigger
                render={
                  <a
                    href="https://github.com/CryptoZephyr/Skepis"
                    target="_blank"
                    rel="noreferrer"
                    className="hidden sm:inline-flex p-2 rounded-md text-stone-500 hover:text-stone-900 glass-panel-subtle hover:border-stone-400 transition-all items-center justify-center"
                    aria-label="GitHub Repository"
                  >
                    <GithubLogo size={16} weight="bold" />
                  </a>
                }
              />
              <Tooltip.Portal>
                <Tooltip.Positioner side="bottom" sideOffset={6}>
                  <Tooltip.Popup className="base-tooltip-popup">
                    GitHub: CryptoZephyr/Skepis
                  </Tooltip.Popup>
                </Tooltip.Positioner>
              </Tooltip.Portal>
            </Tooltip.Root>

            {/* Quickstart CTA */}
            <button
              type="button"
              onClick={() => handleNavClick('docs', 'start/quickstart')}
              className="inline-flex items-center gap-1.5 px-2.5 sm:px-3.5 py-1.5 rounded-md text-xs font-body font-semibold text-white bg-emerald-800 hover:bg-emerald-900 transition-all active:scale-[0.98] shadow-sm shadow-emerald-900/10"
            >
              <TerminalWindow size={14} weight="bold" />
              <span className="hidden xs:inline sm:inline">npx skepis init</span>
              <span className="xs:hidden sm:hidden">Init</span>
            </button>

            {/* Mobile Hamburger Toggle Button */}
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden inline-flex items-center justify-center p-2 rounded-md text-stone-700 hover:text-stone-950 hover:bg-stone-100 border border-stone-200 transition-colors"
              aria-label="Toggle navigation menu"
              aria-expanded={mobileMenuOpen}
            >
              {mobileMenuOpen ? <X size={18} weight="bold" /> : <List size={18} weight="bold" />}
            </button>
          </Flex>
        </Flex>

        {/* Mobile Dropdown Menu */}
        {mobileMenuOpen && (
          <div className="md:hidden mt-3 pt-3 border-t border-stone-200/90 flex flex-col gap-1.5 pb-2 animate-in fade-in slide-in-from-top-2 duration-150">
            <button
              type="button"
              onClick={() => handleNavClick('landing')}
              className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium text-left transition-colors ${
                currentView === 'landing' ? 'bg-emerald-50 text-emerald-900 font-semibold' : 'text-stone-700 hover:bg-stone-100'
              }`}
            >
              <span>Overview</span>
              <span className="text-[10px] font-mono text-stone-400">Landing</span>
            </button>

            <button
              type="button"
              onClick={() => handleNavClick('docs', 'start/quickstart')}
              className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium text-left transition-colors ${
                currentView === 'docs' ? 'bg-emerald-50 text-emerald-900 font-semibold' : 'text-stone-700 hover:bg-stone-100'
              }`}
            >
              <span>Documentation</span>
              <span className="text-[10px] font-mono text-stone-400">Guides</span>
            </button>

            <button
              type="button"
              onClick={() => handleNavClick('docs', 'start/how-it-works')}
              className="flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium text-left text-stone-700 hover:bg-stone-100 transition-colors"
            >
              <span>Architecture</span>
              <span className="text-[10px] font-mono text-stone-400">Pillars</span>
            </button>

            <button
              type="button"
              onClick={() => handleNavClick('docs', 'integrate/mcp-clients')}
              className="flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium text-left text-stone-700 hover:bg-stone-100 transition-colors"
            >
              <span>MCP Clients</span>
              <span className="text-[10px] font-mono text-stone-400">5 Hosts</span>
            </button>

            <button
              type="button"
              onClick={() => handleNavClick('docs', 'reference/cli-commands')}
              className="flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium text-left text-stone-700 hover:bg-stone-100 transition-colors"
            >
              <span>CLI Reference</span>
              <span className="text-[10px] font-mono text-stone-400">Commands</span>
            </button>

            {/* Mobile Search & External Links */}
            <div className="pt-2 mt-1 border-t border-stone-200/80 grid grid-cols-2 gap-2">
              {onOpenSearch && (
                <button
                  type="button"
                  onClick={() => {
                    setMobileMenuOpen(false)
                    onOpenSearch()
                  }}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-stone-100 hover:bg-stone-200 text-stone-700 text-xs font-medium transition-colors"
                >
                  <MagnifyingGlass size={13} />
                  <span>Search Docs</span>
                </button>
              )}

              <a
                href="https://github.com/CryptoZephyr/Skepis"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-stone-100 hover:bg-stone-200 text-stone-700 text-xs font-medium transition-colors"
              >
                <GithubLogo size={14} weight="bold" />
                <span>GitHub</span>
              </a>
            </div>
          </div>
        )}
      </Box>
    </header>
  )
}
