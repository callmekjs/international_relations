import { copyFile, access } from "node:fs/promises";
import { constants } from "node:fs";
import { resolve } from "node:path";
import { ensureAnalysis2025 } from "./build-analysis-2025.mjs";

const source = resolve(process.cwd(), "../data.json");
const destination = resolve(process.cwd(), "public/data.json");

try {
  await access(source, constants.R_OK);
  await copyFile(source, destination);
  console.log("Synced ../data.json to public/data.json");
} catch {
  await access(destination, constants.R_OK);
  console.log("Using the packaged public/data.json snapshot");
}

await ensureAnalysis2025();
