import React, { useState } from 'react'
import { CodeBlock } from './CodeBlock'

interface ClientConfig {
  id: string
  name: string
  configFile: string
  instructionFile: string
  format: 'json' | 'toml'
  snippet: string
  notes: string
}

const CLIENTS: ClientConfig[] = [
  {
    id: 'claude',
    name: 'Claude Code',
    configFile: '.mcp.json',
    instructionFile: 'CLAUDE.md',
    format: 'json',
    notes: 'Configures project-local stdio server. Merges safely with other existing MCP servers.',
    snippet: `{
  "mcpServers": {
    "skepis": {
      "command": "npx",
      "args": ["-y", "skepis-mcp", "--config", "skepis.json"]
    }
  }
}`,
  },
  {
    id: 'cursor',
    name: 'Cursor',
    configFile: '.cursor/mcp.json',
    instructionFile: '.cursor/rules/skepis.mdc',
    format: 'json',
    notes: 'Project-level Cursor configuration. Adds rule instructing agent to use skepis_read_protected.',
    snippet: `{
  "mcpServers": {
    "skepis": {
      "command": "npx",
      "args": ["-y", "skepis-mcp", "--config", "skepis.json"]
    }
  }
}`,
  },
  {
    id: 'codex',
    name: 'Codex',
    configFile: '.codex/config.toml',
    instructionFile: 'AGENTS.md',
    format: 'toml',
    notes: 'TOML configuration is semantically merged preserving comments and existing agent settings.',
    snippet: `[mcp_servers.skepis]
command = "npx"
args = ["-y", "skepis-mcp", "--config", "skepis.json"]`,
  },
  {
    id: 'antigravity',
    name: 'Antigravity',
    configFile: '.agents/mcp_config.json',
    instructionFile: '.agents/rules/skepis.md',
    format: 'json',
    notes: 'Configures native Antigravity agent tool suite. Validated through stdio JSON-RPC handshake.',
    snippet: `{
  "mcpServers": {
    "skepis": {
      "command": "npx",
      "args": ["-y", "skepis-mcp", "--config", "skepis.json"]
    }
  }
}`,
  },
  {
    id: 'gemini',
    name: 'Gemini CLI',
    configFile: '.gemini/settings.json',
    instructionFile: 'GEMINI.md',
    format: 'json',
    notes: 'Standard project-scoped Gemini CLI integration.',
    snippet: `{
  "mcpServers": {
    "skepis": {
      "command": "npx",
      "args": ["-y", "skepis-mcp", "--config", "skepis.json"]
    }
  }
}`,
  },
]

export const McpConfigViewer: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string>('claude')
  const client = CLIENTS.find((c) => c.id === selectedId) || CLIENTS[0]

  return (
    <div className="my-6 rounded-xl border border-stone-200/90 bg-white shadow-sm p-4 sm:p-5 font-body">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-stone-200">
        <div>
          <h4 className="font-heading text-sm font-bold text-stone-900 tracking-tight">
            MCP Client Configuration Matrix
          </h4>
          <p className="text-xs text-stone-600 mt-0.5">
            `skepis connect` automatically writes and verifies these configurations.
          </p>
        </div>

        <div className="w-full sm:w-auto overflow-x-auto no-scrollbar flex items-center gap-1.5 bg-stone-100 p-1 rounded-lg border border-stone-200/70">
          {CLIENTS.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelectedId(c.id)}
              type="button"
              className={`whitespace-nowrap shrink-0 px-2.5 py-1 text-xs font-mono rounded transition-all ${
                selectedId === c.id
                  ? 'bg-white text-stone-900 font-bold shadow-xs border border-stone-200/80'
                  : 'text-stone-600 hover:text-stone-900 hover:bg-stone-200/50'
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        <div className="p-3 bg-[#fbf9f5] rounded-md border border-stone-200/70">
          <span className="text-[11px] font-mono uppercase text-stone-600 font-semibold block mb-1">
            Configuration Path
          </span>
          <code className="font-mono text-xs text-stone-900 font-semibold">
            {client.configFile}
          </code>
        </div>
        <div className="p-3 bg-[#fbf9f5] rounded-md border border-stone-200/70">
          <span className="text-[11px] font-mono uppercase text-stone-600 font-semibold block mb-1">
            Installed Rule / Instruction
          </span>
          <code className="font-mono text-xs text-stone-900 font-semibold">
            {client.instructionFile}
          </code>
        </div>
      </div>

      <div className="mt-3">
        <CodeBlock code={client.snippet} language={client.format} filename={client.configFile} />
      </div>

      <div className="mt-3 text-xs text-stone-600 flex items-center justify-between">
        <span>{client.notes}</span>
        <span className="font-mono text-[11px] text-emerald-800 font-semibold">5 Tools Reachable</span>
      </div>
    </div>
  )
}
