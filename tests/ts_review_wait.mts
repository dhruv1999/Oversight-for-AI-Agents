// The TypeScript client waiting for a person to answer on the review page. Run by tests/test_review_page.py.
import { Oversight } from "../examples/typescript/oversight.mts";

const guard = new Oversight(process.env.OVERSIGHT_URL);
const pay = guard.guarded("pay_invoice", async (p: { vendor: string; amount: number }) => `paid ${p.amount} to ${p.vendor}`, "review-page");
console.log(await pay({ vendor: "Acme", amount: 420 }));
