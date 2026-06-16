import path from "node:path";
import { defineConfig } from "@playwright/test";

const rootDir = path.resolve(__dirname, "..");
const pythonBin = process.env.PYTHON_BIN ?? path.join(rootDir, ".venv", "bin", "python");

export default defineConfig({
  testDir: "./tests/playwright",
  timeout: 30_000,
  webServer: {
    command: `cd "${rootDir}" && "${pythonBin}" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001`,
    url: "http://127.0.0.1:8001/health",
    reuseExistingServer: true,
    timeout: 30_000
  },
  use: {
    baseURL: "http://127.0.0.1:8001"
  }
});
