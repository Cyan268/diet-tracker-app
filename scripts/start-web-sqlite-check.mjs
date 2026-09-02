import { spawn } from "node:child_process";

const child = spawn(
  process.execPath,
  ["node_modules/expo/bin/cli", "start", "--offline", "--port", "8085"],
  {
    stdio: "inherit",
    windowsHide: true,
    env: { ...process.env, NUTRIPILOT_SQLITE_DIAGNOSTICS: "1" },
  }
);
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
console.log("Isolated checks: http://127.0.0.1:8085/__u4_sqlite_check");
