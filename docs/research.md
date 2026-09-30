# Research notes

## The problem, stated precisely

An agent produces a stream of actions $a_1, a_2, \dots$ at times $t_1 < t_2 < \dots$. Each action has observable features $x_i$ (the tool, its parameters) and a hidden label: harmful or not, with a severity. For each action, a router picks one of three reviewers:

- **nobody**: the action runs;
- **a checker** (rules or a model) that catches a harmful action with probability $r$ and wrongly flags a benign one with probability $f$;
- **a person**, who catches a harmful action with probability $q(n)$, where $n$ is how many times they were interrupted in the last hour, and who is only reachable when available, $A(t) \in \{0, 1\}$.

The person's attention is the scarce resource. The router must keep interruptions within a budget of $B$ per window $W$, and the goal is to minimise harm that gets through, with the time actions spend waiting as a secondary cost:

$$\min_{\pi}\ \mathbb{E}\Big[\sum_i \text{severity}_i \cdot \mathbf{1}[\text{harmful}_i \wedge \text{runs}_i]\Big] + \lambda\,\mathbb{E}[\text{waiting time}] \quad \text{s.t.} \quad \#\{\text{interrupts in any window } W\} \le B.$$

Two things make this harder than a standard deferral problem. The person's accuracy $q(n)$ depends on how the budget was spent earlier, so decisions are coupled over time. And the person is sometimes not there at all, so "defer to the expert" can mean "wait for hours".

## How this relates to existing work

**AI control.** Greenblatt et al. ([ICML 2024](https://arxiv.org/abs/2312.06942)) study protocols that get useful work from an untrusted model using a weaker trusted model and a limited budget of trusted human auditing. Bhatt et al. ([Ctrl-Z, 2025](https://arxiv.org/abs/2504.10374)) take this to multi step agents in a shell environment. This project shares the structure (untrusted agent, cheaper trusted checker, scarce human audits) and changes three assumptions: the audit budget is per unit of time rather than a fraction of all actions, the auditor gets worse when overused, and the auditor is not always available. Those three changes are what make routing an online allocation problem.

**Learning to defer.** Madras, Pitassi and Zemel ([NeurIPS 2018](https://proceedings.neurips.cc/paper/2018/hash/09d37c08f7b129e96277388757530c72-Abstract.html)) train a model to decide when to hand a case to a downstream human expert, accounting for that expert's own errors. Here the expert's error rate is not fixed: it rises with load, and the expert can be absent.

**Alert fatigue.** Clinicians override 49% to 96% of drug safety alerts ([van der Sijs et al. 2006](https://pmc.ncbi.nlm.nih.gov/articles/PMC1447540)), and acceptance of reminders fell 30% for each additional reminder per patient visit ([Ancker et al. 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5387195/)). The simulated person loses 4 points of catch rate per review beyond 6 an hour, which is gentler than that; every result is also reported with fatigue switched off.

## What the experiments found

All on synthetic workdays with a simulated person. Numbers and confidence intervals are in [results.md](results.md).

1. **An attention budget roughly halves interruptions without letting more harm through**, compared with fixed rules that send every high risk action to a person. This held across 11 changes to the assumptions about the person, the workload and how interruptions are counted.
2. **The safety gain comes from what happens when the budget runs out**, not from the budget itself. Removing the checker's takeover erased most of the harm reduction.
3. **A checker that takes over must not be allowed to approve high risk actions unless it is nearly perfect.** A confident checker with a 20% catch rate, allowed to approve, let through 52% of harmful actions versus 27% for fixed rules. Restricted to blocking, the same checker did no worse than fixed rules at any catch rate from 20% to 100%. Calibration and the takeover rule matter more than raw accuracy.
4. **Draining the budget does not help an attacker here.** A burst of harmless looking high risk actions before a harmful one raised attack success under fixed rules from 13% to 42% (by tiring the person). With the budget and a block only checker, it stayed near 13% or lower.
5. **Pacing** (keeping the last interruptions for the riskiest actions) gives a small, significant improvement at budgets of 3 or more per hour.

## What this does not show

The data, the person and the checker are simulated, and the same author wrote the scenarios and the rules checker. The findings are about the shape of the trade offs, not about rates in any real deployment. The most important missing experiment is an LLM checker on the same pool (the code for it exists; it needs an API key and about $4 of calls).

## Open questions

- **Learning the risk score.** Today the registry's weights are hand set. The audit log already records every decision and every human answer, which is the data needed to learn which features predict that a person will refuse.
- **Calibrated takeover.** Result 3 says a checker should approve only when its confidence is trustworthy. What calibration test should a model pass before `takeover: approve` is allowed?
- **Memory across actions.** Harm split into innocent looking steps is not caught. A router that scores sequences, not single actions, is the natural next step, and it connects directly to the multi step protocols in Ctrl-Z.
- **Several reviewers.** An on call rotation turns one budget into several, with handoffs and different expertise per reviewer.
- **Adaptive attackers.** The budget drain test used a fixed script. An attacker that watches its own refusals and adapts is the harder case.
