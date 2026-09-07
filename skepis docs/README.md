# Skepis Docs

The public documentation site for [Skepis](https://github.com/CryptoZephyr/Skepis), a local-first benchmark-contamination and evaluation-integrity layer for AI coding-agent benchmarks.

Skepis records exposure only when a registered protected resource is successfully read through its supported CLI or MCP boundary, then gates whether an existing evaluator may make a clean claim. It does not score models, observe every host surface, or provide bypass-proof enforcement. Sibyl Memory is the separate persistent state layer used to carry scoped exposure state and journal events across processes and sessions.

This directory is a static Vite and React application. The Skepis evaluator, capture boundary, Sibyl integration, CLI, and MCP server live in the parent repository under `src/` and `npm/`.

## Local development

Requirements:

- Node.js 18 or newer
- pnpm 11 or a compatible pnpm version

From this directory:

```bash
pnpm install
pnpm run lint
pnpm run build
pnpm run dev
```

Vite serves the site locally. Documentation pages use URL hashes, so direct navigation and refresh work without a server-side router.

## Deployment

The site is configured for Netlify in [`netlify.toml`](netlify.toml). Build the static output and deploy it from this directory with the Netlify CLI:

```bash
pnpm run build
netlify deploy --prod --dir=dist
```

The deployment target, account, and returned URL must be verified against the Netlify CLI output before the site is described as live.

## Public scope

The site documents the verified Skepis workflow and its limits. The core product records exposure through the supported protected-read boundary, persists state through Sibyl, and gates evaluation claims with the configured policy. Direct filesystem, shell, browser, internal-tool, unsupported MCP, and unsupported coding-agent routes remain outside the observed boundary and are not presented as clean evidence.

## License

This project is licensed under the [MIT License](LICENSE).
