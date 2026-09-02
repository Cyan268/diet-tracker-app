import React, { useState } from "react";
import { registerRootComponent } from "expo";
import { openDatabaseAsync } from "expo-sqlite";
import { withWriteTransaction } from "../src/db/transactions";

function barrier() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

async function checkTransactions() {
  // Dedicated in-memory DB: never opens the user's diet-tracker.db.
  const db = await openDatabaseAsync(":memory:", { useNewConnection: true });
  try {
    await db.execAsync(
      "CREATE TABLE probe (id TEXT PRIMARY KEY); CREATE TABLE cursor (value INTEGER);"
    );
    const oldEntered = barrier();
    const oldRelease = barrier();
    const oldA = db
      .withTransactionAsync(async () => {
        await db.runAsync("INSERT INTO probe VALUES ('legacy-A')");
        oldEntered.release();
        await oldRelease.promise;
        throw new Error("intentional legacy rollback");
      })
      .catch((error: Error) => error.message);
    await oldEntered.promise;
    await db.runAsync("INSERT INTO probe VALUES ('legacy-B')");
    oldRelease.release();
    await oldA;
    const legacyRows = await db.getAllAsync<{ id: string }>("SELECT * FROM probe");
    if (legacyRows.length !== 0) throw new Error("legacy mixing scenario did not reproduce");

    const entered = barrier();
    const release = barrier();
    const first = withWriteTransaction(
      db,
      async (txn) => {
        await txn.runAsync("INSERT INTO probe VALUES ('rolled-back-A')");
        await txn.runAsync("INSERT INTO cursor VALUES (12)");
        entered.release();
        await release.promise;
        throw new Error("intentional gated rollback");
      },
      "web"
    ).catch((error: Error) => error.message);
    await entered.promise;
    let secondEntered = false;
    const second = withWriteTransaction(
      db,
      async (txn) => {
        secondEntered = true;
        await txn.runAsync("INSERT INTO probe VALUES ('preserved-B')");
      },
      "web"
    );
    await Promise.resolve();
    const queued = !secondEntered;
    release.release();
    await Promise.all([first, second]);
    const rows = await db.getAllAsync<{ id: string }>("SELECT * FROM probe");
    const cursors = await db.getAllAsync("SELECT * FROM cursor");
    if (!queued || rows.length !== 1 || rows[0].id !== "preserved-B" || cursors.length !== 0) {
      throw new Error("write gate did not isolate rollback/cursor from the next writer");
    }
    return {
      status: "PASS",
      runtime: "Expo SQLite Web WASM/Worker",
      sqlite: await db.getFirstAsync("SELECT sqlite_version() AS version"),
      crossOriginIsolated: window.crossOriginIsolated,
      legacyMixedWriteLost: true,
      queuedWriterIsolated: queued,
      committedRows: rows,
      rolledBackCursorCount: cursors.length,
      userDatabaseTouched: false,
    };
  } finally {
    await db.closeAsync();
  }
}

function App() {
  const [result, setResult] = useState("Ready");
  const [running, setRunning] = useState(false);
  return (
    <main style={{ padding: 32, fontFamily: "system-ui", maxWidth: 960 }}>
      <h1>U4 Web SQLite transaction check</h1>
      <p>Independent in-memory database. No login, production API, model call or user data.</p>
      <button
        disabled={running}
        onClick={async () => {
          setRunning(true);
          setResult("Running");
          try {
            setResult(JSON.stringify(await checkTransactions(), null, 2));
          } catch (error) {
            setResult(`FAIL: ${error instanceof Error ? error.message : String(error)}`);
          } finally {
            setRunning(false);
          }
        }}
      >
        Run isolated transaction checks
      </button>
      <pre role="status">{result}</pre>
    </main>
  );
}

registerRootComponent(App);
