import { useState } from 'react'
import { TerminalSimulator } from '../docs/TerminalSimulator'
import { PolicyCalculator } from '../docs/PolicyCalculator'
import { McpConfigViewer } from '../docs/McpConfigViewer'

export const ArchitectureSection: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'terminal' | 'calculator' | 'matrix'>('terminal')

  return (
    <section id="interactive-suite" className="max-w-7xl mx-auto px-3 sm:px-6 py-10 sm:py-16">
      <div className="text-center max-w-3xl mx-auto mb-8 sm:mb-10 space-y-2.5 sm:space-y-3">
        <h2 className="font-heading text-xl sm:text-2xl md:text-3xl font-bold text-stone-950 tracking-tight text-balance">
          Interactive Evaluation Integrity Suite
        </h2>
        <p className="text-xs sm:text-sm text-stone-600 font-body leading-relaxed max-w-[60ch] mx-auto">
          Test Skepis commands, simulate policy calculations, and inspect MCP client adapter configurations before running locally.
        </p>

        <div className="flex justify-center pt-2 w-full">
          <div className="w-full sm:w-auto overflow-x-auto no-scrollbar flex items-center justify-start sm:justify-center p-1 rounded-lg bg-stone-200/70 border border-stone-300/80 gap-1">
            <button
              type="button"
              onClick={() => setActiveTab('terminal')}
              className={`whitespace-nowrap shrink-0 px-3 sm:px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${
                activeTab === 'terminal'
                  ? 'bg-white text-stone-900 shadow-xs'
                  : 'text-stone-600 hover:text-stone-900'
              }`}
            >
              Interactive CLI
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('calculator')}
              className={`whitespace-nowrap shrink-0 px-3 sm:px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${
                activeTab === 'calculator'
                  ? 'bg-white text-stone-900 shadow-xs'
                  : 'text-stone-600 hover:text-stone-900'
              }`}
            >
              Policy Calculator
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('matrix')}
              className={`whitespace-nowrap shrink-0 px-3 sm:px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${
                activeTab === 'matrix'
                  ? 'bg-white text-stone-900 shadow-xs'
                  : 'text-stone-600 hover:text-stone-900'
              }`}
            >
              MCP Client Matrix
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6">
        {activeTab === 'terminal' && <TerminalSimulator />}
        {activeTab === 'calculator' && <PolicyCalculator />}
        {activeTab === 'matrix' && <McpConfigViewer />}
      </div>

      {/* 4 Architecture Pillars */}
      <div className="mt-12 sm:mt-16 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-5 text-xs">
        <div className="p-5 rounded-xl bg-white/80 border border-stone-200 shadow-xs backdrop-blur-xs space-y-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-800 flex items-center justify-center font-bold">
            01
          </div>
          <h4 className="font-heading text-sm font-bold text-stone-900">Semantic Registration</h4>
          <p className="text-stone-600 leading-relaxed">
            Register arbitrary string task IDs, protected answer paths, and developer evaluators with no rigid fixture constraints.
          </p>
        </div>

        <div className="p-5 rounded-xl bg-white/80 border border-stone-200 shadow-xs backdrop-blur-xs space-y-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-800 flex items-center justify-center font-bold">
            02
          </div>
          <h4 className="font-heading text-sm font-bold text-stone-900">Zero-Touch Connect</h4>
          <p className="text-stone-600 leading-relaxed">
            Auto-detects Claude Code, Cursor, Codex, Antigravity, or Gemini CLI and configures project-scoped stdio MCP servers.
          </p>
        </div>

        <div className="p-5 rounded-xl bg-white/80 border border-stone-200 shadow-xs backdrop-blur-xs space-y-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-800 flex items-center justify-center font-bold">
            03
          </div>
          <h4 className="font-heading text-sm font-bold text-stone-900">Objective Capture</h4>
          <p className="text-stone-600 leading-relaxed">
            Records exposure only after successful registered reads, persisted securely in Sibyl Memory across process boundaries.
          </p>
        </div>

        <div className="p-5 rounded-xl bg-white/80 border border-stone-200 shadow-xs backdrop-blur-xs space-y-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-800 flex items-center justify-center font-bold">
            04
          </div>
          <h4 className="font-heading text-sm font-bold text-stone-900">Policy-Gated Eval</h4>
          <p className="text-stone-600 leading-relaxed">
            Filters contaminated tasks, evaluates clean subsets, and produces audit-ready clean claims with zero hallucinated scores.
          </p>
        </div>
      </div>
    </section>
  )
}
