// A typed client for the oversight HTTP service, for agents written in TypeScript or JavaScript.
// Start the service with `oversight serve`, then wrap any tool function with `guarded`.
// Run this file directly: node --experimental-strip-types examples/typescript/oversight.mts

import { pathToFileURL } from "node:url";

export type Outcome = "execute" | "block" | "ask_human" | "defer";

export interface Decision {
  call_id: string;
  outcome: Outcome;
  risk: "low" | "medium" | "high" | "critical";
  reason: string;
  reasons: string[];
  rules: string;
}

export class Oversight {
  private url: string;
  private token: string | undefined;

  constructor(url = process.env.OVERSIGHT_URL ?? "http://127.0.0.1:8321", token = process.env.OVERSIGHT_TOKEN) {
    this.url = url;
    this.token = token;
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(this.url + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}) },
      body: JSON.stringify(body),
    });
    const data = (await res.json()) as T;
    if (!res.ok && (data as { outcome?: Outcome }).outcome === undefined) {
      throw new Error(`oversight ${path} failed with ${res.status}: ${JSON.stringify(data)}`);
    }
    return data;
  }

  check(tool: string, params: Record<string, unknown>, description = ""): Promise<Decision> {
    return this.post<Decision>("/check", { tool, params, description });
  }

  answer(callId: string, approved: boolean, note = ""): Promise<{ ok: boolean }> {
    return this.post("/answer", { call_id: callId, approved, note });
  }

  setPersonAvailable(available: boolean): Promise<{ ok: boolean }> {
    return this.post("/person", { available });
  }

  // Wrap a tool so it only runs when oversight allows it. `ask` puts the question to a person.
  guarded<P extends Record<string, unknown>, R>(
    tool: string,
    fn: (params: P) => Promise<R>,
    ask?: (d: Decision) => Promise<boolean>,
  ): (params: P) => Promise<R> {
    return async (params: P) => {
      const d = await this.check(tool, params);
      if (d.outcome === "execute") return fn(params);
      if (d.outcome === "ask_human" && ask) {
        const approved = await ask(d);
        await this.answer(d.call_id, approved);
        if (approved) return fn(params);
      }
      throw new Error(`${tool} was not run (${d.outcome}, ${d.risk} risk): ${d.reason}`);
    };
  }
}

// Demo: three made up tool calls (runs only when this file is executed directly).
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const guard = new Oversight();
  const readFile = guard.guarded("read_file", async (p: { path: string }) => `contents of ${p.path}`);
  const payInvoice = guard.guarded(
    "pay_invoice",
    async (p: { vendor: string; amount: number }) => `paid ${p.amount} to ${p.vendor}`,
    async (d) => {
      console.log(`asking a person: ${d.reason}`);
      return true;
    },
  );
  console.log(await readFile({ path: "README.md" }));
  console.log(await payInvoice({ vendor: "Acme Paper Co", amount: 420 }));
  try {
    await guard.guarded("run_sql", async () => "dropped")({ database: "app_production", query: "DROP TABLE orders" });
  } catch (e) {
    console.log((e as Error).message);
  }
}
