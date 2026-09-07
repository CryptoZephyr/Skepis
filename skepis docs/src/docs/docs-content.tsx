import React from 'react'
import { CodeBlock } from './CodeBlock'
import { Callout } from './Callout'
import { TerminalSimulator } from './TerminalSimulator'
import { PolicyCalculator } from './PolicyCalculator'
import { McpConfigViewer } from './McpConfigViewer'

export interface DocContentMap {
  [slug: string]: {
    title: string
    category: string
    content: React.ReactNode
    onThisPage: { id: string; title: string }[]
  }
}

export const DOCS_CONTENT: DocContentMap = {
  'start/introduction': {
    title: 'Introduction to Skepis',
    category: '01 / Start',
    onThisPage: [
      { id: 'the-problem', title: 'The Contamination Problem' },
      { id: 'plain-language', title: 'Plain-language Model' },
      { id: 'evidence-example', title: 'Failure Mode and Correction' },
      { id: 'mental-model', title: 'One-Sentence Mental Model' },
      { id: 'core-invariant', title: 'The Supported Invariant' },
      { id: 'coverage-boundary', title: 'Monitoring Boundary' },
      { id: 'who-it-is-for', title: 'Target Audience' },
      { id: 'what-skepis-is-not', title: 'Product Boundary' },
      { id: 'where-next', title: 'Where This Goes Next' },
      { id: 'next-steps', title: 'Where to Go Next' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          <strong>Skepis</strong> keeps AI-agent evaluations honest by remembering which benchmark tasks have already been exposed and gating whether an existing evaluator may make a clean claim. It records exposure only when a registered protected resource is successfully read through a supported Skepis boundary. It does not score models, and it is not a bypass-proof sandbox or universal monitor.
        </p>

        <p className="text-xs leading-relaxed text-stone-700">
          <strong>Sibyl Memory</strong> is the separate persistent state layer Skepis uses to carry scoped exposure state and journal events across process and session boundaries.
        </p>

        <h2 id="the-problem" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          The Contamination Problem
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          During normal development, an autonomous AI coding agent can read a hidden test, benchmark answer key, solution patch, or protected task artifact. When that development session ends, its conversational context is wiped clean.
        </p>
        <p className="text-xs leading-relaxed text-stone-700">
          In a later evaluation session, the benchmark runner evaluates the agent. Because the evaluator runs in a fresh process without memory of earlier sessions, it assumes every task is pristine and clean. The agent gets scored on questions it already peeked at, creating wildly misleading benchmark results.
        </p>

        <h2 id="plain-language" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Plain-language Model
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          If an agent reads an answer file through the protected-read path, Skepis remembers that task. On a later evaluation, it excludes or blocks the task according to policy. If the agent uses a route outside the supported boundary, Skepis reports incomplete monitoring instead of pretending the task is clean.
        </p>

        <h2 id="evidence-example" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Failure Mode and Correction
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          This simplified example shows why an evaluator needs exposure history. The values illustrate the decision boundary, not a model score or an independent user result.
        </p>
        <CodeBlock
          code={`WITHOUT AN INTEGRITY GATE
Agent: reads private/answers/refund.yaml
Evaluator: receives all 18 task IDs and reports its score
Problem: the evaluator has no evidence of the earlier read

WITH THE SKEPIS PROTECTED-READ BOUNDARY
Skepis: refund-idempotency was exposed
Requested: 18 tasks
Selected for evaluation: 17 clean tasks
Clean claim: permitted for the selected set`}
          language="text"
        />

        <Callout type="invariant" title="The Supported Invariant">
          When a registered protected resource is successfully read through a supported Skepis boundary, the task is marked exposed and cannot contribute to a clean claim unless the benchmark policy explicitly resets or replaces that task.
        </Callout>

        <h2 id="mental-model" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          One-Sentence Mental Model
        </h2>
        <div className="p-4 rounded-lg bg-[#f4f1eb] border border-stone-300 font-heading text-sm font-semibold text-stone-900 italic">
          &ldquo;Know which benchmark tasks your agent can still honestly be tested on.&rdquo;
        </div>

        <h2 id="core-invariant" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Why Git and Local State Are Insufficient
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          A coding agent can inspect a protected file without modifying a single byte in Git. Because no commits or file diffs were generated, Git cannot testify to what the agent observed. Skepis uses <strong>Sibyl Memory</strong> to persist objective exposure events outside the agent transcript and repository files, surviving process and session destruction.
        </p>

        <h2 id="coverage-boundary" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Monitoring Boundary
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Installing an MCP server does not create universal observation. Skepis makes hard exposure decisions only for the boundary it controls and keeps gaps visible.
        </p>
        <div className="overflow-x-auto rounded-lg border border-stone-200">
          <table className="w-full text-left text-xs">
            <thead className="bg-stone-100 text-stone-900">
              <tr>
                <th className="p-2.5 font-semibold">Surface</th>
                <th className="p-2.5 font-semibold">Status</th>
                <th className="p-2.5 font-semibold">Meaning</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-200 bg-white text-stone-700">
              <tr>
                <td className="p-2.5">Registered protected reads</td>
                <td className="p-2.5 font-mono text-emerald-800">COMPLETE</td>
                <td className="p-2.5">Successful reads create objective exposure evidence.</td>
              </tr>
              <tr>
                <td className="p-2.5">Generic shell, filesystem, browser, or unsupported MCP access</td>
                <td className="p-2.5 font-mono text-amber-800">INCOMPLETE_MONITORING</td>
                <td className="p-2.5">The route is outside the current capture boundary.</td>
              </tr>
              <tr>
                <td className="p-2.5">Missing or mismatched Sibyl state</td>
                <td className="p-2.5 font-mono text-red-700">UNKNOWN</td>
                <td className="p-2.5">The task cannot support a clean claim until evidence is available.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h2 id="who-it-is-for" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Target Audience
        </h2>
        <ul className="list-disc list-inside text-xs leading-relaxed text-stone-700 space-y-1.5 pl-2">
          <li><strong>Coding Agent Developers:</strong> Building agents on Claude Code, Cursor, Codex, Antigravity, or Gemini CLI who need repeatable benchmarks.</li>
          <li><strong>Evaluation Engineers:</strong> Handling known exposure when testing regression suites against LLM agents.</li>
          <li><strong>Benchmark Maintainers:</strong> Tracking durable exposure history across evaluation test suites and agent worktrees.</li>
          <li><strong>AI Startups & Labs:</strong> Producing evidence-backed clean evaluation claims with explicit monitoring limits.</li>
        </ul>

        <h2 id="what-skepis-is-not" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Product Boundary (What Skepis Is Not)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          To maintain a narrow technical focus, Skepis explicitly rejects scope creep:
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div className="p-3 bg-stone-50 rounded border border-stone-200 text-stone-700">
            <strong>✕ NOT a generic eval logger</strong>: Only tracks protected exposure and policy gating.
          </div>
          <div className="p-3 bg-stone-50 rounded border border-stone-200 text-stone-700">
            <strong>✕ NOT a model training detector</strong>: Only records observable local agent exposure.
          </div>
          <div className="p-3 bg-stone-50 rounded border border-stone-200 text-stone-700">
            <strong>✕ NOT a background daemon/watcher</strong>: Zero background telemetry; runs on-demand.
          </div>
          <div className="p-3 bg-stone-50 rounded border border-stone-200 text-stone-700">
            <strong>✕ NOT an LLM heuristic evaluator</strong>: Model inference never creates hard contamination state.
          </div>
        </div>

        <h2 id="where-next" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Where This Goes Next
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          The current product is a local evaluation-integrity layer. The roadmap keeps the same evidence and eligibility model at the center while exploring shared team state, independent evaluation, and eventually an evaluation network where a clean result can be checked by someone other than the agent developer.
        </p>
        <p className="text-xs leading-relaxed text-stone-700">
          Those are future directions, not current capabilities. Inspect AI integration, Base settlement, and Virtuals coordination remain deferred until a real workflow needs them.
        </p>

        <h2 id="next-steps" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Where to Go Next
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Proceed to the <a href="#start/quickstart" className="text-emerald-700 font-semibold underline">Quickstart</a> to install Skepis and initialize your first project in under 2 minutes.
        </p>
      </div>
    ),
  },

  'start/quickstart': {
    title: 'Quickstart Guide',
    category: '01 / Start',
    onThisPage: [
      { id: 'interactive-terminal', title: 'Interactive CLI Tour' },
      { id: 'step-1-init', title: '1. Initialize Project' },
      { id: 'step-2-connect', title: '2. Connect MCP Agent' },
      { id: 'step-3-work', title: '3. Work Normally' },
      { id: 'step-4-eval', title: '4. Run Policy-Gated Evaluation' },
      { id: 'step-5-inspect', title: '5. Inspect Provenance' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          The standard Skepis journey consists of four simple commands. No daemons, no background services, and no complex configuration files to hand-edit.
        </p>

        <h2 id="interactive-terminal" className="font-heading text-lg font-bold text-stone-900 pt-2">
          Interactive CLI Tour
        </h2>
        <p className="text-xs text-stone-600">
          Click through the steps below to see exact terminal inputs and verified outputs from a live Skepis run:
        </p>
        <TerminalSimulator />

        <h2 id="step-1-init" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          1. Initialize Project (`skepis init`)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Run this in the repository containing the benchmark and evaluation targets:
        </p>
        <CodeBlock code="npx skepis init" language="bash" />
        <p className="text-xs leading-relaxed text-stone-700">
          `skepis init` prompts for:
        </p>
        <ul className="list-disc list-inside text-xs leading-relaxed text-stone-700 space-y-1 pl-2">
          <li><strong>Benchmark ID:</strong> e.g. <code className="font-mono text-stone-900 font-semibold">payments-regression</code></li>
          <li><strong>Evaluation Subject:</strong> e.g. <code className="font-mono text-stone-900 font-semibold">payments-agent</code></li>
          <li><strong>Task IDs & Protected Paths:</strong> e.g. <code className="font-mono text-stone-900">refund-idempotency=private/answers/refund.yaml</code></li>
          <li><strong>Evaluator Command:</strong> e.g. <code className="font-mono text-stone-900">python evaluate.py</code></li>
        </ul>

        <h2 id="step-2-connect" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          2. Connect MCP Agent (`skepis connect`)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Connect your coding agent environment with a single command:
        </p>
        <CodeBlock code="skepis connect" language="bash" />
        <p className="text-xs leading-relaxed text-stone-700">
          Skepis auto-detects Claude Code, Cursor, Codex, Antigravity, or Gemini CLI, merges the stdio server config, and installs the minimal instruction rule.
        </p>

        <h2 id="step-3-work" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          3. Work Normally
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Continue ordinary software development. When the agent accesses a protected benchmark resource via <code className="font-mono text-stone-900">skepis_read_protected</code>, Skepis verifies the path and records durable objective exposure in Sibyl Memory.
        </p>

        <h2 id="step-4-eval" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          4. Run Policy-Gated Evaluation (`skepis eval`)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Execute the evaluation command:
        </p>
        <CodeBlock code="skepis eval" language="bash" />
        <p className="text-xs leading-relaxed text-stone-700">
          Skepis checks Sibyl Memory, filters out previously exposed tasks under policy (default: <code className="font-mono text-stone-900">EXCLUDE</code>), and executes your evaluator only on clean tasks.
        </p>

        <h2 id="step-5-inspect" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          5. Inspect Provenance (`skepis inspect`)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          When an explanation is required for why a task was excluded or unknown:
        </p>
        <CodeBlock code="skepis inspect" language="bash" />
      </div>
    ),
  },

  'start/how-it-works': {
    title: 'How Skepis Works',
    category: '01 / Start',
    onThisPage: [
      { id: 'causal-loop', title: 'The Core Causal Loop' },
      { id: 'architecture-diagram', title: 'System Architecture' },
      { id: 'sibyl-memory', title: 'Why Sibyl is Load-Bearing' },
      { id: 'objective-evidence', title: 'Objective Evidence Standards' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis operates across process and session boundaries by separating the <strong>Capture Side</strong> from the <strong>Evaluation Side</strong>, linked together by <strong>Sibyl Memory</strong>.
        </p>

        <h2 id="causal-loop" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          The Core Causal Loop
        </h2>
        <div className="p-4 rounded-xl bg-[#1e232a] text-stone-200 font-mono text-xs leading-relaxed overflow-x-auto">
          <pre>{`PAST SESSION A
Agent accesses protected benchmark resource (private/answers/refund.yaml)
  ↓
OBJECTIVE CAPTURE
ProtectedReadBoundary confirms successful registered read
  ↓
SIBYL WRITE
Task 'refund-idempotency' is marked EXPOSED in WARM store
COLD append-only event 'benchmark_material_observed' journaled
  ↓
SESSION BOUNDARY
Process terminates. Conversational transcript is deleted.

═══════════════════════════════════════════════════════════════

FRESH SESSION B
Developer or CI starts evaluation run: 'skepis eval'
  ↓
SIBYL READ
Skepis queries WARM state: 'refund-idempotency' was previously exposed
  ↓
POLICY GATE DECISION
Policy EXCLUDE active: task excluded from clean evaluation set
  ↓
EVALUATION EXECUTION
Evaluator invoked only with clean task IDs in SKEPIS_TASK_IDS
  ↓
PORTABLE CLEAN REPORT
Report output: 14/16 passed on clean tasks (87.5%). Clean claim: permitted.`}</pre>
        </div>

        <h2 id="architecture-diagram" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          System Architecture
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="p-4 bg-white rounded-lg border border-stone-200 shadow-xs space-y-2">
            <h4 className="font-heading text-sm font-bold text-stone-900">Capture Side</h4>
            <p className="text-stone-600">Monitors registered protected benchmark file access through the <code className="font-mono text-stone-900">skepis_read_protected</code> MCP tool.</p>
            <ul className="list-disc list-inside text-stone-600 space-y-1">
              <li>In-root path validation</li>
              <li>Hash & identifier matching</li>
              <li>Exposure event generation</li>
              <li>Zero background daemon overhead</li>
            </ul>
          </div>
          <div className="p-4 bg-white rounded-lg border border-stone-200 shadow-xs space-y-2">
            <h4 className="font-heading text-sm font-bold text-stone-900">Evaluation Side</h4>
            <p className="text-stone-600">Loads durable Sibyl state and gates benchmark execution before the evaluator runs.</p>
            <ul className="list-disc list-inside text-stone-600 space-y-1">
              <li>Policy classification (CLEAN, EXPOSED, UNKNOWN)</li>
              <li>Dynamic task partitioning</li>
              <li>Evaluator subprocess invocation</li>
              <li>Safe portable report generation</li>
            </ul>
          </div>
        </div>

        <h2 id="sibyl-memory" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Why Sibyl Memory is Load-Bearing
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          A fresh evaluation session cannot infer what occurred in previous sessions from Git commits or local disk files. Reading a hidden test modifies no files. Sibyl Memory provides persistent, tenant-isolated memory that carries exposure truth across session lifecycles.
        </p>

        <h2 id="objective-evidence" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Objective Evidence Standards
        </h2>
        <Callout type="security" title="Non-Authoritative Model Inference">
          Model inference, LLM self-reports, or prompt inspection must NEVER create hard contamination state. Contamination in Skepis is strictly rooted in objective, observable events: verified reads of registered protected resources through the capture boundary.
        </Callout>
      </div>
    ),
  },

  'concepts/core-primitives': {
    title: 'Core Primitives',
    category: '02 / Concepts',
    onThisPage: [
      { id: 'benchmark-id', title: 'Benchmark Identity' },
      { id: 'evaluation-subject', title: 'Evaluation Subject' },
      { id: 'task-ids', title: 'Semantic Task IDs' },
      { id: 'protected-resources', title: 'Protected Resources' },
      { id: 'evaluator-command', title: 'Evaluator Command' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis operates on five semantic primitives configured in <code className="font-mono text-stone-900">skepis.json</code>.
        </p>

        <h2 id="benchmark-id" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          1. Benchmark Identity (<code className="font-mono text-stone-900 text-sm">benchmark_id</code>)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          A stable string identifying the test suite or regression benchmark (e.g. <code className="font-mono text-stone-900">payments-regression</code>, <code className="font-mono text-stone-900">swe-bench-lite</code>). All exposure events and evaluation runs are scoped to this identifier.
        </p>

        <h2 id="evaluation-subject" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          2. Evaluation Subject (<code className="font-mono text-stone-900 text-sm">evaluation_subject</code>)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          The entity being evaluated (for example, <code className="font-mono text-stone-900">payments-agent</code> or <code className="font-mono text-stone-900">checkout-agent</code>). Exposure state is tracked per subject, ensuring evaluations of different agents remain completely isolated.
        </p>

        <h2 id="task-ids" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          3. Semantic Task IDs (<code className="font-mono text-stone-900 text-sm">task_ids</code>)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Arbitrary strings identifying benchmark tasks (e.g. <code className="font-mono text-stone-900">refund-idempotency</code>, <code className="font-mono text-stone-900">auth-token-refresh</code>).
        </p>
        <Callout type="info" title="No Sequential Assumptions">
          Skepis does not require sequential numbers, fixed task counts, or numeric indexes. Arbitrary string task IDs of any length and count are fully supported.
        </Callout>

        <h2 id="protected-resources" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          4. Protected Resources (<code className="font-mono text-stone-900 text-sm">protected_resources</code>)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          File paths or patterns mapped to specific task IDs. When an agent opens these files through <code className="font-mono text-stone-900">skepis_read_protected</code>, exposure is recorded. Example:
        </p>
        <CodeBlock
          code={`{
  "refund-idempotency": "private/answers/refund.yaml",
  "auth-token-refresh": "private/keys/oauth_test_secret.json"
}`}
          language="json"
          filename="protected_resources mapping"
        />

        <h2 id="evaluator-command" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          5. Evaluator Command (<code className="font-mono text-stone-900 text-sm">evaluator_command</code>)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          The command executed during <code className="font-mono text-stone-900">skepis eval</code>. The evaluator receives selected task IDs via environment variables and outputs structured JSON to stdout.
        </p>
      </div>
    ),
  },

  'concepts/state-model': {
    title: 'State & Memory Model',
    category: '02 / Concepts',
    onThisPage: [
      { id: 'memory-tiers', title: 'WARM vs COLD Memory Tiers' },
      { id: 'warm-schema', title: 'WARM State Schema' },
      { id: 'cold-events', title: 'COLD Event Journal' },
      { id: 'deletion-test', title: 'The Deletion Test' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis memory architecture is split into two operational tiers backed by Sibyl Memory:
        </p>

        <h2 id="memory-tiers" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          WARM vs COLD Memory Tiers
        </h2>
        <div className="overflow-x-auto my-4">
          <table className="w-full text-xs font-body border border-stone-200 rounded-lg">
            <thead className="bg-[#f4f1eb] text-stone-900 font-semibold border-b border-stone-200 text-left">
              <tr>
                <th className="p-2.5">Tier</th>
                <th className="p-2.5">Role</th>
                <th className="p-2.5">Write Trigger</th>
                <th className="p-2.5">Read Trigger</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-200 text-stone-700">
              <tr>
                <td className="p-2.5 font-mono font-bold text-emerald-800">WARM</td>
                <td className="p-2.5">Canonical current eligibility state for all registered tasks.</td>
                <td className="p-2.5">Objective exposure access event.</td>
                <td className="p-2.5">Evaluation start (`skepis eval`) & preflight check.</td>
              </tr>
              <tr>
                <td className="p-2.5 font-mono font-bold text-blue-800">COLD</td>
                <td className="p-2.5">Append-only historical journal for audit and provenance verification.</td>
                <td className="p-2.5">Exposure, evaluation start, completion, or failure.</td>
                <td className="p-2.5">`skepis inspect` & portable report generation.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h2 id="warm-schema" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          WARM State Schema
        </h2>
        <CodeBlock
          code={`{
  "evaluation_subject": "payments-agent",
  "benchmark": "payments-regression",
  "tasks": {
    "refund-idempotency": {
      "eligibility": "EXPOSED",
      "reason": "protected_resource_accessed",
      "first_observed_at": "2026-08-31T14:22:01Z",
      "last_observed_at": "2026-08-31T14:22:01Z"
    },
    "oauth-refresh-expiry": {
      "eligibility": "UNSEEN"
    }
  }
}`}
          language="json"
          filename="WARM entity shape"
        />

        <h2 id="cold-events" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          COLD Event Journal
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Every critical lifecycle state transition emits an immutable COLD event:
        </p>
        <ul className="list-disc list-inside text-xs leading-relaxed text-stone-700 space-y-1 font-mono pl-2">
          <li>benchmark_material_observed</li>
          <li>evaluation_gate_decision</li>
          <li>evaluation_started</li>
          <li>evaluation_completed</li>
          <li>evaluation_failed</li>
          <li>observation_gap_detected</li>
        </ul>

        <h2 id="deletion-test" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          The Deletion Test (Fail-Closed Proof)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          If Sibyl state is deleted or unreachable, what happens? Skepis maps all requested tasks to <code className="font-mono text-stone-900 font-bold">UNKNOWN</code>, immediately halts in strict mode, and refuses to emit a clean evaluation claim. Missing evidence is never assumed to be clean.
        </p>
      </div>
    ),
  },

  'concepts/policy-engine': {
    title: 'Policy Engine',
    category: '02 / Concepts',
    onThisPage: [
      { id: 'interactive-calculator', title: 'Interactive Policy Calculator' },
      { id: 'policy-modes', title: 'Supported Policy Modes' },
      { id: 'clean-claim-rules', title: 'Clean Claim Permission Rules' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          The Policy Engine dictates how historical contamination impacts the evaluation run and whether a &ldquo;Clean claim: permitted&rdquo; verdict can be honestly granted.
        </p>

        <h2 id="interactive-calculator" className="font-heading text-lg font-bold text-stone-900 pt-2">
          Interactive Policy Calculator
        </h2>
        <p className="text-xs text-stone-600">
          Experiment with different task counts, exposed sets, and policy modes to observe how Skepis calculates clean scores:
        </p>
        <PolicyCalculator />

        <h2 id="policy-modes" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Supported Policy Modes
        </h2>
        <div className="space-y-3 text-xs">
          <div className="p-4 bg-white rounded-lg border border-stone-200 shadow-xs">
            <h4 className="font-mono font-bold text-stone-900 text-sm">EXCLUDE (Default)</h4>
            <p className="text-stone-600 mt-1">
              Contaminated tasks are excluded from the denominator. The evaluator is passed only the remaining pristine tasks. If 16 of 18 tasks are clean and 14 pass, the clean score is 14/16 (87.5%).
            </p>
          </div>
          <div className="p-4 bg-white rounded-lg border border-stone-200 shadow-xs">
            <h4 className="font-mono font-bold text-stone-900 text-sm">FLAG</h4>
            <p className="text-stone-600 mt-1">
              All tasks are evaluated, but exposed tasks are explicitly flagged in the portable report and metrics breakdowns.
            </p>
          </div>
          <div className="p-4 bg-white rounded-lg border border-stone-200 shadow-xs">
            <h4 className="font-mono font-bold text-stone-900 text-sm">STRICT</h4>
            <p className="text-stone-600 mt-1">
              Any prior exposure or unknown history causes the evaluation run to fail immediately. Zero contamination is tolerated.
            </p>
          </div>
        </div>

        <h2 id="clean-claim-rules" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Clean Claim Permission Rules
        </h2>
        <Callout type="warning" title="UNKNOWN Tasks Block Clean Claims">
          A clean claim is permitted ONLY when all evaluated tasks have verified pristine history and monitoring coverage is intact. If any task is in an UNKNOWN state, the clean claim is strictly DENIED.
        </Callout>
      </div>
    ),
  },

  'concepts/trust-boundary': {
    title: 'Trust & Data Boundary',
    category: '02 / Concepts',
    onThisPage: [
      { id: 'monitored-surface', title: 'Monitored Surface' },
      { id: 'incomplete-monitoring', title: 'INCOMPLETE_MONITORING' },
      { id: 'data-privacy', title: 'What Enters & Leaves Sibyl' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis adheres to an explicit, honest trust boundary. It never pretends to possess god-mode observation over an operating system.
        </p>

        <h2 id="monitored-surface" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          The Monitored Surface
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Skepis monitors registered in-root benchmark files accessed through the <code className="font-mono text-stone-900">skepis_read_protected</code> MCP tool. Access is verified, read, and immediately journaled into Sibyl.
        </p>

        <h2 id="incomplete-monitoring" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Handling Unmonitored Channels (INCOMPLETE_MONITORING)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          If an agent accesses files via raw Bash (<code className="font-mono text-stone-900">cat</code>), internal editor plugins, or browser tools that bypass MCP, Skepis does not claim universal interception. Instead, it marks those tasks as:
        </p>
        <div className="p-3 bg-stone-900 text-emerald-400 font-mono text-xs rounded-md">
          INCOMPLETE_MONITORING
        </div>
        <p className="text-xs leading-relaxed text-stone-700">
          Under fail-closed rules, incomplete monitoring results in an <code className="font-mono text-stone-900">UNKNOWN</code> task status, blocking an unearned clean claim.
        </p>

        <h2 id="data-privacy" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          What Enters & Leaves Sibyl
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-body">
          <div className="p-4 bg-emerald-50/70 border border-emerald-300 rounded-lg space-y-2">
            <span className="font-bold text-emerald-950 block">Recorded in Memory</span>
            <ul className="list-disc list-inside text-emerald-900 space-y-1">
              <li>Benchmark and Subject IDs</li>
              <li>Task IDs (semantic strings)</li>
              <li>Timestamp of observed access</li>
              <li>Resource path identifier</li>
              <li>Cryptographic hash of exposure event</li>
            </ul>
          </div>
          <div className="p-4 bg-stone-100 border border-stone-300 rounded-lg space-y-2">
            <span className="font-bold text-stone-950 block">NEVER Recorded</span>
            <ul className="list-disc list-inside text-stone-700 space-y-1">
              <li>Raw secret answer bodies</li>
              <li>Full coding agent transcripts</li>
              <li>Unrelated repository source code</li>
              <li>API keys, tokens, or credentials</li>
              <li>Private environment variables</li>
            </ul>
          </div>
        </div>
      </div>
    ),
  },

  'build/prerequisites': {
    title: 'Prerequisites & Environment',
    category: '03 / Build',
    onThisPage: [
      { id: 'runtimes', title: 'Supported Runtimes' },
      { id: 'os-support', title: 'Operating Systems' },
      { id: 'mcp-hosts', title: 'Supported MCP Hosts' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis is designed to install with zero friction on modern developer environments.
        </p>

        <h2 id="runtimes" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Supported Runtimes
        </h2>
        <ul className="list-disc list-inside text-xs leading-relaxed text-stone-700 space-y-2 pl-2">
          <li><strong>Node.js:</strong> Version 18.0.0 or newer (npm launcher and npx commands).</li>
          <li><strong>Python:</strong> Version 3.11 or newer (powers the core policy, Sibyl client, and MCP stdio server).</li>
        </ul>
        <Callout type="info" title="Automatic Python Bootstrap">
          The npm package automatically provisions a private per-user virtual environment on first launch when Python 3.11+ is detected on the system PATH.
        </Callout>

        <h2 id="os-support" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Operating Systems
        </h2>
        <ul className="list-disc list-inside text-xs leading-relaxed text-stone-700 space-y-1 pl-2">
          <li><strong>Linux & WSL2:</strong> Fully verified (108/108 test suite passed).</li>
          <li><strong>Windows 10/11:</strong> Fully verified (108/108 test suite passed).</li>
          <li><strong>macOS:</strong> Unverified; POSIX paths supported but not claimed in release evidence.</li>
        </ul>

        <h2 id="mcp-hosts" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Supported MCP Hosts
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Claude Code, Cursor, Codex, Antigravity, and Gemini CLI. Generic MCP hosts can be configured via standard stdio JSON.
        </p>
      </div>
    ),
  },

  'build/skepis-init': {
    title: 'Project Initialization (`skepis init`)',
    category: '03 / Build',
    onThisPage: [
      { id: 'interactive-init', title: 'Interactive Flow' },
      { id: 'noninteractive-init', title: 'CI Noninteractive Mode' },
      { id: 'config-schema', title: 'skepis.json Schema' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          <code className="font-mono text-stone-900 font-semibold">skepis init</code> creates the canonical project configuration and verifies that Sibyl Memory is available.
        </p>

        <h2 id="interactive-init" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Interactive Flow
        </h2>
        <CodeBlock code="npx skepis init" language="bash" />
        <p className="text-xs text-stone-600">
          Output:
        </p>
        <div className="p-4 rounded bg-[#1e232a] text-stone-200 font-mono text-xs leading-relaxed">
          <pre>{`Skepis ready.

Benchmark: payments-regression
Agent: payments-agent
Tasks: 18
Protected resources: 3 patterns
Policy: EXCLUDE
Memory: available

Next: skepis connect`}</pre>
        </div>

        <h2 id="noninteractive-init" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          CI Noninteractive Mode
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Provide all arguments directly to avoid terminal prompts:
        </p>
        <CodeBlock
          code={`npx skepis init \\
  --root . \\
  --benchmark-id payments-regression \\
  --evaluation-subject payments-agent \\
  --task refund-idempotency \\
  --task oauth-refresh-expiry \\
  --protected refund-idempotency=private/answers/refund.yaml \\
  --evaluator-command "python evaluate.py"`}
          language="bash"
        />

        <h2 id="config-schema" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          skepis.json Configuration File
        </h2>
        <CodeBlock
          code={`{
  "schema_version": "1.0",
  "benchmark_id": "payments-regression",
  "evaluation_subject": "payments-agent",
  "policy": "EXCLUDE",
  "tasks": [
    "refund-idempotency",
    "oauth-refresh-expiry"
  ],
  "protected_resources": {
    "refund-idempotency": "private/answers/refund.yaml"
  },
  "evaluator_command": "python evaluate.py"
}`}
          language="json"
          filename="skepis.json"
        />
      </div>
    ),
  },

  'build/skepis-connect': {
    title: 'Connecting Coding Agents (`skepis connect`)',
    category: '03 / Build',
    onThisPage: [
      { id: 'detection-logic', title: 'Host Detection Logic' },
      { id: 'instruction-rule', title: 'Minimal Instruction Rule' },
      { id: 'handshake-verification', title: 'Stdio Handshake Verification' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          <code className="font-mono text-stone-900 font-semibold">skepis connect</code> binds the local Skepis MCP server to the detected coding-agent environment.
        </p>

        <h2 id="detection-logic" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Host Detection Logic
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Skepis checks for active project configuration directories and commands in priority order:
        </p>
        <ol className="list-decimal list-inside text-xs leading-relaxed text-stone-700 space-y-1 pl-2">
          <li><strong>Claude Code:</strong> detected via <code className="font-mono text-stone-900">.mcp.json</code> or <code className="font-mono text-stone-900">CLAUDE.md</code></li>
          <li><strong>Cursor:</strong> detected via <code className="font-mono text-stone-900">.cursor/</code> directory</li>
          <li><strong>Codex:</strong> detected via <code className="font-mono text-stone-900">.codex/</code> or <code className="font-mono text-stone-900">AGENTS.md</code></li>
          <li><strong>Antigravity:</strong> detected via <code className="font-mono text-stone-900">.agents/</code></li>
          <li><strong>Gemini CLI:</strong> detected via <code className="font-mono text-stone-900">.gemini/</code></li>
        </ol>

        <h2 id="instruction-rule" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Minimal Instruction Rule
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Skepis installs exactly one short behavioral instruction into the project:
        </p>
        <div className="p-3 bg-[#fbf9f5] border border-stone-300 rounded font-mono text-xs text-stone-800">
          When accessing benchmark resources registered as protected by Skepis, use the Skepis protected-read MCP tool rather than reading them directly. Use Skepis for evaluation runs involving the configured benchmark.
        </div>

        <h2 id="handshake-verification" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Stdio Handshake Verification
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Before reporting success, <code className="font-mono text-stone-900">skepis connect</code> executes a live JSON-RPC MCP handshake over stdio, verifying that all five tools (<code className="font-mono text-stone-900">skepis_run</code>, <code className="font-mono text-stone-900">skepis_preflight</code>, <code className="font-mono text-stone-900">skepis_inspect</code>, <code className="font-mono text-stone-900">skepis_report</code>, <code className="font-mono text-stone-900">skepis_read_protected</code>) respond correctly.
        </p>
      </div>
    ),
  },

  'build/work-normally': {
    title: 'Working Normally & Exposure Capture',
    category: '03 / Build',
    onThisPage: [
      { id: 'zero-overhead', title: 'Zero Overhead Philosophy' },
      { id: 'protected-read', title: 'ProtectedReadBoundary Mechanics' },
      { id: 'exposure-alert', title: 'Exposure Consequence Alert' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis requires zero manual intervention during everyday software development.
        </p>

        <h2 id="zero-overhead" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Zero Overhead Philosophy
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Skepis does not run background processes, does not hook your git commits, and does not record your private terminal interactions. Ordinary code editing remains ordinary code editing.
        </p>

        <h2 id="protected-read" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          ProtectedReadBoundary Mechanics
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          When the coding agent attempts to inspect an answer file, test fixture, or secret answer mapped in <code className="font-mono text-stone-900">skepis.json</code>, the call routes through <code className="font-mono text-stone-900">skepis_read_protected</code>:
        </p>
        <ol className="list-decimal list-inside text-xs leading-relaxed text-stone-700 space-y-1.5 pl-2">
          <li>The boundary checks that the path is registered and exists within the repository root.</li>
          <li>The file contents are read into memory.</li>
          <li>Exposure is permanently recorded in Sibyl Memory for that task ID and evaluation subject.</li>
          <li>The content is returned to the agent with an exposure warning.</li>
        </ol>

        <h2 id="exposure-alert" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Exposure Consequence Alert
        </h2>
        <div className="p-4 rounded bg-[#1e232a] text-amber-300 font-mono text-xs">
          Skepis: oauth-refresh-expiry was exposed.<br />
          It will not count as clean evaluation evidence.
        </div>
      </div>
    ),
  },

  'build/skepis-eval': {
    title: 'Running Policy-Gated Evaluation (`skepis eval`)',
    category: '03 / Build',
    onThisPage: [
      { id: 'eval-flow', title: 'The Evaluation Sequence' },
      { id: 'terminal-output', title: 'Standard Evaluation Output' },
      { id: 'evaluator-env', title: 'Environment Variables' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          <code className="font-mono text-stone-900 font-semibold">skepis eval</code> is the central human and CI evaluation command.
        </p>

        <h2 id="eval-flow" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          The Evaluation Sequence
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          When you execute <code className="font-mono text-stone-900">skepis eval</code>:
        </p>
        <ol className="list-decimal list-inside text-xs leading-relaxed text-stone-700 space-y-1.5 pl-2">
          <li><strong>Load State:</strong> Reads canonical exposure state from Sibyl Memory.</li>
          <li><strong>Classify Tasks:</strong> Partitions requested tasks into CLEAN, EXPOSED, and UNKNOWN sets.</li>
          <li><strong>Apply Policy:</strong> Filters tasks according to policy (<code className="font-mono text-stone-900">EXCLUDE</code>, <code className="font-mono text-stone-900">FLAG</code>, <code className="font-mono text-stone-900">STRICT</code>).</li>
          <li><strong>Run Evaluator:</strong> Executes <code className="font-mono text-stone-900">evaluator_command</code> with selected task IDs.</li>
          <li><strong>Build Report:</strong> Generates canonical terminal and portable JSON reports.</li>
        </ol>

        <h2 id="terminal-output" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Standard Evaluation Output
        </h2>
        <CodeBlock code="skepis eval" language="bash" />
        <div className="p-4 rounded bg-[#1e232a] text-stone-200 font-mono text-xs leading-relaxed">
          <pre>{`Skepis Evaluation

payments-agent × payments-regression

18 requested
16 clean
2 previously exposed

Evaluating 16 clean tasks...

Passed: 14 / 16
Clean score: 87.5%
2 exposed tasks excluded

Clean claim: permitted`}</pre>
        </div>

        <h2 id="evaluator-env" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Environment Variables Passed to Evaluator
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Skepis runs the evaluator without a subshell, supplying:
        </p>
        <ul className="list-disc list-inside text-xs leading-relaxed text-stone-700 space-y-1 pl-2">
          <li><code className="font-mono text-stone-900 font-semibold">SKEPIS_TASK_IDS</code>: JSON array of permitted task IDs.</li>
          <li><code className="font-mono text-stone-900 font-semibold">SKEPIS_EVALUATION_REQUEST</code>: Path to full request JSON containing benchmark ID, run ID, and policy.</li>
        </ul>
      </div>
    ),
  },

  'build/skepis-inspect': {
    title: 'Safe Provenance Inspection (`skepis inspect`)',
    category: '03 / Build',
    onThisPage: [
      { id: 'why-inspect', title: 'Why Was My Task Excluded?' },
      { id: 'safe-redaction', title: 'Safe Redaction Guarantees' },
      { id: 'json-inspect', title: 'Structured JSON Provenance' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          <code className="font-mono text-stone-900 font-semibold">skepis inspect</code> is a read-only debugging tool that explains task exclusions without altering journal state.
        </p>

        <h2 id="why-inspect" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Why Was My Task Excluded?
        </h2>
        <CodeBlock code="skepis inspect" language="bash" />
        <div className="p-4 rounded bg-[#1e232a] text-stone-200 font-mono text-xs leading-relaxed">
          <pre>{`Why didn't these tasks count?

oauth-refresh-expiry
EXPOSED
Protected material accessed Aug 31 14:22:01
Resource: private/answers/refund.yaml

inventory-race-condition
UNKNOWN
Monitoring history incomplete`}</pre>
        </div>

        <h2 id="safe-redaction" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Safe Redaction Guarantees
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          `skepis inspect` filters out all sensitive information:
        </p>
        <ul className="list-disc list-inside text-xs leading-relaxed text-stone-700 space-y-1 pl-2">
          <li>Protected answer bodies are never printed.</li>
          <li>Raw evaluator debug traces and secrets are redacted.</li>
          <li>Unrelated tenant and benchmark tasks are filtered out.</li>
        </ul>

        <h2 id="json-inspect" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Structured JSON Provenance
        </h2>
        <CodeBlock code="skepis inspect --json" language="bash" />
      </div>
    ),
  },

  'integrate/mcp-clients': {
    title: 'Supported MCP Clients Matrix',
    category: '04 / Integrate',
    onThisPage: [
      { id: 'interactive-matrix', title: 'Interactive Client Config' },
      { id: 'supported-hosts', title: 'Supported Host Table' },
      { id: 'manual-fallback', title: 'Manual Configuration' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis connects natively to major AI coding agents through project-scoped configurations.
        </p>

        <h2 id="interactive-matrix" className="font-heading text-lg font-bold text-stone-900 pt-2">
          Interactive Client Config Viewer
        </h2>
        <p className="text-xs text-stone-600">
          Select an agent below to view its verified configuration format and installed rule:
        </p>
        <McpConfigViewer />

        <h2 id="supported-hosts" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Supported Host Table
        </h2>
        <div className="overflow-x-auto my-3">
          <table className="w-full text-xs font-body border border-stone-200 rounded-lg">
            <thead className="bg-[#f4f1eb] text-stone-900 font-semibold border-b border-stone-200 text-left">
              <tr>
                <th className="p-2.5">Agent Host</th>
                <th className="p-2.5">Config Location</th>
                <th className="p-2.5">Format</th>
                <th className="p-2.5">Instruction File</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-200 text-stone-700">
              <tr>
                <td className="p-2.5 font-semibold">Claude Code</td>
                <td className="p-2.5 font-mono">.mcp.json</td>
                <td className="p-2.5">JSON</td>
                <td className="p-2.5 font-mono">CLAUDE.md</td>
              </tr>
              <tr>
                <td className="p-2.5 font-semibold">Cursor</td>
                <td className="p-2.5 font-mono">.cursor/mcp.json</td>
                <td className="p-2.5">JSON</td>
                <td className="p-2.5 font-mono">.cursor/rules/skepis.mdc</td>
              </tr>
              <tr>
                <td className="p-2.5 font-semibold">Codex</td>
                <td className="p-2.5 font-mono">.codex/config.toml</td>
                <td className="p-2.5">TOML</td>
                <td className="p-2.5 font-mono">AGENTS.md</td>
              </tr>
              <tr>
                <td className="p-2.5 font-semibold">Antigravity</td>
                <td className="p-2.5 font-mono">.agents/mcp_config.json</td>
                <td className="p-2.5">JSON</td>
                <td className="p-2.5 font-mono">.agents/rules/skepis.md</td>
              </tr>
              <tr>
                <td className="p-2.5 font-semibold">Gemini CLI</td>
                <td className="p-2.5 font-mono">.gemini/settings.json</td>
                <td className="p-2.5">JSON</td>
                <td className="p-2.5 font-mono">GEMINI.md</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h2 id="manual-fallback" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Manual Configuration Fallback
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          For unsupported or custom MCP clients, launch the stdio server directly:
        </p>
        <CodeBlock code="npx -y skepis-mcp --config skepis.json" language="bash" />
      </div>
    ),
  },

  'integrate/evaluator-contract': {
    title: 'Evaluator Command Contract',
    category: '04 / Integrate',
    onThisPage: [
      { id: 'subshell-safety', title: 'Execution Protocol' },
      { id: 'request-payload', title: 'Evaluation Request Payload' },
      { id: 'response-schema', title: 'Evaluator Output Schema' },
      { id: 'sample-evaluator', title: 'Example Python Evaluator' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          The evaluator is an arbitrary program supplied by the developer that scores benchmark tasks. Skepis does not replace the evaluator or provide model scoring itself.
        </p>

        <h2 id="subshell-safety" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Execution Protocol
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Skepis invokes the evaluator directly via <code className="font-mono text-stone-900">subprocess.run</code> without a shell, avoiding shell-injection vulnerabilities. The evaluator must:
        </p>
        <ol className="list-decimal list-inside text-xs leading-relaxed text-stone-700 space-y-1.5 pl-2">
          <li>Read task IDs from the <code className="font-mono text-stone-900">SKEPIS_TASK_IDS</code> environment variable or the file named by <code className="font-mono text-stone-900">SKEPIS_EVALUATION_REQUEST</code>.</li>
          <li>Evaluate <em>only</em> those selected tasks.</li>
          <li>Write a single JSON object to <code className="font-mono text-stone-900">stdout</code> and exit with code 0.</li>
        </ol>

        <h2 id="request-payload" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Evaluation Request Payload
        </h2>
        <CodeBlock
          code={`{
  "benchmark_id": "payments-regression",
  "evaluation_subject": "payments-agent",
  "run_id": "eval_8f319a2b",
  "policy": "EXCLUDE",
  "task_ids": [
    "refund-idempotency",
    "webhook-signature"
  ]
}`}
          language="json"
          filename="SKEPIS_EVALUATION_REQUEST file content"
        />

        <h2 id="response-schema" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Evaluator Output Schema
        </h2>
        <CodeBlock
          code={`{
  "evaluated_tasks": [
    "refund-idempotency",
    "webhook-signature"
  ],
  "passed_tasks": [
    "refund-idempotency"
  ],
  "score": 0.5,
  "metrics": {
    "execution_time_ms": 1240
  }
}`}
          language="json"
          filename="stdout JSON response"
        />

        <h2 id="sample-evaluator" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Example Python Evaluator
        </h2>
        <CodeBlock
          code={`import os, json, sys

def main():
    task_ids = json.loads(os.environ.get("SKEPIS_TASK_IDS", "[]"))
    passed = []
    for tid in task_ids:
        # Run test for task...
        if test_task(tid):
            passed.append(tid)

    result = {
        "evaluated_tasks": task_ids,
        "passed_tasks": passed,
        "score": len(passed) / len(task_ids) if task_ids else 0.0
    }
    print(json.dumps(result))

def test_task(tid):
    return True

if __name__ == "__main__":
    main()`}
          language="python"
          filename="evaluate.py"
        />
      </div>
    ),
  },

  'integrate/ci-cd': {
    title: 'CI & Headless Pipelines',
    category: '04 / Integrate',
    onThisPage: [
      { id: 'github-actions', title: 'GitHub Actions Workflow' },
      { id: 'exit-codes', title: 'CI Exit Codes' },
      { id: 'report-artifact', title: 'Archiving Clean Claims' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis can gate pull requests and automated benchmarks in continuous integration pipelines.
        </p>

        <h2 id="github-actions" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          GitHub Actions Workflow
        </h2>
        <CodeBlock
          code={`name: Benchmark Integrity

on:
  pull_request:
    branches: [main]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Run Skepis Evaluation
        run: |
          npx skepis eval --json > evaluation-report.json

      - name: Upload Clean Report
        uses: actions/upload-artifact@v4
        with:
          name: skepis-evaluation-report
          path: evaluation-report.json`}
          language="yaml"
          filename=".github/workflows/eval.yml"
        />

        <h2 id="exit-codes" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          CI Exit Codes
        </h2>
        <ul className="list-disc list-inside text-xs leading-relaxed text-stone-700 space-y-1.5 pl-2">
          <li><strong>0:</strong> Evaluation completed successfully; clean claim permitted.</li>
          <li><strong>1:</strong> Policy violation, strict mode failure, or clean claim denied.</li>
          <li><strong>2:</strong> Configuration syntax error or missing Sibyl store.</li>
        </ul>
      </div>
    ),
  },

  'reference/cli-commands': {
    title: 'CLI Command Reference',
    category: '05 / Reference',
    onThisPage: [
      { id: 'command-table', title: 'Commands Overview' },
      { id: 'flags-table', title: 'Global Flags & Options' },
      { id: 'env-vars', title: 'Environment Variables' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Complete reference for all CLI commands, flags, and environment variables.
        </p>

        <h2 id="command-table" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Commands Overview
        </h2>
        <div className="overflow-x-auto my-3">
          <table className="w-full text-xs font-body border border-stone-200 rounded-lg">
            <thead className="bg-[#f4f1eb] text-stone-900 font-semibold border-b border-stone-200 text-left">
              <tr>
                <th className="p-2.5">Command</th>
                <th className="p-2.5">Arguments</th>
                <th className="p-2.5">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-200 text-stone-700 font-mono">
              <tr>
                <td className="p-2.5 font-bold text-emerald-800">skepis init</td>
                <td className="p-2.5 text-stone-600">[--root &lt;path&gt;]</td>
                <td className="p-2.5 font-body">Initialize benchmark configuration and check Sibyl store.</td>
              </tr>
              <tr>
                <td className="p-2.5 font-bold text-emerald-800">skepis connect</td>
                <td className="p-2.5 text-stone-600">[--client &lt;name&gt;]</td>
                <td className="p-2.5 font-body">Auto-detect and configure project MCP coding agent.</td>
              </tr>
              <tr>
                <td className="p-2.5 font-bold text-emerald-800">skepis eval</td>
                <td className="p-2.5 text-stone-600">[--json] [--policy &lt;mode&gt;]</td>
                <td className="p-2.5 font-body">Execute evaluation through the contamination policy gate.</td>
              </tr>
              <tr>
                <td className="p-2.5 font-bold text-emerald-800">skepis inspect</td>
                <td className="p-2.5 text-stone-600">[--json] [--task &lt;id&gt;]</td>
                <td className="p-2.5 font-body">Read-only explanation of task eligibility and exclusions.</td>
              </tr>
              <tr>
                <td className="p-2.5 font-bold text-emerald-800">skepis report</td>
                <td className="p-2.5 text-stone-600">[--format md|json] [--output &lt;path&gt;]</td>
                <td className="p-2.5 font-body">Retrieve latest scoped evaluation report.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h2 id="env-vars" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Environment Variables
        </h2>
        <ul className="list-disc list-inside text-xs leading-relaxed text-stone-700 space-y-1.5 pl-2 font-mono">
          <li><strong>SKEPIS_CONFIG_PATH:</strong> Explicit path to skepis.json.</li>
          <li><strong>SKEPIS_POLICY:</strong> Override default policy (EXCLUDE, FLAG, STRICT).</li>
          <li><strong>SKEPIS_TASK_IDS:</strong> JSON array passed to evaluator subprocess.</li>
        </ul>
      </div>
    ),
  },

  'reference/mcp-tools': {
    title: 'MCP 5-Tool Reference',
    category: '05 / Reference',
    onThisPage: [
      { id: 'skepis-run', title: '1. skepis_run' },
      { id: 'skepis-preflight', title: '2. skepis_preflight' },
      { id: 'skepis-inspect-tool', title: '3. skepis_inspect' },
      { id: 'skepis-report-tool', title: '4. skepis_report' },
      { id: 'skepis-read-protected', title: '5. skepis_read_protected' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          The Skepis MCP server exposes exactly five tools over stdio JSON-RPC:
        </p>

        <h2 id="skepis-run" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          1. <code className="font-mono text-emerald-800">skepis_run</code>
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          <strong>Role:</strong> Runs the configured evaluator through the policy gate.<br />
          <strong>State Change:</strong> Journals evaluation events into COLD store.<br />
          <strong>Guarantees:</strong> Uses only the evaluator command from project config; refuses caller-supplied evaluation scripts.
        </p>

        <h2 id="skepis-preflight" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          2. <code className="font-mono text-emerald-800">skepis_preflight</code>
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          <strong>Role:</strong> Classifies requested tasks before evaluation.<br />
          <strong>State Change:</strong> Read-only, idempotent.<br />
          <strong>Returns:</strong> Partition counts for CLEAN, EXPOSED, and UNKNOWN tasks.
        </p>

        <h2 id="skepis-inspect-tool" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          3. <code className="font-mono text-emerald-800">skepis_inspect</code>
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          <strong>Role:</strong> Explains task eligibility with safe, redacted provenance.<br />
          <strong>State Change:</strong> Read-only, idempotent.<br />
          <strong>Returns:</strong> Timestamps, resource paths, and policy exclusion reasons.
        </p>

        <h2 id="skepis-report-tool" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          4. <code className="font-mono text-emerald-800">skepis_report</code>
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          <strong>Role:</strong> Retrieves the latest portable evaluation report.<br />
          <strong>State Change:</strong> Read-only.<br />
          <strong>Formats:</strong> JSON or Markdown.
        </p>

        <h2 id="skepis-read-protected" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          5. <code className="font-mono text-emerald-800">skepis_read_protected</code>
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          <strong>Role:</strong> Reads a registered protected file through the capture boundary.<br />
          <strong>State Change:</strong> Records objective exposure in Sibyl Memory.<br />
          <strong>Invariant:</strong> Exposure is written ONLY after a successful file read.
        </p>
      </div>
    ),
  },

  'reference/error-reference': {
    title: 'Error & Status Reference',
    category: '05 / Reference',
    onThisPage: [
      { id: 'status-codes', title: 'Task Status Values' },
      { id: 'error-codes', title: 'Error Codes & Remedies' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Complete glossary of task statuses and error codes emitted by Skepis.
        </p>

        <h2 id="status-codes" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Task Status Values
        </h2>
        <div className="space-y-2.5 text-xs">
          <div className="p-3 bg-white border border-stone-200 rounded">
            <strong className="font-mono text-emerald-700">CLEAN (UNSEEN):</strong> The task has no recorded exposure in Sibyl Memory and full monitoring coverage is intact.
          </div>
          <div className="p-3 bg-white border border-stone-200 rounded">
            <strong className="font-mono text-amber-700">EXPOSED:</strong> Objective evidence shows the agent read the protected resource for this task in an earlier session.
          </div>
          <div className="p-3 bg-white border border-stone-200 rounded">
            <strong className="font-mono text-red-700">UNKNOWN:</strong> Monitoring history was incomplete or Sibyl store was unavailable. Under fail-closed rules, blocks clean claims.
          </div>
        </div>

        <h2 id="error-codes" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Common Error Codes & Remedies
        </h2>
        <div className="space-y-3 text-xs">
          <div className="p-3 bg-[#fbf9f5] border border-stone-300 rounded space-y-1">
            <div className="font-mono font-bold text-stone-900">E001: SIBYL_STORE_UNAVAILABLE</div>
            <p className="text-stone-600">The Sibyl persistence database could not be reached. Fix: verify disk permissions or check Sibyl client configuration.</p>
          </div>
          <div className="p-3 bg-[#fbf9f5] border border-stone-300 rounded space-y-1">
            <div className="font-mono font-bold text-stone-900">E002: TASK_NOT_REGISTERED</div>
            <p className="text-stone-600">The evaluator returned a task ID that was not registered in skepis.json. Fix: ensure task IDs match exactly.</p>
          </div>
          <div className="p-3 bg-[#fbf9f5] border border-stone-300 rounded space-y-1">
            <div className="font-mono font-bold text-stone-900">E003: EVALUATOR_FAILED</div>
            <p className="text-stone-600">The evaluator subprocess crashed or exited with non-zero code. Fix: inspect evaluator stdout/stderr logs.</p>
          </div>
        </div>
      </div>
    ),
  },

  'production/releases': {
    title: 'Published Packages & Releases',
    category: '06 / Production',
    onThisPage: [
      { id: 'npm-package', title: 'npm Distribution' },
      { id: 'python-package', title: 'Python Package' },
      { id: 'release-history', title: 'Release Changelog' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis is distributed publicly via npm and Python packaging.
        </p>

        <h2 id="npm-package" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          npm Distribution (<code className="font-mono text-stone-900">skepis@0.1.4</code>)
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          The public npm package provides instant CLI access:
        </p>
        <CodeBlock code="npm install -g skepis" language="bash" />
        <p className="text-xs text-stone-600">Or invoke directly via npx:</p>
        <CodeBlock code="npx skepis --help" language="bash" />

        <h2 id="python-package" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Python Native Package
        </h2>
        <CodeBlock code="pip install -e ." language="bash" />

        <h2 id="release-history" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Release Changelog
        </h2>
        <div className="space-y-2 text-xs">
          <div className="p-3 bg-white border border-stone-200 rounded">
            <strong>v0.1.4 (Current):</strong> Full 5-adapter matrix (Claude Code, Cursor, Codex, Antigravity, Gemini CLI), portable markdown/json reporting, and fresh-session persistence verification.
          </div>
          <div className="p-3 bg-white border border-stone-200 rounded">
            <strong>v0.1.3:</strong> Thin npm launcher distribution with private per-user virtualenv bootstrap.
          </div>
          <div className="p-3 bg-white border border-stone-200 rounded">
            <strong>v0.1.2:</strong> MCP stdio server with five tools and safe provenance projection.
          </div>
        </div>
      </div>
    ),
  },

  'production/verification-matrix': {
    title: 'Verification Matrix & Test Proofs',
    category: '06 / Production',
    onThisPage: [
      { id: 'test-evidence', title: 'Verified Test Suites' },
      { id: 'adapter-proofs', title: '5-Adapter Configuration Checks' },
      { id: 'fresh-session-proof', title: 'Fresh-Session Recall Proof' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Every release is backed by automated test suites executed across Windows and Linux.
        </p>

        <h2 id="test-evidence" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Verified Test Suites
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-body">
          <div className="p-4 bg-[#fbf9f5] border border-stone-200 rounded-lg">
            <h4 className="font-bold text-stone-900 text-sm">WSL2 / Linux Suite</h4>
            <div className="text-2xl font-bold font-mono text-emerald-800 my-1">108 / 108 Passed</div>
            <p className="text-stone-600 text-[11px]">Full integration coverage: MCP stdio handshake, capture, policy, evaluator, deletion, and scope proofs.</p>
          </div>
          <div className="p-4 bg-[#fbf9f5] border border-stone-200 rounded-lg">
            <h4 className="font-bold text-stone-900 text-sm">Windows Native Suite</h4>
            <div className="text-2xl font-bold font-mono text-emerald-800 my-1">108 / 108 Passed</div>
            <p className="text-stone-600 text-[11px]">Clean npm journey, Claude Code project detection, fresh evaluation processes, and inspect output.</p>
          </div>
        </div>

        <h2 id="adapter-proofs" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          5-Adapter Configuration Checks
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Tested against project-local configuration files for Claude Code (<code className="font-mono text-stone-900">.mcp.json</code>), Cursor (<code className="font-mono text-stone-900">.cursor/mcp.json</code>), Codex (<code className="font-mono text-stone-900">.codex/config.toml</code>), Antigravity (<code className="font-mono text-stone-900">.agents/mcp_config.json</code>), and Gemini CLI (<code className="font-mono text-stone-900">.gemini/settings.json</code>). These checks do not prove observation of every host-application session.
        </p>

        <h2 id="fresh-session-proof" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Fresh-Session Recall Proof
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Tests that when Session A executes a protected read, the process ends, and Session B starts as an unrelated process, the exposure is recalled from Sibyl.
        </p>
      </div>
    ),
  },

  'production/portable-reports': {
    title: 'Canonical Portable Reports',
    category: '06 / Production',
    onThisPage: [
      { id: 'json-report', title: 'Canonical JSON Format' },
      { id: 'markdown-report', title: 'Rendered Markdown Format' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis produces portable clean-evaluation reports that make task eligibility, policy decisions, evaluator results, and monitoring coverage explicit. The report is derived from canonical state and does not prove observation outside the supported boundary.
        </p>

        <h2 id="json-report" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Canonical JSON Format
        </h2>
        <CodeBlock
          code={`{
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
  "score": 0.875,
  "clean_claim_permitted": true,
  "monitoring_coverage": {
    "protected_reads": "COMPLETE",
    "generic_shell": "INCOMPLETE_MONITORING",
    "sibyl_memory": "AVAILABLE"
  }
}`}
          language="json"
          filename="skepis-report.json"
        />

        <h2 id="markdown-report" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Rendered Markdown Format
        </h2>
        <CodeBlock
          code={`# Skepis Clean Evaluation Report

**Benchmark:** payments-regression\\
**Evaluation Subject:** payments-agent\\
**Run ID:** eval_8f319a2b\\
**Date:** 2026-09-02 11:42:00 UTC\\

## Task Eligibility
- **Requested:** 18
- **Clean:** 16
- **Exposed:** 2
- **Unknown:** 0

## Evaluation Result
- **Passed:** 14 / 16
- **Clean Score:** 87.5%
- **Clean Claim:** PERMITTED`}
          language="markdown"
          filename="skepis-report.md"
        />
      </div>
    ),
  },

  'security/trust-model': {
    title: 'Trust & Security Model',
    category: '07 / Security',
    onThisPage: [
      { id: 'local-first', title: 'Local-First Architecture' },
      { id: 'isolation', title: 'Tenant & Benchmark Isolation' },
      { id: 'evaluator-isolation', title: 'Subprocess Isolation' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis is architected from the ground up for strict local-first security.
        </p>

        <h2 id="local-first" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Local-First Architecture
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Skepis transmits zero telemetry, benchmark code, or evaluation results to external third parties. All states reside on your machine in local Sibyl Memory.
        </p>

        <h2 id="isolation" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Tenant & Benchmark Isolation
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          State written for benchmark A cannot leak into benchmark B. Evaluations for subject X cannot observe contamination state for subject Y.
        </p>

        <h2 id="evaluator-isolation" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Subprocess Isolation
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Evaluator commands execute directly without a shell, reducing shell-injection risk. Evaluator code and benchmark inputs remain project-owned code and data.
        </p>
      </div>
    ),
  },

  'security/privacy-boundary': {
    title: 'Privacy & Data Boundary',
    category: '07 / Security',
    onThisPage: [
      { id: 'no-secret-persistence', title: 'No Secret Persistence' },
      { id: 'provenance-redaction', title: 'Provenance Redaction' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Skepis ensures proprietary evaluation secrets remain private.
        </p>

        <h2 id="no-secret-persistence" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          No Secret Persistence
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          When an agent reads a protected answer file through <code className="font-mono text-stone-900">skepis_read_protected</code>, the file body is streamed to the agent and discarded. Only the task identifier, path name, and timestamp are saved to Sibyl Memory.
        </p>

        <h2 id="provenance-redaction" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Provenance Redaction
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          Reports and inspection outputs scrub sensitive raw evaluator dumps, so public benchmarks can share clean proof without leaking proprietary test suites.
        </p>
      </div>
    ),
  },

  'security/failure-behavior': {
    title: 'Failure Modes & Fail-Closed Invariant',
    category: '07 / Security',
    onThisPage: [
      { id: 'fail-closed', title: 'Fail-Closed Invariant' },
      { id: 'missing-memory', title: 'Memory Loss Behavior' },
      { id: 'malformed-eval', title: 'Evaluator Misbehavior' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          When errors occur, Skepis fails closed to protect benchmark credibility.
        </p>

        <h2 id="fail-closed" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Fail-Closed Invariant
        </h2>
        <Callout type="warning" title="Incomplete History = Denied Clean Claim">
          If monitoring history is interrupted, corrupted, or unavailable, Skepis refuses to issue a clean evaluation claim.
        </Callout>

        <h2 id="missing-memory" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Memory Loss Behavior
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          If the Sibyl database file is deleted, tasks map to <code className="font-mono text-stone-900 font-semibold">UNKNOWN</code> rather than assuming they were never exposed.
        </p>

        <h2 id="malformed-eval" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Evaluator Misbehavior
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          If an evaluator outputs a task ID that was not in the policy-selected set, Skepis rejects the entire result as untrusted.
        </p>
      </div>
    ),
  },

  'help/troubleshooting': {
    title: 'Troubleshooting & Diagnostics',
    category: '08 / Help',
    onThisPage: [
      { id: 'mcp-not-found', title: 'MCP Server Not Reachable' },
      { id: 'python-mismatch', title: 'Python Version Conflicts' },
      { id: 'evaluator-hangs', title: 'Evaluator Subprocess Timeout' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Step-by-step diagnostics for common setup issues.
        </p>

        <h2 id="mcp-not-found" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          1. MCP Server Not Reachable
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          <strong>Symptom:</strong> Coding agent reports &ldquo;tool skepis_read_protected not found&rdquo;.<br />
          <strong>Fix:</strong> Run <code className="font-mono text-stone-900 font-semibold">skepis connect</code> to verify stdio handshake. Ensure the project root contains <code className="font-mono text-stone-900">skepis.json</code>.
        </p>

        <h2 id="python-mismatch" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          2. Python Version Conflicts
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          <strong>Symptom:</strong> <code className="font-mono text-stone-900">skepis init</code> fails with Python import errors.<br />
          <strong>Fix:</strong> Skepis requires Python 3.11+. Verify with <code className="font-mono text-stone-900">python --version</code> and install 3.11 or newer if necessary.
        </p>

        <h2 id="evaluator-hangs" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          3. Evaluator Subprocess Timeout
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          <strong>Symptom:</strong> <code className="font-mono text-stone-900">skepis eval</code> hangs indefinitely.<br />
          <strong>Fix:</strong> Ensure your evaluator command does not block on interactive stdin. Check that it parses <code className="font-mono text-stone-900">SKEPIS_TASK_IDS</code> non-interactively.
        </p>
      </div>
    ),
  },

  'help/faq': {
    title: 'Frequently Asked Questions',
    category: '08 / Help',
    onThisPage: [
      { id: 'faq-logger', title: 'Is Skepis an evaluation logger?' },
      { id: 'faq-reset', title: 'Can an exposed task become clean again?' },
      { id: 'faq-mcp-only', title: 'Does Skepis require MCP?' },
      { id: 'faq-daemon', title: 'Does Skepis run in the background?' },
    ],
    content: (
      <div className="space-y-6">
        <p className="text-sm leading-relaxed text-stone-700">
          Common architectural and conceptual questions about Skepis.
        </p>

        <h2 id="faq-logger" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Is Skepis an evaluation logger?
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          No. An evaluation logger merely observes and prints scores. Skepis actively changes evaluation eligibility based on durable historical exposure, excluding contaminated tasks from clean scoring claims.
        </p>

        <h2 id="faq-reset" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Can an exposed task ever become clean again?
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          No. Exposure is an objective historical fact. In Skepis, exposure is monotonic. Only a benchmark policy that retires and replaces a task with a brand new unseen variant can produce a clean claim.
        </p>

        <h2 id="faq-mcp-only" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Does Skepis require MCP?
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          The human developer journey is CLI-first (<code className="font-mono text-stone-900">npx skepis init</code>, <code className="font-mono text-stone-900">skepis eval</code>). MCP is the interface adapter that connects your coding agent to the controlled capture boundary.
        </p>

        <h2 id="faq-daemon" className="font-heading text-lg font-bold text-stone-900 pt-4 border-t border-stone-200">
          Does Skepis run a daemon or background watcher?
        </h2>
        <p className="text-xs leading-relaxed text-stone-700">
          No. Skepis runs only when explicitly invoked by you or your coding agent. There are zero background daemons, watchers, or telemetry services running on your machine.
        </p>
      </div>
    ),
  },
}
