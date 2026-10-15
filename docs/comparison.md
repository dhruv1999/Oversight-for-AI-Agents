# How it compares

Most paid tools in this space screen what goes into and out of a model, or control access, and are sold to enterprises. The free options are toolkits you assemble yourself, and agent frameworks can pause before the tools you mark and wait for a yes.

| Tool | What it does | Cost |
|---|---|---|
| [Lakera Guard](https://www.lakera.ai) | catches prompt attacks and data leaks | free tier; enterprise plans through sales |
| [Zenity](https://zenity.io) | security and governance for company agents | enterprise, through sales |
| [Amazon Bedrock Guardrails](https://aws.amazon.com/bedrock/guardrails/) | filters harmful content and topics | pay per use |
| [Permit.io](https://www.permit.io) | access control for apps and agents, including requests a person approves | free tier; paid plans priced by active users |
| [Guardrails AI](https://www.guardrailsai.com) | checks model output against rules | open source; paid Pro version |
| [NVIDIA NeMo Guardrails](https://docs.nvidia.com/nemo/guardrails/) | programmable rules around a model, including checks on tool calls | free, open source |
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/human-in-the-loop), [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) | pause before tools you mark and wait for approval | free, open source |

Where this project fits:

* It answers the question these tools leave to you: can this person still give a good approval right now? None of the tools above, as far as we could find, keeps track of how often the reviewer has already been asked.
* It is free under the MIT license and runs on your own machines. Nothing leaves them unless you turn on an AI checker.
* It works alongside them. A content filter can screen what the model reads, while Oversight decides which actions a person sees.

*Based on public product pages and listings as of October 2026. Prices change, so check with each vendor.*
