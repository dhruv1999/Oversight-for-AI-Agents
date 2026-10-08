// A typed client for the oversight HTTP service, for agents written in TypeScript or JavaScript.
// Start the service with `oversight serve`, then wrap any tool function with `guarded`.
// Pass "review-page" as the third argument to let the person decide on the service's review page.
// Run this file directly: node --experimental-strip-types examples/typescript/oversight.mts

import { pathToFileURL } from "node:url";

export type Outcome = "execute" | "block" | "ask_human" | "defer";

export interface Decision {
  call_id: string;
  outcome: Outcome;
  risk: "low" | "medium" | "high" | "critical";
  reason: string;
  summary: string;
  reasons: string[];
  rules: string;
}

export interface Status {
  call_id: string;
  status: "waiting" | "approved" | "rejected";
  note?: string;
}

export class Oversight {
  private url: string;
  private token: string | undefined;

  constructor(url = process.env.OVERSIGHT_URL ?? "http://127.0.0.1:8321", token = process.env.OVERSIGHT_TOKEN) {
    this.url = url;
    this.token = token;
  }

  private auth(): Record<string, string> {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(this.url + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.auth() },
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

  // Where a waiting action stands: still waiting, approved or rejected on the review page. undefined if unknown.
  async status(callId: string): Promise<Status | undefined> {
    const res = await fetch(`${this.url}/checks/${encodeURIComponent(callId)}`, { headers: this.auth() });
    if (res.status === 404) return undefined;
    if (!res.ok) throw new Error(`oversight /checks failed with ${res.status}`);
    return (await res.json()) as Status;
  }

  // Wait until the person answers on the review page. Nobody answering in time means "do not run it".
  async waitForAnswer(callId: string, timeoutMs = 10 * 60_000, intervalMs = 2000): Promise<boolean> {
    const end = Date.now() + timeoutMs;
    while (Date.now() < end) {
      const s = await this.status(callId);
      if (s === undefined) return false;
      if (s.status !== "waiting") return s.status === "approved";
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    return false;
  }

  // Wrap a tool so it only runs when oversight allows it. `ask` puts the question to a person, or
  // "review-page" waits for their answer on the service's review page (queued actions included).
  guarded<P extends Record<string, unknown>, R>(
    tool: string,
    fn: (params: P) => Promise<R>,
    ask?: ((d: Decision) => Promise<boolean>) | "review-page",
  ): (params: P) => Promise<R> {
    return async (params: P) => {
      const d = await this.check(tool, params);
      if (d.outcome === "execute") return fn(params);
      if (ask === "review-page" && (d.outcome === "ask_human" || d.outcome === "defer")) {
        if (await this.waitForAnswer(d.call_id)) return fn(params);
      } else if (d.outcome === "ask_human" && ask) {
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
