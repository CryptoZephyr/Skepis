import React, { useState } from 'react'
import { Terminal, Copy, Check, BookOpen, Play } from '@phosphor-icons/react'

interface HeroProps {
  onNavigateToDocs: (slug?: string) => void
  onScrollToTerminal: () => void
}

export const Hero: React.FC<HeroProps> = ({
  onNavigateToDocs,
  onScrollToTerminal,
}) => {
  const [copied, setCopied] = useState(false)
  const installCmd = 'npx skepis init'

  const handleCopy = () => {
    navigator.clipboard.writeText(installCmd)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section className="relative min-h-[90vh] sm:min-h-[92vh] flex items-center justify-center pt-24 sm:pt-28 pb-12 sm:pb-20 px-3 sm:px-6 overflow-hidden">
      {/* Full-Screen Ambient Cream Architectural Media Background */}
      <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden select-none">
        <img
          src="/assets/hero_cream_bg.jpg"
          alt="Skepis architectural cream marble and glass background"
          className="w-full h-full object-cover object-center filter contrast-[1.08] brightness-[1.02] saturate-[1.05]"
        />

        {/* Ambient Overlays to Guarantee Flawless Text Legibility */}
        <div className="absolute inset-0 bg-radial-[ellipse_at_center] from-white/45 via-[#fbf9f5]/25 to-[#fbf9f5]/80 pointer-events-none" />
        <div className="absolute inset-x-0 bottom-0 h-44 bg-gradient-to-t from-[#fbf9f5] via-[#fbf9f5]/85 to-transparent pointer-events-none" />
        <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-[#fbf9f5]/80 to-transparent pointer-events-none" />
      </div>

      <div className="relative z-10 max-w-4xl mx-auto w-full flex flex-col items-start text-left">
        {/* Main Frosted Glass Hero Card */}
        <div className="w-full flex flex-col items-start text-left space-y-5 sm:space-y-6 p-5 sm:p-8 md:p-12 rounded-xl sm:rounded-2xl glass-panel border border-white/95 shadow-2xl backdrop-blur-2xl bg-white/85 transition-all duration-300">
          {/* Direct headline without fluff badges */}
          <h1 className="font-heading text-2xl sm:text-4xl md:text-5xl lg:text-6xl font-extrabold tracking-tight text-stone-950 leading-[1.12] text-balance">
            Know which benchmark tasks your agent can still honestly be tested on
          </h1>

          {/* Restrained value prop copy */}
          <p className="font-body text-xs sm:text-base text-stone-700 max-w-[56ch] leading-relaxed font-normal">
            Skepis records exposure through its supported protected-read boundary and gates clean claims. It is designed for cooperative agent workflows, not as a bypass-proof sandbox or universal monitor.
          </p>

          {/* Quick Start Command Line Bar */}
          <div className="w-full max-w-md glass-panel p-1.5 sm:p-2 rounded-lg border border-stone-300 flex items-center justify-between gap-2 shadow-xs bg-white/95">
            <div className="flex items-center gap-2 sm:gap-3 overflow-hidden px-1.5 sm:px-2 min-w-0">
              <Terminal size={17} className="text-emerald-700 shrink-0" />
              <code className="text-xs sm:text-sm font-mono text-stone-900 truncate font-semibold">
                {installCmd}
              </code>
            </div>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-md text-xs font-body font-medium text-stone-700 glass-panel-subtle hover:bg-stone-200/60 hover:text-stone-950 active:scale-[0.97] transition-all shrink-0 border border-stone-300 min-h-[36px]"
              title="Copy to clipboard"
              type="button"
            >
              {copied ? (
                <>
                  <Check size={14} className="text-emerald-700" />
                  <span className="text-emerald-700 font-semibold font-body">Copied</span>
                </>
              ) : (
                <>
                  <Copy size={14} />
                  <span className="font-body">Copy</span>
                </>
              )}
            </button>
          </div>

          {/* CTAs mapped to concrete actions */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full sm:w-auto pt-2">
            <button
              type="button"
              onClick={() => onNavigateToDocs('start/quickstart')}
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-xs font-body font-semibold text-white bg-emerald-800 hover:bg-emerald-900 active:scale-[0.98] transition-all shadow-sm shadow-emerald-950/10 min-h-[42px]"
            >
              <BookOpen size={14} weight="bold" />
              <span>Read Documentation</span>
            </button>

            <button
              type="button"
              onClick={onScrollToTerminal}
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-xs font-body font-semibold text-stone-800 glass-panel hover:text-stone-950 border border-stone-300 active:scale-[0.98] transition-all shadow-xs min-h-[42px]"
            >
              <Play size={14} weight="fill" />
              <span>Try Interactive CLI</span>
            </button>
          </div>

          {/* Factual evidence status strip */}
          <div className="pt-3 border-t border-stone-200/80 w-full flex flex-col sm:flex-row sm:items-center justify-between text-[11px] font-mono text-stone-500 gap-1.5 sm:gap-2">
            <span>108 Linux & 108 Windows Tests Verified</span>
            <span>Sibyl Memory Backend</span>
            <span>5 Native MCP Adapters</span>
          </div>
        </div>
      </div>
    </section>
  )
}
