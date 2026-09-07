import { useState } from 'react'
import { TerminalWindow, Play, ArrowClockwise } from '@phosphor-icons/react'

interface CommandTab {
  id: string
  label: string
  command: string
  output: string
  description: string
}

const COMMANDS: CommandTab[] = [
  {
    id: 'init',
    label: '1. init',
    command: 'npx skepis init',
    description: 'Registers benchmark identity, task IDs, protected resource patterns, and evaluator command.',
    output: `Skepis ready.

Benchmark: payments-regression
Agent: payments-agent
Tasks: 18
Protected resources: 3 patterns
Policy: EXCLUDE
Memory: available (Sibyl store online)

Next: skepis connect`,
  },
  {
    id: 'connect',
    label: '2. connect',
    command: 'skepis connect',
    description: 'Auto-detects project MCP client, merges stdio server, and verifies tool discovery.',
    output: `Detected: Claude Code (.mcp.json)
Project: payments-agent

✓ Skepis MCP stdio server configured
✓ Handshake verified (5 tools reachable)
✓ Project instruction written to CLAUDE.md

Skepis is connected.
Continue using your coding agent normally.`,
  },
  {
    id: 'eval',
    label: '3. eval',
    command: 'skepis eval',
    description: 'Filters exposed tasks via policy and runs the evaluator only on clean tasks.',
    output: `Skepis Evaluation

payments-agent × payments-regression

18 requested
16 clean
2 previously exposed

Evaluating 16 clean tasks...

Passed: 14 / 16
Clean score: 87.5%
2 exposed tasks excluded

Clean claim: permitted`,
  },
  {
    id: 'inspect',
    label: '4. inspect',
    command: 'skepis inspect',
    description: 'Read-only safe provenance explanation for why tasks were excluded.',
    output: `Why didn't these tasks count?

oauth-refresh-expiry
EXPOSED
Protected material accessed Aug 31 14:22:01
Source: private/answers/refund.yaml (ProtectedReadBoundary)

inventory-race-condition
UNKNOWN
Monitoring history incomplete (direct bash access detected)

Run \`skepis report\` for full audit record.`,
  },
  {
    id: 'report',
    label: '5. report',
    command: 'skepis report --json',
    description: 'Retrieves canonical portable evaluation report with cryptographic audit journal.',
    output: `{
  "schema_version": "1.0",
  "benchmark_id": "payments-regression",
  "evaluation_subject": "payments-agent",
  "run_id": "eval_8f319a2b",
  "timestamp": "2026-09-02T11:42:00Z",
  "policy": "EXCLUDE",
  "task_partitions": {
    "requested_count": 18,
    "clean_count": 16,
    "exposed_count": 2,
    "unknown_count": 0
  },
  "evaluated_tasks": ["refund-idempotency", "webhook-signature", "..."],
  "score": 0.875,
  "clean_claim_permitted": true,
  "monitoring_coverage": {
    "protected_reads": "COMPLETE",
    "generic_shell": "INCOMPLETE_MONITORING",
    "sibyl_memory": "AVAILABLE"
  }
}`,
  },
]

export const TerminalSimulator: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('init')
  const [isRunning, setIsRunning] = useState(false)
  const [ran, setRan] = useState(true)

  const current = COMMANDS.find((c) => c.id === activeTab) || COMMANDS[0]

  const handleRun = () => {
    setIsRunning(true)
    setRan(false)
    setTimeout(() => {
      setIsRunning(false)
      setRan(true)
    }, 450)
  }

  return (
    <div className="my-6 rounded-xl border border-stone-200/90 bg-[#161a1f] shadow-lg overflow-hidden text-stone-100">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-stone-800 bg-[#111418] px-3 sm:px-4 py-2.5 gap-2">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5 mr-2">
            <div className="w-2.5 h-2.5 rounded-full bg-stone-700" />
            <div className="w-2.5 h-2.5 rounded-full bg-stone-700" />
            <div className="w-2.5 h-2.5 rounded-full bg-stone-700" />
          </div>
          <TerminalWindow size={15} weight="bold" className="text-emerald-400" />
          <span className="text-xs font-mono text-stone-300 font-medium">skepis-interactive-cli</span>
        </div>

        <div className="w-full sm:w-auto overflow-x-auto no-scrollbar flex items-center gap-1 bg-[#1a1e24] p-1 rounded-md border border-stone-800">
          {COMMANDS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id)
                setRan(true)
              }}
              type="button"
              className={`whitespace-nowrap shrink-0 px-2.5 py-1 text-[11px] font-mono rounded transition-colors ${
                activeTab === tab.id
                  ? 'bg-emerald-800/80 text-white font-semibold shadow-xs'
                  : 'text-stone-400 hover:text-stone-200 hover:bg-stone-800/50'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Description */}
      <div className="px-3 sm:px-4 py-2 text-xs bg-[#191e24] text-stone-400 border-b border-stone-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
        <span className="text-stone-300 text-[11px] sm:text-xs">{current.description}</span>
        <button
          onClick={handleRun}
          type="button"
          disabled={isRunning}
          className="inline-flex items-center gap-1 text-[11px] font-mono text-emerald-400 hover:text-emerald-300 transition-colors self-start sm:self-auto"
        >
          {isRunning ? (
            <ArrowClockwise size={12} className="animate-spin" />
          ) : (
            <Play size={12} weight="fill" />
          )}
          <span>Re-run</span>
        </button>
      </div>

      {/* Terminal View */}
      <div className="p-5 font-mono text-xs leading-relaxed overflow-x-auto min-h-[220px]">
        <div className="flex items-center gap-2 text-stone-400 mb-3 select-none">
          <span className="text-emerald-400 font-bold">$</span>
          <span className="text-stone-100 font-semibold">{current.command}</span>
        </div>

        {isRunning ? (
          <div className="flex items-center gap-2 text-stone-500 py-6">
            <ArrowClockwise size={14} className="animate-spin text-emerald-400" />
            <span>Running command in isolated environment...</span>
          </div>
        ) : ran ? (
          <pre className="text-stone-300 font-mono text-xs whitespace-pre-wrap leading-relaxed animate-in fade-in duration-200">
            {current.output}
          </pre>
        ) : null}
      </div>
    </div>
  )
}
