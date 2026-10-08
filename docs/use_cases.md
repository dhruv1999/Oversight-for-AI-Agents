# Where this helps

Any team that lets an AI agent take real actions runs into the same question: which of those actions should a person look at first? Ask about too many and people stop reading. Ask about too few and something expensive slips through. This page walks through the situations where that tradeoff matters most, in plain terms.

The outcomes described below are what the default rules do today. Every team can adjust them in one readable file.

## Finance and back office

An agent pays approved invoices, reconciles accounts and keeps vendor records up to date. The finance lead is the person who approves anything that moves money.

Today that lead either approves every payment, including the routine ones, or turns approvals off for small amounts and hopes for the best. The riskiest request of the day, such as a vendor asking to change their bank details, arrives looking exactly like the other forty.

With Oversight, looking up records and preparing reports happen without anyone being asked. Paying an invoice goes to the finance lead while they still have attention to spare. A change to a vendor's bank details is treated as high risk, and a payment of $10,000 or more as critical, which always waits for a person, even if the lead is in a meeting all afternoon. When the lead has no attention left, the automatic checker can stop a suspicious payment but cannot approve one, so nothing that moves money runs without a person.

## Customer support

An agent drafts and sends replies, looks up orders and updates tickets. A support manager is responsible for what goes out under the company's name.

Out of the box, any email to someone outside the company counts as high risk, so it goes to a person while they have attention left. A team that trusts its agent with routine replies can register those replies as their own, lower risk tool, for example answers on existing tickets. A message to every customer at once stays critical and always needs a person. That is the email that does lasting damage if it is wrong.

## Software engineering

A coding agent such as Claude Code or Cursor reads files, edits code, runs tests and executes commands on a developer's machine.

Today developers either approve every command, which turns into clicking yes without reading, or switch prompts off entirely. Oversight lets reading, editing and running tests continue without interruption. Deleting files asks first. Downloading a script from an unknown server and running it goes to the developer, and if they were interrupted moments ago, the automatic checker blocks it outright rather than asking again. Writing keys into system files, or sending secrets anywhere outside the company, always goes to the developer.

## Data and analytics

An agent answers questions by querying the company database.

Reading data runs freely, so analysts get answers without waiting. Queries that touch customer records are checked automatically first. Changing data goes to a person, and deleting a table always waits for one. The agent stays useful for the ninety percent of requests that only read, without being able to quietly rewrite the database.

## IT and operations

An agent handles deployments, access requests and routine maintenance, often outside working hours.

Deploying to a test environment is checked automatically. Deploying to production and granting someone access go to the on call engineer. At night, when that engineer is asleep, risky actions wait until morning instead of running unattended or paging someone for every request.

## Who gets value from it

**Product teams launching agent features** get a way to give agents real permissions without asking users to approve everything, and a clear story for how risk is handled.

**The people who approve actions** are interrupted only for what matters, and only as often as they can actually pay attention.

**Security, risk and compliance teams** get an audit log of every decision: what the agent tried, who or what decided, why, and which version of the rules was in force. Secrets are removed before anything is written down.

**Engineering teams** can add it to an existing agent in a few lines, in Python, through MCP, over HTTP or as a Claude Code hook. In Claude Code its default mode only adds questions and blocks on top of the existing prompts, so it can be rolled out without removing any safeguard people already rely on.

## When you probably do not need it

If your agent only reads and answers questions, there is little to oversee. If it runs inside a sandbox where nothing it does can leave or be undone, a full review step adds little. And if a person only needs to approve a handful of actions a week, they can simply review them all. This project is for the space in between: agents that do many things a day, some of which really matter.
