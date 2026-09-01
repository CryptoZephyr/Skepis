#!/usr/bin/env node

"use strict";

const childProcess = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const packageRoot = path.resolve(__dirname, "..");
const packageMetadata = require(path.join(packageRoot, "package.json"));
const pythonDependencies = ["mcp>=1.27.0,<2", "sibyl-memory-client>=0.7.0"];

function run(moduleName, argv) {
  const runtime = ensureRuntime();
  const sourceRoot = path.join(packageRoot, "src");
  const environment = {
    ...process.env,
    PYTHONPATH: appendPath(sourceRoot, process.env.PYTHONPATH),
    SKEPIS_RUNTIME_PYTHON: runtime.python,
    SKEPIS_RUNTIME_SOURCE_ROOT: sourceRoot,
  };
  const result = childProcess.spawnSync(
    runtime.command,
    [...runtime.prefixArgs, "-m", moduleName, ...argv],
    {
      cwd: process.cwd(),
      env: environment,
      stdio: "inherit",
      windowsHide: true,
    },
  );
  if (result.error) {
    process.stderr.write(`skepis launcher error: ${result.error.message}\n`);
    return 1;
  }
  return typeof result.status === "number" ? result.status : 1;
}

function ensureRuntime() {
  const selected = findPython();
  if (process.env.SKEPIS_SKIP_BOOTSTRAP === "1") {
    return selected;
  }

  const platformKey = `${process.platform}-${process.arch}`;
  const cacheRoot = path.resolve(process.env.SKEPIS_NPM_CACHE || path.join(
    os.homedir(),
    ".cache",
    "skepis",
    "python",
    `${packageMetadata.version}-${platformKey}`,
  ));
  const virtualEnvironment = path.join(cacheRoot, "venv");
  const marker = path.join(cacheRoot, "ready.json");
  const virtualPython = process.platform === "win32"
    ? path.join(virtualEnvironment, "Scripts", "python.exe")
    : path.join(virtualEnvironment, "bin", "python");

  if (!fs.existsSync(marker) || !fs.existsSync(virtualPython)) {
    fs.mkdirSync(cacheRoot, { recursive: true });
    if (!fs.existsSync(virtualPython)) {
      const created = spawn(selected.command, [...selected.prefixArgs, "-m", "venv", virtualEnvironment]);
      if (created.status !== 0) {
        throwLauncherError("could not create the private Python environment", created);
      }
    }
    const installed = spawn(
      virtualPython,
      [
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        ...pythonDependencies,
      ],
    );
    if (installed.status !== 0) {
      throwLauncherError("could not install the Skepis Python dependencies", installed);
    }
    fs.writeFileSync(
      marker,
      JSON.stringify({ package: packageMetadata.name, version: packageMetadata.version }) + "\n",
      "utf8",
    );
  }
  return { command: virtualPython, prefixArgs: [], python: virtualPython };
}

function findPython() {
  const configured = process.env.SKEPIS_PYTHON;
  const candidates = configured
    ? [{ command: configured, prefixArgs: [] }]
    : process.platform === "win32"
      ? [
        { command: "python", prefixArgs: [] },
        { command: "py", prefixArgs: ["-3"] },
      ]
      : [
        { command: "python3", prefixArgs: [] },
        { command: "python", prefixArgs: [] },
      ];

  for (const candidate of candidates) {
    const result = spawn(candidate.command, [...candidate.prefixArgs, "--version"]);
    if (result.status !== 0) {
      continue;
    }
    const versionText = `${result.stdout || ""} ${result.stderr || ""}`;
    const match = versionText.match(/Python\s+(\d+)\.(\d+)/i);
    if (
      match
      && (Number(match[1]) > 3
        || (Number(match[1]) === 3 && Number(match[2]) >= 11))
    ) {
      return { ...candidate, python: candidate.command };
    }
  }
  throw new Error("Python 3.11 or newer is required for the Skepis runtime");
}

function spawn(command, argv) {
  return childProcess.spawnSync(command, argv, {
    cwd: packageRoot,
    encoding: "utf8",
    timeout: 600000,
    windowsHide: true,
  });
}

function throwLauncherError(message, result) {
  const detail = result.error ? result.error.message : (result.stderr || "").trim();
  throw new Error(detail ? `${message}: ${detail}` : message);
}

function appendPath(first, existing) {
  return existing ? `${first}${path.delimiter}${existing}` : first;
}

if (require.main === module) {
  try {
    process.exitCode = run("skepis", process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`skepis launcher error: ${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = { run };
