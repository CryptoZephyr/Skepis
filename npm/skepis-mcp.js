#!/usr/bin/env node

"use strict";

const { run } = require("./skepis.js");

try {
  process.exitCode = run("skepis.mcp", process.argv.slice(2));
} catch (error) {
  process.stderr.write(`skepis MCP launcher error: ${error.message}\n`);
  process.exitCode = 1;
}
