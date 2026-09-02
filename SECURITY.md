# Security

Skepis is a local-first evaluation tool for coding-agent benchmarks. It records exposure evidence for registered protected resources and gates evaluation claims. It is not a sandbox, an access-control system, or a universal monitor.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature for this repository when it is available. Do not include private benchmark material, credentials, tokens, or keys in issues or pull requests. If private reporting is unavailable, open a public issue requesting a private reporting channel without sharing sensitive details.

## Scope

Security-sensitive code includes:

- protected-resource path validation and reads under `src/skepis/capture/`;
- the MCP server and tool boundary in `src/skepis/mcp.py`;
- policy and persisted exposure state under `src/skepis/policy/` and the Sibyl integration;
- the npm launcher and local runtime setup under `npm/`.

## Trust boundaries and limits

- Only successful reads of registered, in-root resources through supported CLI or MCP boundaries create exposure events.
- Direct filesystem, shell, browser, internal-tool, unsupported MCP, and unsupported coding-agent activity remains outside the observed boundary and is reported as incomplete monitoring.
- The configured evaluator runs without a shell, but evaluator code and benchmark inputs remain project-owned code and data.
- Never store real secrets in repository configuration, fixtures, issue reports, or logs.
- The project is not independently audited and should not be used as the only control for production secrets or high-consequence decisions.
