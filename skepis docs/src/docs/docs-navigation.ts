export interface DocItem {
  id: string
  title: string
  slug: string
  description: string
  badge?: string
}

export interface DocSection {
  id: string
  number: string
  title: string
  items: DocItem[]
}

export const DOCS_SECTIONS: DocSection[] = [
  {
    id: 'start',
    number: '01',
    title: 'Start',
    items: [
      {
        id: 'introduction',
        title: 'Introduction',
        slug: 'start/introduction',
        description: 'What Skepis is, why it exists, and the core invariant of evaluation integrity.',
      },
      {
        id: 'quickstart',
        title: 'Quickstart',
        slug: 'start/quickstart',
        description: 'Get from clean repository to policy-gated evaluation in 4 commands.',
        badge: 'Popular',
      },
      {
        id: 'how-it-works',
        title: 'How Skepis Works',
        slug: 'start/how-it-works',
        description: 'The causal loop: from objective exposure to durable Sibyl memory and fresh-session evaluation.',
      },
    ],
  },
  {
    id: 'concepts',
    number: '02',
    title: 'Concepts',
    items: [
      {
        id: 'core-primitives',
        title: 'Core Primitives',
        slug: 'concepts/core-primitives',
        description: 'Benchmarks, evaluation subjects, semantic task IDs, and protected resource boundaries.',
      },
      {
        id: 'state-model',
        title: 'State & Memory Model',
        slug: 'concepts/state-model',
        description: 'Why Sibyl is load-bearing: WARM canonical state vs COLD append-only journals.',
      },
      {
        id: 'policy-engine',
        title: 'Policy Engine',
        slug: 'concepts/policy-engine',
        description: 'EXCLUDE, FLAG, and STRICT policy modes and the clean claim rule.',
      },
      {
        id: 'trust-boundary',
        title: 'Trust & Data Boundary',
        slug: 'concepts/trust-boundary',
        description: 'What is monitored, what remains private, and INCOMPLETE_MONITORING boundaries.',
      },
    ],
  },
  {
    id: 'build',
    number: '03',
    title: 'Build',
    items: [
      {
        id: 'prerequisites',
        title: 'Prerequisites',
        slug: 'build/prerequisites',
        description: 'Node.js 18+, Python 3.11+, and supported development environments.',
      },
      {
        id: 'skepis-init',
        title: 'skepis init',
        slug: 'build/skepis-init',
        description: 'First-time setup: registering benchmarks, tasks, and evaluator commands.',
      },
      {
        id: 'skepis-connect',
        title: 'skepis connect',
        slug: 'build/skepis-connect',
        description: 'Zero-touch MCP client configuration with stdio handshake verification.',
      },
      {
        id: 'work-normally',
        title: 'Work Normally',
        slug: 'build/work-normally',
        description: 'Day-to-day coding: no daemon, no watcher, objective MCP capture.',
      },
      {
        id: 'skepis-eval',
        title: 'skepis eval',
        slug: 'build/skepis-eval',
        description: 'Running the evaluator through the policy gate to produce honest scores.',
      },
      {
        id: 'skepis-inspect',
        title: 'skepis inspect',
        slug: 'build/skepis-inspect',
        description: 'Explaining exclusions and viewing safe, redacted provenance.',
      },
    ],
  },
  {
    id: 'integrate',
    number: '04',
    title: 'Integrate',
    items: [
      {
        id: 'mcp-clients',
        title: 'Supported MCP Clients',
        slug: 'integrate/mcp-clients',
        description: 'Claude Code, Cursor, Codex, Antigravity, Gemini CLI, and manual configuration.',
      },
      {
        id: 'evaluator-contract',
        title: 'Evaluator Contract',
        slug: 'integrate/evaluator-contract',
        description: 'The JSON protocol between Skepis and developer-provided test scripts.',
      },
      {
        id: 'ci-cd',
        title: 'CI & Headless Pipelines',
        slug: 'integrate/ci-cd',
        description: 'Non-interactive init, automated eval runs, and exit code handling in CI.',
      },
    ],
  },
  {
    id: 'reference',
    number: '05',
    title: 'Reference',
    items: [
      {
        id: 'cli-commands',
        title: 'CLI Command Reference',
        slug: 'reference/cli-commands',
        description: 'Complete documentation of commands, flags, arguments, and environment variables.',
      },
      {
        id: 'mcp-tools',
        title: 'MCP 5-Tool Reference',
        slug: 'reference/mcp-tools',
        description: 'skepis_run, skepis_preflight, skepis_inspect, skepis_report, and skepis_read_protected.',
      },
      {
        id: 'error-reference',
        title: 'Error & Status Reference',
        slug: 'reference/error-reference',
        description: 'UNKNOWN, UNAVAILABLE, INCOMPLETE_MONITORING, and fail-closed behaviors.',
      },
    ],
  },
  {
    id: 'production',
    number: '06',
    title: 'Production / Proof',
    items: [
      {
        id: 'releases',
        title: 'Published Packages',
        slug: 'production/releases',
        description: 'skepis@0.1.4 npm package, Python package, and verified release history.',
      },
      {
        id: 'verification-matrix',
        title: 'Verification Matrix',
        slug: 'production/verification-matrix',
        description: 'Evidence from 108 WSL tests and 108 Windows tests across five MCP clients.',
      },
      {
        id: 'portable-reports',
        title: 'Portable Reports',
        slug: 'production/portable-reports',
        description: 'Canonical JSON and Markdown clean evaluation report specifications.',
      },
    ],
  },
  {
    id: 'security',
    number: '07',
    title: 'Security',
    items: [
      {
        id: 'trust-model',
        title: 'Trust Model',
        slug: 'security/trust-model',
        description: 'Local-first architecture: no cloud telemetry, no central database, no credential leaks.',
      },
      {
        id: 'privacy-boundary',
        title: 'Privacy & Data Boundary',
        slug: 'security/privacy-boundary',
        description: 'Why secret answer bodies are never copied into Sibyl Memory.',
      },
      {
        id: 'failure-behavior',
        title: 'Failure Behavior',
        slug: 'security/failure-behavior',
        description: 'Fail-closed invariant: what happens when Sibyl state is missing or corrupted.',
      },
    ],
  },
  {
    id: 'help',
    number: '08',
    title: 'Help',
    items: [
      {
        id: 'troubleshooting',
        title: 'Troubleshooting',
        slug: 'help/troubleshooting',
        description: 'Concrete fixes for MCP connection drops, Python env conflicts, and evaluator timeouts.',
      },
      {
        id: 'faq',
        title: 'FAQ',
        slug: 'help/faq',
        description: 'Frequently asked questions regarding agent benchmarking, Sibyl, and policy modes.',
      },
    ],
  },
]
