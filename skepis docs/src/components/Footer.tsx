import React, { useState } from 'react'
import { Dialog } from '@base-ui-components/react/dialog'
import { GithubLogo } from '@phosphor-icons/react'

interface FooterProps {
  onNavigateToDocs: (slug: string) => void
}

export const Footer: React.FC<FooterProps> = ({ onNavigateToDocs }) => {
  const [activeDialog, setActiveDialog] = useState<'security' | 'privacy' | null>(null)

  return (
    <footer className="relative bg-[#fbf9f5] border-t border-stone-200/80 pt-12 sm:pt-16 pb-10 sm:pb-12 px-3 sm:px-6 text-xs text-stone-600 font-body">
      <div className="max-w-7xl mx-auto grid grid-cols-1 sm:grid-cols-2 md:grid-cols-12 gap-8 sm:gap-10 pb-10 sm:pb-12 border-b border-stone-200">
        <div className="md:col-span-4 space-y-4">
          <div className="flex items-center gap-2.5">
            <img
              src="/skepis_logo_dark.png"
              alt="Skepis logo"
              className="w-7 h-7 sm:w-8 sm:h-8 object-contain shrink-0"
            />
            <span className="font-heading text-lg sm:text-xl font-bold text-stone-900 tracking-tight">skepis</span>
            <span className="text-[10px] font-mono text-stone-500 bg-stone-100 px-1.5 py-0.5 rounded border border-stone-200">
              v0.1.4
            </span>
          </div>
          <p className="text-stone-600 text-xs leading-relaxed max-w-[38ch] font-body">
            Local-first policy-gated evaluation and protected-resource capture for AI coding-agent benchmarks.
          </p>
          <div className="flex items-center gap-3 text-stone-700">
            <a
              href="https://github.com/CryptoZephyr/Skepis"
              target="_blank"
              rel="noreferrer"
              className="p-2 rounded-md glass-panel-subtle hover:text-stone-950 border border-stone-300 transition-colors"
              aria-label="GitHub Repository"
            >
              <GithubLogo size={16} />
            </a>
          </div>
          <div className="pt-2 border-t border-stone-200/70 text-[11px] font-mono text-stone-500 space-y-0.5">
            <div>
              <span>Memory Partner: </span>
              <a
                href="https://sibyllabs.org"
                target="_blank"
                rel="noreferrer"
                className="text-emerald-800 font-semibold hover:underline"
              >
                Sibyl Labs
              </a>
            </div>
            <div className="text-[10px] text-stone-400">
              Persistent Cross-Session Memory
            </div>
          </div>
        </div>

        <div className="md:col-span-3 space-y-3">
          <div className="text-stone-900 font-semibold uppercase tracking-wider text-[11px] font-body">
            Documentation
          </div>
          <ul className="space-y-2 font-body text-xs">
            <li>
              <button
                type="button"
                onClick={() => onNavigateToDocs('start/introduction')}
                className="hover:text-emerald-800 transition-colors"
              >
                Introduction & Mental Model
              </button>
            </li>
            <li>
              <button
                type="button"
                onClick={() => onNavigateToDocs('start/quickstart')}
                className="hover:text-emerald-800 transition-colors"
              >
                Quickstart (4 Commands)
              </button>
            </li>
            <li>
              <button
                type="button"
                onClick={() => onNavigateToDocs('concepts/policy-engine')}
                className="hover:text-emerald-800 transition-colors"
              >
                Policy Engine & Clean Claims
              </button>
            </li>
            <li>
              <button
                type="button"
                onClick={() => onNavigateToDocs('integrate/mcp-clients')}
                className="hover:text-emerald-800 transition-colors"
              >
                Supported MCP Matrix
              </button>
            </li>
          </ul>
        </div>

        <div className="md:col-span-3 space-y-3">
          <div className="text-stone-900 font-semibold uppercase tracking-wider text-[11px] font-body">
            Architecture
          </div>
          <ul className="space-y-2 font-body text-xs">
            <li>
              <button
                type="button"
                onClick={() => onNavigateToDocs('concepts/state-model')}
                className="hover:text-emerald-800 transition-colors"
              >
                Sibyl WARM / COLD Memory
              </button>
            </li>
            <li>
              <button
                type="button"
                onClick={() => onNavigateToDocs('reference/mcp-tools')}
                className="hover:text-emerald-800 transition-colors"
              >
                MCP 5-Tool Reference
              </button>
            </li>
            <li>
              <button
                type="button"
                onClick={() => onNavigateToDocs('production/verification-matrix')}
                className="hover:text-emerald-800 transition-colors"
              >
                Verification Evidence (108 Tests)
              </button>
            </li>
            <li>
              <button
                type="button"
                onClick={() => onNavigateToDocs('help/faq')}
                className="hover:text-emerald-800 transition-colors"
              >
                FAQ & Invariants
              </button>
            </li>
          </ul>
        </div>

        <div className="md:col-span-2 space-y-3">
          <div className="text-stone-900 font-semibold uppercase tracking-wider text-[11px] font-body">
            Compatibility
          </div>
          <p className="text-stone-600 text-xs leading-relaxed font-body">
            Linux, WSL2, and Windows native runtimes. Supported adapters for Claude Code, Cursor, Codex, Antigravity, and Gemini CLI.
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto pt-6 sm:pt-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4 text-stone-600 font-body">
        <div>
          © 2026 Skepis Project. MIT Licensed.
        </div>
        <div className="flex items-center gap-6">
          <button
            onClick={() => setActiveDialog('security')}
            type="button"
            className="hover:text-stone-950 transition-colors underline-offset-4 hover:underline font-body"
          >
            Security Policy
          </button>
          <button
            onClick={() => setActiveDialog('privacy')}
            type="button"
            className="hover:text-stone-950 transition-colors underline-offset-4 hover:underline font-body"
          >
            Privacy Boundary
          </button>
        </div>
      </div>

      <Dialog.Root open={activeDialog !== null} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <Dialog.Portal>
          <Dialog.Backdrop className="base-dialog-backdrop" />
          <Dialog.Popup className="base-dialog-popup">
            <div className="glass-panel border border-stone-300 rounded-lg p-6 text-left shadow-2xl bg-white">
              <Dialog.Title className="text-base font-bold text-stone-900 mb-2 font-heading">
                {activeDialog === 'security' ? 'Security & Policy Boundary' : 'Privacy Boundary'}
              </Dialog.Title>
              <Dialog.Description className="text-xs text-stone-700 space-y-3 leading-relaxed font-body">
                {activeDialog === 'security' ? (
                  <>
                    <p>1. Local-First Core: Skepis stores exposure and evaluation state locally and does not provide a hosted telemetry service.</p>
                    <p>2. Subprocess Isolation: Evaluators run without a shell interpreter, mitigating command injection vectors.</p>
                    <p>3. Fail-Closed Behavior: Missing, deleted, or unverified memory states block clean evaluation claims.</p>
                  </>
                ) : (
                  <>
                    <p>1. No Secret Answer Persistence: Answer bodies and solution code are streamed to the agent and never cached or stored in Sibyl.</p>
                    <p>2. Scoped Event Journal: Only semantic task IDs, access timestamps, and resource path identifiers are journaled.</p>
                    <p>3. Safe Provenance Redaction: Inspection and report endpoints redact private evaluator payloads and unrelated tenant metadata.</p>
                  </>
                )}
              </Dialog.Description>
              <div className="mt-6 flex justify-end">
                <Dialog.Close
                  className="px-4 py-1.5 rounded-md text-xs font-body font-medium text-white bg-emerald-800 hover:bg-emerald-900 transition-all shadow-sm"
                >
                  Close
                </Dialog.Close>
              </div>
            </div>
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>
    </footer>
  )
}
