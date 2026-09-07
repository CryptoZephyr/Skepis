import React from 'react'
import { Database, ArrowUpRight, Cpu, ShieldCheck, Coins } from '@phosphor-icons/react'

interface SponsorSectionProps {
  onNavigateToDocs: (slug: string) => void
}

export const SponsorSection: React.FC<SponsorSectionProps> = ({ onNavigateToDocs }) => {
  return (
    <section className="relative z-10 max-w-7xl mx-auto px-3 sm:px-6 py-8 sm:py-12">
      {/* Section Header */}
      <div className="text-center max-w-2xl mx-auto mb-6 sm:mb-8 space-y-2">
        <div className="inline-flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200/80 text-emerald-900 text-[11px] sm:text-xs font-mono">
          <Database size={13} className="text-emerald-700 shrink-0" />
          <span>Core Infrastructure & Partner Ecosystem</span>
        </div>
        <h2 className="font-heading text-xl sm:text-2xl md:text-3xl font-extrabold text-stone-950 tracking-tight text-balance">
          Backed by Sibyl Labs: Built for Agent Runtimes
        </h2>
        <p className="text-xs sm:text-sm text-stone-600 font-body leading-relaxed max-w-[56ch] mx-auto">
          Sibyl Memory is the separate persistent state layer that carries Skepis exposure evidence across process and session boundaries.
        </p>
      </div>

      {/* Primary Sponsor Card: Sibyl Labs */}
      <div className="p-4 sm:p-6 md:p-8 rounded-xl sm:rounded-2xl glass-panel border border-stone-200/90 bg-white/85 shadow-lg backdrop-blur-xl mb-6 sm:mb-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
          <div className="lg:col-span-8 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-heading text-lg sm:text-2xl font-black text-stone-900 tracking-tight">
                Sibyl Labs
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] sm:text-[11px] font-mono font-bold uppercase bg-emerald-100 text-emerald-900 border border-emerald-200">
                Primary Memory Partner
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] sm:text-[11px] font-mono text-stone-600 bg-stone-100 border border-stone-200">
                Persistent Memory Layer
              </span>
            </div>

            <p className="text-xs sm:text-sm text-stone-700 leading-relaxed font-body max-w-[62ch]">
              Sibyl Memory carries scoped exposure state and journal events across process and session boundaries. Skepis uses that state to gate clean claims after exposure is captured through its supported boundary. It does not observe unmediated shell, browser, filesystem, or unsupported MCP access.
            </p>

            <div className="flex flex-wrap gap-3 sm:gap-4 pt-1 text-xs font-mono text-stone-600">
              <div className="flex items-center gap-1.5">
                <ShieldCheck size={15} className="text-emerald-700 shrink-0" />
                <span>WARM State Isolation</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Database size={15} className="text-emerald-700 shrink-0" />
                <span>COLD Append-Only Journal</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Cpu size={15} className="text-emerald-700 shrink-0" />
                <span>sibyl-memory-client v0.7.0</span>
              </div>
            </div>
          </div>

          <div className="lg:col-span-4 flex flex-col sm:flex-row lg:flex-col gap-2.5 sm:gap-3 justify-end lg:items-end w-full">
            <a
              href="https://sibyllabs.org"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-xs font-body font-semibold text-white bg-emerald-800 hover:bg-emerald-900 transition-all shadow-xs w-full sm:w-auto min-h-[40px]"
            >
              <span>Visit Sibyl Labs</span>
              <ArrowUpRight size={14} weight="bold" />
            </a>
            <button
              type="button"
              onClick={() => onNavigateToDocs('concepts/state-model')}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-xs font-body font-semibold text-stone-800 bg-stone-100 hover:bg-stone-200/80 border border-stone-300 transition-all shadow-xs w-full sm:w-auto min-h-[40px]"
            >
              <span>Read Memory Architecture</span>
            </button>
          </div>
        </div>
      </div>

      {/* Grid of Verified Agent Runtimes & Roadmap Networks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-5 text-xs font-body">
        {/* Verified Runtimes */}
        <div className="p-4 sm:p-5 rounded-xl bg-white/70 border border-stone-200/80 shadow-xs backdrop-blur-md space-y-3">
          <div className="flex items-center justify-between border-b border-stone-200/80 pb-2">
            <span className="font-mono font-bold uppercase text-[10px] sm:text-[11px] text-stone-500 tracking-wider">
              Verified MCP Agent Runtimes
            </span>
            <span className="font-mono text-[10px] text-emerald-800 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
              5 Hosts Tested
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 sm:gap-2.5 pt-1">
            <div className="p-2 sm:p-2.5 rounded-lg bg-[#fbf9f5] border border-stone-200/70">
              <span className="font-semibold text-stone-900 block text-xs truncate">Claude Code</span>
              <span className="text-[10px] font-mono text-stone-500">.mcp.json</span>
            </div>
            <div className="p-2 sm:p-2.5 rounded-lg bg-[#fbf9f5] border border-stone-200/70">
              <span className="font-semibold text-stone-900 block text-xs truncate">Cursor</span>
              <span className="text-[10px] font-mono text-stone-500">.cursor/mcp</span>
            </div>
            <div className="p-2 sm:p-2.5 rounded-lg bg-[#fbf9f5] border border-stone-200/70">
              <span className="font-semibold text-stone-900 block text-xs truncate">Codex</span>
              <span className="text-[10px] font-mono text-stone-500">config.toml</span>
            </div>
            <div className="p-2 sm:p-2.5 rounded-lg bg-[#fbf9f5] border border-stone-200/70">
              <span className="font-semibold text-stone-900 block text-xs truncate">Antigravity</span>
              <span className="text-[10px] font-mono text-stone-500">.agents/mcp</span>
            </div>
            <div className="p-2 sm:p-2.5 rounded-lg bg-[#fbf9f5] border border-stone-200/70">
              <span className="font-semibold text-stone-900 block text-xs truncate">Gemini CLI</span>
              <span className="text-[10px] font-mono text-stone-500">settings.json</span>
            </div>
            <div className="p-2 sm:p-2.5 rounded-lg bg-[#fbf9f5] border border-stone-200/70 flex items-center justify-center">
              <button
                type="button"
                onClick={() => onNavigateToDocs('integrate/mcp-clients')}
                className="text-[11px] font-semibold text-emerald-800 hover:underline"
              >
                View Matrix →
              </button>
            </div>
          </div>
        </div>

        {/* Economic / Network Expansion Roadmap */}
        <div className="p-4 sm:p-5 rounded-xl bg-white/70 border border-stone-200/80 shadow-xs backdrop-blur-md space-y-3">
          <div className="flex items-center justify-between border-b border-stone-200/80 pb-2">
            <span className="font-mono font-bold uppercase text-[10px] sm:text-[11px] text-stone-500 tracking-wider">
              Evaluation Network Roadmap
            </span>
            <span className="font-mono text-[10px] text-stone-500 bg-stone-100 px-2 py-0.5 rounded border border-stone-200">
              Roadmap Scope
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
            <div className="p-3 rounded-lg bg-[#fbf9f5] border border-stone-200/70 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-stone-900">Virtuals Protocol</span>
                <span className="text-[10px] font-mono text-stone-400">ACP</span>
              </div>
              <p className="text-[11px] text-stone-600 leading-relaxed">
                Agent Commerce Protocol integration for autonomous agent evaluation discovery.
              </p>
            </div>

            <div className="p-3 rounded-lg bg-[#fbf9f5] border border-stone-200/70 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-stone-900">Base</span>
                <Coins size={13} className="text-stone-400" />
              </div>
              <p className="text-[11px] text-stone-600 leading-relaxed">
                Micropayment settlement and x402 payment receipts for independent evaluation jobs.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
