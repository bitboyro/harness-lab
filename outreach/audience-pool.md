# Outreach pool — who to send harness-lab posts & results to

Audience for **API packaging for agents**: MCP vs MCP+skill vs docs+curl vs code sandbox, holding API / tasks / model fixed. Prefer people who care about *measurement*, agent tooling, or MCP — not generic AI hype.

**Pitch in one line:** *Same API, same model, same tasks — only packaging changes. Which form do agents actually use better, and at what cost?*

Use the **angle** column when writing a DM / email so it matches what they already write about.

Status legend: `primary` = highest fit / send first · `secondary` = good amplification · `community` = post publicly, don’t cold-DM individuals · `press` = only with a real result story

---

## A. Send first (highest fit)

| Name | Role | Where | Angle | Status | Notes |
|---|---|---|---|---|---|
| **Simon Willison** | LLM / agentic engineering blogger | [simonwillison.net](https://simonwillison.net/), [@simonw](https://twitter.com/simonw), [newsletter](https://simonw.substack.com/) | MCP vs skills vs curl — he literally wrote that skills+terminal eclipsed MCP, then re-engaged on stateless MCP | primary | Best single target. Link a short reproducible result + `harness report` HTML. Contact via blog / Mastodon / X; he often linkblogs careful measurements. |
| **swyx (Shawn Wang)** | Latent Space / AI Engineer | [swyx.io](https://www.swyx.io/), [@swyx](https://twitter.com/swyx), [latent.space](https://www.latent.space/) | “Agent experience” / packaging as an AI-eng concern; AI Engineer World’s Fair MCP track | primary | Warm intro preferred (they discourage cold PR). Discord + public post often better than cold email. |
| **Hamel Husain** | Evals / AI product quality | [@hamelhusain](https://twitter.com/hamelhusain), essays on evals | Gold-free vs graded metrics, contamination gate, programmatic grading (no LLM judge) | primary | Frame as *evals for packaging*, not another model leaderboard. |
| **Shreya Shankar** | LLM eval methodology | [@sh_reya](https://twitter.com/sh_reya) | Validation flags, refuse-to-pool boundaries, judge skepticism | primary | Cite that harness refuses LLM-as-judge for correctness. |
| **Dex Horthy** | 12-Factor Agents / HumanLayer | [@dexhorthy](https://twitter.com/dexhorthy) | Production agent design: how tools are exposed to the loop | primary | Packaging = DX for the model, not the human. |
| **Jason Liu** | Structured outputs / tool routing (OpenAI Codex DX) | [@jxnlco](https://twitter.com/jxnlco) | Tool schemas, routing, Instructor lineage | primary | Emphasize tool-surface / discovery axes. |
| **Lee Robinson** | Cursor DX | [@leerob](https://twitter.com/leerob) | Coding agents + skills + MCP in real workflows | primary | Natural fit for Cursor/Claude Code skill install story (`harness init`). |
| **Chip Huyen** | AI Engineering author | [huyenchip.com](https://huyenchip.com/) | Production AI systems, context as a scarce resource | secondary | Doc-budget-as-causal-property (V2) is on-brand. |
| **Eugene Yan** | Applied ML / eval surveys | [eugeneyan.com](https://eugeneyan.com/), [@eugeneyan](https://twitter.com/eugeneyan) | Task-specific eval techniques | secondary | Offer methodology write-up, not just a winner chart. |
| **Omar Khattab** | DSPy / MIT | [@lateinteraction](https://twitter.com/lateinteraction) | Programming agent pipelines vs prompt stuffing | secondary | Contrast “authored skill” vs generated materials. |
| **Jeremy Howard** | fast.ai / Answer.AI | [@jeremyphoward](https://twitter.com/jeremyphoward) | Small-team rigorous experimentation | secondary | Reproducible harness + contamination-free rig. |
| **Tadas Antanavicius** | PulseMCP / MCP Registry | [@tadasant](https://github.com/tadasant), PulseMCP | Empirical evidence for how MCP servers should be packaged | primary | MCP ecosystem amplifier; registry / directory audiences. |
| **Adam Jones** | Anthropic / MCP Registry | [@domdomegg](https://github.com/domdomegg) | Spec-adjacent empirical data (revisions, discovery) | secondary | Via MCP Discord / GitHub, not cold sales email. |
| **Toby Padilla** | GitHub / MCP Registry | [@toby](https://github.com/toby) | Registry + server quality signals | secondary | Same channel as registry maintainers. |

---

## B. Newsletters, podcasts, and editors

| Outlet | Who | Fit | How to approach | Status |
|---|---|---|---|---|
| **Latent Space** | swyx + hosts | Perfect topical fit | Discord community post; guest pitch only with warm intro ([about](https://www.latent.space/about) — no cold PR) | primary |
| **Simon’s newsletter / linkblog** | Simon Willison | Highest organic reach for this topic | Short post + clear figure + open source link; he finds things | primary |
| **Interconnects** | Nathan Lambert [@natolambert](https://twitter.com/natolambert) | Weaker fit (post-training) unless you have model×packaging interaction | Only if results say something about effort / reasoning levels | secondary |
| **The Pragmatic Engineer** | Gergely Orosz | Eng org / AI-at-work angle | Pitch “what packaging to ship for agents” for eng leaders | secondary |
| **Practical AI** (Changelog) | Chris / Daniel | Practitioner podcast | Pitch episode: measuring MCP vs docs | secondary |
| **Software Engineering Daily** | SED editors | Deep-dive technical | Full methodology episode | secondary |
| **TLDR AI / Ben’s Bites / The Batch** | newsletter editors | Broad AI | Only with a sharp one-sentence finding + chart | press |
| **VentureBeat / The New Stack** | reporters covering MCP | Spec / industry news | Pair with a newsworthy result or release | press |

---

## C. MCP & agent protocol community (post here)

| Channel | URL / entry | What to post | Status |
|---|---|---|---|
| **MCP Discord** | [modelcontextprotocol.io/community/communication](https://modelcontextprotocol.io/community/communication) · invite often `discord.gg/6CSzBmMkjX` | Short result thread; ask for feedback on dual-revision testing | community |
| **MCP GitHub Discussions** | [github.com/modelcontextprotocol](https://github.com/modelcontextprotocol) | Spec-relevant findings (e.g. revision A vs B, discovery patterns) | community |
| **MCP Registry discussions** | [registry discussions](https://github.com/modelcontextprotocol/registry/discussions) | “How should servers be packaged for agents?” + data | community |
| **PulseMCP / MCP directories** | PulseMCP site + social | Server authors who want measured packaging advice | community |
| **AAIF / Linux Foundation MCP news** | follow AAIF announcements | Cite when discussing governance-neutral measurement | community |

---

## D. Product / platform people (tools your audience already uses)

| Org / person | Why they care | Status |
|---|---|---|
| **Anthropic** — Claude Code, Skills, MCP teams | Skills vs MCP is *their* design space; your arms map onto it | primary |
| **Cursor** — agent / MCP / skills | `harness init --agent cursor`; packaging for coding agents | primary |
| **OpenAI** — Agents / Codex / Responses tool-use | Tool-calling packaging comparisons | secondary |
| **Microsoft** — Copilot Studio / MCP | Enterprise MCP packaging | secondary |
| **Block / Cloudflare / others shipping MCP** | “Should we ship MCP, docs, or a sandbox?” | secondary |
| **Vercel AI / Modal / agent infra** | Agent experience & cost decomposition | secondary |

Prefer public threads that tag the product area over cold enterprise sales emails. Offer: *run against your public MCP / OpenAPI for free with a pack*.

---

## E. Research & benchmarks (cite + share mutually)

| Project / people | Link | Why | Status |
|---|---|---|---|
| **Berkeley Function Calling Leaderboard (BFCL)** | [gorilla.cs.berkeley.edu](https://gorilla.cs.berkeley.edu/leaderboard) · Patil et al. | Complementary: they score *models* on tools; you score *packaging* holding the model fixed | primary |
| **MCP-Bench** (Accenture et al.) | [github.com/Accenture/mcp-bench](https://github.com/Accenture/mcp-bench) · arXiv:2508.20453 | Live MCP servers / multi-step; different question (model capability vs packaging) | primary |
| **τ-bench / agent bench authors** | various | Multi-turn tool agents | secondary |
| **Lilian Weng** | [@lilianweng](https://twitter.com/lilianweng) | Agents survey audience | secondary |
| **Academic X / Bluesky** | tag with `MCP`, `tool use`, `agent eval` | Reproducible methods papers love contamination-free rigs | secondary |

Outreach note: lead with *orthogonal contribution* (“we don’t replace BFCL; we fix packaging while freezing the model”) so this isn’t dismissed as another leaderboard.

---

## F. Public forums (broadcast, then engage)

| Forum | Where | Posting tip | Status |
|---|---|---|---|
| **Hacker News** | news.ycombinator.com | Title = question or measured claim; lead with method + open source; expect MCP debate | community |
| **r/MachineLearning** | Show & Tell / research | Abstract + figures + limitations | community |
| **r/LocalLLaMA** | if open models appear in matrix | Cost / packaging under local models | community |
| **r/ClaudeAI**, **r/OpenAI**, **r/cursor** | practitioner subs | Shorter “what I measured” post | community |
| **Lobsters** | lobste.rs (`ai`, `programming`) | More method-skeptical; bring validity controls | community |
| **Dev.to / Hashnode** | long-form mirror | Good for SEO of the methodology post | community |
| **LinkedIn** | personal + AI Eng groups | Chart + one finding; tag people from §A sparingly | community |
| **X / Bluesky** | thread | Hook = surprising packaging win or “MCP didn’t win”; attach report screenshot | community |
| **Latent Space Discord** | [latent.space/p/community](https://www.latent.space/p/community) | Share in appropriate channel; ask for critique | community |
| **AI Engineer events** | World’s Fair / Summit (lu.ma/ls) | Talk proposal: packaging as causal variable | secondary |

---

## G. Romanian / EU / regional (optional local amplification)

Useful if you want local press or meetups alongside the global AI-eng crowd. Fill handles as you confirm them.

| Type | Targets to find / add | Status |
|---|---|---|
| Local AI / ML meetups | Bucharest, Cluj, Iași AI meetups; How to Web; DefCamp side events | secondary |
| EU AI eng communities | AI Engineer EU satellites, Berlin agentic meetups | secondary |
| Regional tech media | GoIT / local eng blogs, Softbinator-style communities, LinkedIn RO AI groups | secondary |
| University labs | CS departments working on NLP / agents — seminar talk | secondary |

---

## H. Tracking sheet (copy into a spreadsheet)

Suggested columns for your CRM / Notion:

| field | example |
|---|---|
| name | Simon Willison |
| tier | A — primary |
| channel | blog DM / X |
| angle | MCP vs skills vs curl measurement |
| asset_sent | insights.html + HN post URL |
| date_sent | 2026-… |
| reply | none / interested / shared |
| next_step | send full matrix when ready |
| do_not_spam | true after 1 follow-up |

---

## Outreach sequence (recommended)

1. **Publish** a short public post (blog or HN) with one chart, method caveats, and repo link — so DMs aren’t a cold pitch with no artifact.
2. **Day 0:** post to MCP Discord + Latent Space Discord + X/Bluesky thread.
3. **Day 0–1:** personal notes to **Simon, Hamel, Dex, Tadas, Lee** (5 max). One paragraph + link. No attachments wall.
4. **Day 2–3:** secondary individuals + LinkedIn.
5. **Week 2:** podcast / newsletter pitches only if the public post got engagement.
6. **Never** claim a winner from a probe or smoke run; use language matching the report (`validated-controlled` vs `unvalidated`).

### DM / email skeleton

```text
Subject: Measured API packaging for agents (MCP vs skill vs docs+curl)

Hi {name} — you wrote about {their_topic}. I ran a controlled study that
holds API, tasks, and model fixed and only changes packaging (MCP, MCP+skill,
docs+curl, code sandbox).

One finding: {one careful claim with caveat}.
Report: {url}
Repo: https://github.com/…/harness-lab

Happy to share the pack / traces if useful — or take a critique on the design.
```

### What *not* to do

- Don’t mass-CC influencers.
- Don’t pitch Latent Space as “PR”.
- Don’t lead with cost-savings marketing copy; lead with a falsifiable claim.
- Don’t pool or overclaim across models / revisions / field vs controlled.

---

## Quick “start this week” shortlist

1. Simon Willison  
2. MCP Discord + Registry / PulseMCP (Tadas)  
3. Hamel Husain  
4. Dex Horthy  
5. swyx / Latent Space Discord (public share, not cold PR email)  
6. Lee Robinson (Cursor angle)  
7. Hacker News Show HN or measured-results post  
8. BFCL / MCP-Bench authors (academic courtesy + mutual citation)

---

## Maintenance

Update this file when someone replies or a handle goes stale. Prefer adding **people who already write about agents/MCP/evals** over vanity follower counts.
