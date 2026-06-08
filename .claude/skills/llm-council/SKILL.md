---
name: llm-council
description: Convene a "council" of specialist sub-agents to adversarially review a plan, design, strategy, PR, or decision from multiple expert angles in parallel, then synthesize their critiques into one prioritized, deduplicated recommendation list. Use when the user says "ask the council", "convene the council", "get a council review", or wants multi-perspective scrutiny before committing to an approach.
---

# LLM Council

Run a panel of independent expert reviewers over a single artifact (a plan,
architecture, trading strategy, PR diff, RFC, business decision…) and return a
single synthesized verdict. The value is *diversity of perspective* plus
*adversarial scrutiny* — each member is told to find flaws, not to praise.

## When to use
- The user asks to "ask/convene the council" or wants a multi-angle review.
- A consequential decision is about to be made and you want failure modes
  surfaced before implementation.

## How to run the council

1. **Identify the artifact** under review. If it's a file (e.g. a plan in
   `/root/.claude/plans/*.md` or a PR diff), read it first so you can quote it
   to the members. If it's described in chat, summarize it crisply.

2. **Pick 3–4 council members** whose lenses fit the artifact. Default panels:
   - *Software/trading project*: *(a)* domain expert (quant/trader),
     *(b)* risk/safety reviewer, *(c)* software/systems architect,
     *(d, optional)* product/UX or security reviewer.
   - *Generic decision*: optimist, skeptic, domain expert, end-user advocate.
   - Adapt the roles to the artifact; don't force-fit.

3. **Launch the members IN PARALLEL** — a single message with one `Agent`
   (general-purpose) tool call per member so they run concurrently. Give each
   member:
   - the artifact (inline — don't assume shared file access),
   - their specific lens and 4–6 pointed questions,
   - an instruction to **be skeptical, find flaws, and return a concise,
     prioritized list of concrete critiques + recommended changes** (P0/P1/P2),
   - permission to use WebSearch/WebFetch to verify current facts when relevant.

4. **Synthesize.** When all members return, produce ONE report:
   - **Cross-cutting themes** (issues ≥2 members raised — these are highest
     signal),
   - **Prioritized findings** (P0 → P2), deduplicated across members,
   - **Concrete recommended changes** the user can act on,
   - a short **bottom line / verdict**.
   Attribute non-obvious points to the member who raised them. Don't just
   concatenate the reviews — distill them.

5. **Offer to fold accepted findings** into the artifact (e.g. update the plan
   file) if the user wants.

## Notes
- Keep members independent: do not let one member's output bias another (they
  run in parallel, blind to each other).
- Prefer 3 sharp members over 5 shallow ones.
- If the artifact is underspecified, ask the user 1–2 clarifying questions
  before convening, so the council reviews the right thing.
