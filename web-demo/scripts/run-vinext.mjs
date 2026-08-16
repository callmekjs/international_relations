import { spawn } from "node:child_process";
import { resolve } from "node:path";

const [command, ...args] = process.argv.slice(2);

if (!command) {
  throw new Error("vinext command is required");
}

const cli = resolve(process.cwd(), "node_modules", "vinext", "dist", "cli.js");
const child = spawn(process.execPath, [cli, command, ...args], {
  cwd: process.cwd(),
  env: {
    ...process.env,
    WRANGLER_LOG_PATH: ".wrangler/wrangler.log",
  },
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error(error);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  if (signal) {
    console.error(`vinext stopped by ${signal}`);
    process.exitCode = 1;
    return;
  }
  process.exitCode = code ?? 1;
});
