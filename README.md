# ReqFlow — AI Requirement Pipeline Agent

>**Agents League Hackathon — Reasoning Agents Track**
>6-Agent collaborative pipeline. AI structures. Humans decide. The organization gets smarter every run.

---

## What It Does

ReqFlow is an AI requirement pipeline that prevents information loss between handoffs and accumulates organizational knowledge automatically.

**The problem:** When requirements move from Sales → PM → R&D → Release, information decays. The same mistakes repeat across teams. New hires have no access to institutional memory.

**Our solution:** 6 AI Agents process every requirement end-to-end. Each stage the AI structures input, humans verify and correct. Every rejection, every correction, every decision is automatically written back to a knowledge base. Next time someone submits a similar requirement, the system surfaces what went wrong last time.

---

## Pipeline (6 Agents)

```
User Input → S1 Gatekeeper → S2a PM Form → S2b AI Generate → S3a RD Estimate → S3b Self-Test → S4 Release Review → S5a Survey → S5b CSV Analysis → S5c Results → S6 Retrospective
```

| Stage | Agent | What AI Does | What Human Does |
|---|---|---|---|
| S1 | Gatekeeper | Extracts 4Q (who/scene/problem/expected), judges verdict | Reviews AI extraction, edits, confirms |
| S2a | Value Transform | Pre-fills PM form | Fills core value, acceptance criteria, priority |
| S2b | Value Transform (full) | Generates structured criteria + test cases | Reviews output, edits, confirms |
| S3a | Scenario Test | No AI pre-fill (by design) | Fills technical plan, workload, risks |
| S3b | Scenario Test (full) | AI analyzes self-test results | Reports self-test result, decides (approve/reject/defer) |
| S4 | Release Review | Pre-assesses release verdict | Fills release info, HARD GATE: scenario must be verified |
| S5a | Feedback Analysis | Generates survey questions | Reviews, edits, publishes |
| S5b | Feedback Analysis (full) | Analyzes CSV feedback data | Pastes customer feedback |
| S6 | Retrospective | Analyzes process bottlenecks + rework patterns | Reviews retrospective |

---

## Key Features

### Self-Improving Knowledge Loop
- 15 write points → Foundry IQ (Azure AI Search)
- Every rejection captured as structured feedback
- Next similar requirement → Stage 1 alerts with historical pitfalls
- Stage 6 retrospective analyzes rework patterns from actual pipeline data

### Human-in-the-Loop Design
- All 6 stages use editable Adaptive Cards (v1.5)
- AI pre-fills suggestions, humans confirm or correct
- Stage 4 Hard Gate: scenario_verified=no → code-level block, cannot proceed
- Max 3 rounds of `info_needed` before forced rejection

### Multi-Person Collaboration
- Each card includes "next person" field for handoff
- Rollback chain: reject → notify previous stage → retry/escalate/abandon
- Rework counter tracked per requirement in Foundry IQ

---

## Microsoft Technologies Used

| Technology | Role |
|---|---|
| **Foundry IQ** (Azure AI Search) | Knowledge base — 15 write points, semantic search, self-improving loop |
| **Work IQ** (Microsoft Graph) | User lookup by name, validates handoff routing |
| **Azure Bot Service** | Bot hosting & Teams integration |
| **Bot Framework SDK** | Adaptive Cards, Activity routing, Auth |
| **Adaptive Cards v1.5** | Interactive editable forms at every stage |
| **DeepSeek API** (via OpenAI SDK) | Powering all 6 Agent LLM calls |

---

## Architecture

```
Teams / Web Chat
       ↓
   bot.py (Bot Framework)
       ↓
   pipeline.py (6-Stage Orchestrator)
    ├── agent_runner.py (LLM calls)
    ├── foundry_iq.py (Azure AI Search)
    ├── work_iq.py (Microsoft Graph)
    ├── cards.py (Adaptive Cards v1.5)
    └── schema_builder.py (JSON validation)
```

---

## Quick Start

1. Copy `.env.template` to `.env` and fill in your credentials:
```bash
cp .env.template .env
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Start ngrok:
```bash
ngrok http 3978
```

4. Start the bot:
```bash
python bot.py
```

5. Configure Azure Bot Messaging Endpoint with your ngrok URL:
```
https://your-ngrok-url.ngrok-free.dev/api/messages
```

6. Test in Azure Portal → Test in Web Chat, or sideload the Teams App Package.

---

## Demo Script

1. **Happy Path:** Submit a requirement → follow cards through all 6 stages
2. **Self-Improvement:** Reject at Stage 2 → capture feedback → Foundry IQ learns → next requirement gets alerted
3. **Hard Gate:** Stage 4 submit with scenario_verified=no → blocked, must fix
4. **Knowledge Query:** `?how to set up EDI` → Foundry IQ returns historical lessons

---

## Project Structure

```
├── bot.py                  # Teams Bot entry (activity routing, card dispatching)
├── pipeline/
│   ├── pipeline.py         # 6-stage orchestrator
│   ├── agent_runner.py     # LLM call engine (DeepSeek via OpenAI SDK)
│   ├── foundry_iq.py       # Azure AI Search integration (archive + search)
│   ├── work_iq.py          # Microsoft Graph user lookup
│   ├── cards.py            # Adaptive Cards v1.5 (17 cards)
│   └── schema_builder.py   # JSON extraction + validation
├── agents/                 # Agent system prompts (Markdown)
├── config/                 # Configuration + pipeline YAML
├── test_bot_interactive.py # E2E test suite (12 tests)
└── teams-app/              # Teams App Package (for sideloading)
```

---

Built for **Agents League Hackathon 2026** — Reasoning Agents Track
