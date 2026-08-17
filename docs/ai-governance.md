# AI Governance

EPOS Lite uses GPT-4o (Azure OpenAI) under strict governance. The guiding principle is:

> **Deterministic Python calculates facts. GPT-4o explains facts. Humans review and approve.**

## What GPT-4o may and may not do
**May:** summarise and explain validated facts; draft executive and engineering summaries;
group findings; suggest human-review next steps; classify a raw question into an approved intent;
extract a project, change request, or domain selector for deterministic validation; explain selected
allowlisted documentation; choose which read-only lookups answer a question, with every argument
limited to recorded values.

**May not:** calculate health/confidence scores; forecast dates; identify dependencies by
guessing; create or edit any record; change risk status; execute actions; make autonomous
decisions; state any fact not present in the supplied evidence.

## Grounding (evidence packaging)
- The app never sends the whole dataset. `ai_assistant` first selects a small, **validated**
  evidence package of typed records relevant to the question.
- The system prompt instructs the model to use **only** supplied source records and to return the
  **source IDs** that support each statement.
- Semantic classification receives the raw question plus approved intent and portfolio
  vocabularies. It receives no scores and is instructed not to answer. All returned selectors are
  checked against the loaded portfolio.
- Product-knowledge answers receive at most six chunks from an explicit documentation allowlist,
  plus a static source-tree test inventory. The inventory explicitly does not claim test execution
  or success.

## Understanding restrictions ("only tech projects")

Enterprise assistants turn a request into a structured query and show that query back before
relying on it: Microsoft's Azure OpenAI chat reference sample rewrites the question into a search
query with filters and shows it in a "thought process" panel; Jira's natural-language search shows
the JQL it generated; self-querying retrievers let a model choose metadata filters only from a
declared attribute schema. EPOS follows the same pattern, with one addition: a restriction that
cannot be expressed in recorded values is reported, never dropped.

1. **Slot filling before routing.** `api/services/project_query.py` recognises project
   restrictions deterministically: domain (full name, name token, or a small documented set of
   umbrella words such as *tech*), phase, business priority, project manager, calculated health
   band, project-name keyword, exclusions ("except", "not managed by"), and "top N worst"
   ordering. Intent matching then runs on the question with those words removed, so "list projects
   in execution phase" is no longer mistaken for an executive report and "list high priority
   projects" is no longer an attention analysis.
2. **Model interpretation within an allowlist.** When a restriction is an interpretation or could
   not be matched, the semantic classifier may return a `project_filter`. Its JSON schema is built
   per request with `enum` lists of the domains, phases, priorities and managers actually recorded,
   so the model can only choose real values. Python validates every value again. Literal matches in
   the text outrank the model; an empty or invalid model reply never removes the user's
   restriction.
3. **Deterministic execution.** The filters are applied in Python to the authorised portfolio.
   Health bands and health ordering come from the health engine, never from the model. The same
   filter narrows any portfolio question ("which high priority projects need attention?", "risks
   in tech projects").
4. **Shown back and correctable.** Every answer carries `applied_filters` (with `interpreted_from`
   when a word was read as recorded values) and `unapplied_filters`. The interface shows them as
   chips; an interpretation is also stated in the answer ("“tech” is not a recorded domain, so it
   was read as Digital Engineering, Embedded Software and IT Systems") with a "List all projects"
   follow-up. A restriction EPOS cannot honour produces "I couldn't match … to a recorded domain,
   phase, business priority, project manager or health band, so no projects are listed" and the
   recorded values instead of a wider answer.
5. **Carried into follow-ups.** The validated query is saved with the conversation turn, so
   "what about those projects' risks?" keeps the same scope.

The explanation prompts also ask for the direct answer first, specific findings about named
records, no generic advice, and a plain statement when the evidence cannot answer part of the
question.

## Model-planned assistant (production default)

People rarely phrase questions the way fixed rules expect: "which one is the worst", "and the
second one", "whats due friday", "was ist heute dringend". In production, Ask EPOS therefore lets
the model understand the question while Python keeps every fact
(`api/services/copilot_agent.py`).

1. **Plan.** The model receives the latest message, the last eight conversation turns, today's
   date and weekday, the page scope, the caller's name and role, the tool catalogue and a data
   dictionary built from the caller's own records. The dictionary lists each record type with its
   meaning, record count, main date and owner fields, and every field a query can use: its type,
   the recorded values of short categorical fields, the range of number fields, and which fields
   Python derives. The model returns up to four tool calls and the language to reply in, under a
   strict schema built per request: project, person, dependency and change-request arguments are
   `enum` lists of the values recorded in the caller's snapshot. Python validates every argument
   again, drops anything unknown, and keeps only the arguments the chosen tool reads. There is no
   list of topics or question types: tools are described by what they return. Earlier replies
   are passed only as short summaries for resolving references such as "it" or "that one"; they
   are never evidence.
2. **Run.**
   - `find_records` is a general query over every record type the caller may see: conditions on
     any field (all of, or any of: equals, contains, one of, comparisons, empty), owner, projects,
     a window on the main date, the open, overdue, blocked and unowned switches, links between
     records (one hop, through trace links and dependencies), ordering, grouping by any field,
     owner, project or record type, and counts, totals, averages, medians, minimums and maximums,
     with the highest and lowest groups named. Python derives days overdue and until due, slip,
     exposure, utilisation, hours over and under capacity, the number of linked records of each
     type, a word-search field, and each project's health, confidence and attention flag from the
     same engines as the rest of EPOS. Each result states in plain words what it covers, for
     example "6 task records, among 6 blocked task records, where completion_percent greater than
     0", so the answer can say exactly what a figure is over.
   - A query can build on another: `within` keeps only the records an earlier search matched and
     `linked_to` follows links from them. The earlier search may belong to the same answer, to
     the previous one, or, when named exactly, to an older answer the conversation still shows.
     Each answer records its searches with their names, sizes and descriptions, and up to 60
     identifiers of the records it showed, so "which of those are blocked" keeps exactly the
     records the person was shown, limited to those they can still see.
   - Queries run exactly as planned. A condition on an unknown field, or a reference that cannot
     be resolved, returns nothing with the reason and the fields that can be used; it is never
     dropped, because dropping it would silently widen the answer. An empty result states which
     single condition emptied it, and records pointed at by `within` that fail the other
     conditions are shown as not matched, so the answer can say which condition they fail. Two
     reinterpretations are automatic, used only when the literal reading matches nothing, and
     the result reports them: a word that matches no record's text but names a project is read
     as that project, and records linked to records of their own type are read as those records.
     A third is structural and also reported: in a search over every record type, conditions on
     one type's main date, such as a task's planned end date, become one date window applied to
     each record type's own main date, so "anything due Friday" also finds actions and
     milestones rather than tasks alone.
   - The calculated analyses (portfolio overview, project status, early warnings, gate readiness,
     change impact, what-if, change history and the weekly report) reuse the engines above. Gate
     readiness uses the same calculation as the Gates page, and "what changed" reads the audit
     history behind the project change view. Scores reach the model already formatted as the
     interface shows them, and sign-in addresses never reach it. Tools the role lacks, such as
     scenarios or the weekly report, are not offered.
3. **Answer.** The model writes the reply from the tool results alone, in the planned language,
   and says when the results do not answer the question rather than filling the gap from general
   knowledge. It may ask once for up to three more lookups, for example to correct a failed
   lookup or to fetch a count no result states, and then writes the reply from all the results.
   It must not count, total or subtract: every number comes from a result. Citations outside the
   returned records are removed, and any identifier or decimal figure in the prose that the
   results do not contain (a rounding within 0.05 is accepted) rejects the whole reply. A
   rejected reply is replaced by the calculated results with a warning. Alert keys and bracketed
   citation lists are stripped before anyone reads the text, and the model's own wording is kept
   rather than rewritten by the label vocabulary. A plan or reply that runs out of tokens, which
   happens only when the model loops, is asked for once more.

Secret-seeking and instruction-override wording never reaches the assistant; the rule-based
refusal answers it. If planning fails, the rule-based pipeline answers instead.
`EPOS_ASSISTANT_MODE=classic` selects the rule-based pipeline everywhere; outside production it is
the default, so automated tests stay deterministic.

## Model roles

1. **Semantic classifier:** strict `epos_semantic_route` output; chooses only allowlisted intents
   and nullable selectors. No user-facing prose from this call is displayed.
2. **Evidence explainer:** strict `copilot_response` output over deterministic engine evidence.
3. **Documentation explainer:** strict `epos_knowledge_answer` output over allowlisted chunks and
   metadata.
4. **Workspace evidence explainer:** strict `epos_workspace_answer` output over one deterministically
  selected record type, its validated filters, and an application-calculated matched count.

All four use `temperature: 0`, the same 30-second, secret-safe transport boundary, and independent
Pydantic validation. Transport, parse, or validation failure degrades without affecting
deterministic features.

### Shared transport boundary (`complete_structured`)
- **Bounded output.** Every request carries `max_tokens`: 1,500 for explanations and 400 for
  classification. A reply that stops at the limit (`finish_reason: "length"`) is rejected as
  truncated and is never repaired. A reply withheld by the service content filter is rejected too.
- **Classified failures.** A timeout, an HTTP refusal, and any other transport failure all keep the
  public `error` status, but carry distinct internal failure kinds and warnings. A timeout reports
  "Request timed out", and an HTTP refusal reports only its status code, for example
  "Request failed with HTTP 429." Response bodies and exception messages are never surfaced.
- **One short retry.** When a busy deployment answers HTTP 429 or 503 and asks for a wait of at
  most four seconds (`retry-after-ms` or `retry-after`), the request is sent once more after that
  wait. A longer requested wait, or a second refusal, fails at once.
- **Connection reuse.** The default transport keeps one pooled `requests.Session` per worker
  thread, so repeat calls reuse TLS connections. The API key is sent per request in a header and
  is never stored on the session. An injected transport bypasses the session entirely.
- **Token usage** from the reply is captured for tracing. Non-integer usage values are ignored.

### Observability
Each `/copilot/ask` request opens a trace and returns its random ID in the `X-EPOS-Trace-Id`
response header. When the request ends, one `epos.ai.trace` INFO line records the following:
- stage timings: semantic classification, evidence build, answer
- per model call: schema name, status, failure kind, elapsed time, prompt size, token counts

The trace never contains the question, evidence, model output, headers, endpoint, or credentials.
The line is emitted only when INFO logging is enabled for that logger. Alembic's logging setup at
startup no longer disables application loggers, so AI failure warnings reach the server log.

Dependency-delay scenario requests are classified by the model but calculated only by the existing
scenario engine after dependency, delay bounds, and `scenario.run` permission are validated. The
result is deterministic and is not sent back to a model for recalculation.

## Structured output
Every response is validated into a strict `CopilotResponse`:
- `executive_summary: str`
- `key_findings: list[str]`
- `recommended_actions: list[str]`
- `source_ids: list[str]`
- `human_review_required: bool`
- `disclaimer: str`

Two further fields, `status` and `warnings`, are **set by the application, never by the model**.
The JSON schema sent to Azure declares only the six model-authored fields above, with
`additionalProperties: false` and `strict: true`.

**Confirmed response-format mode:** this project sends
`response_format: {"type": "json_schema", "json_schema": {"name": "copilot_response",
"strict": true, "schema": ...}}` with `temperature: 0`. This mode has been **manually verified
working against the project's real Azure OpenAI deployment**. No `json_object` fallback is
implemented, because none is needed for this deployment and untested speculative code was
deliberately avoided. Structured-output support is defence in depth, not the only safeguard: the
reply is independently validated against `CopilotResponse` and every returned source ID is checked
against the evidence, so a model that ignored the schema would still be caught and rejected safely.

## Implementation (`src/ai_assistant.py`)
- **Supported question types** (seven): projects needing attention, why a project is in its band,
  risks without a mitigation owner, milestones at risk, requirements lacking verification evidence,
  what a change request affects, and a weekly executive update. Anything else raises a clear error.
- **Evidence packages** are built only from the deterministic engines
  (`calculate_project_health`, `calculate_project_confidence`, `generate_early_warnings`,
  `generate_portfolio_early_warnings`, `calculate_change_impact`) plus the specific underlying
  records those results reference by ID. The whole portfolio is never sent.
- **Injectable transport:** `ask_epos(..., transport=...)` accepts a callable
  `(url, headers, payload, timeout) -> dict`. The default posts to the configured endpoint; every
  automated API test disables live Azure by default and model tests inject a fake, so the suite
  never contacts the real API. Live evaluation is a separate manual command.
- **Status handling:** `ask_epos` always returns a `CopilotResponse`. `status` is one of
  `ok`, `unavailable` (configuration missing), `error` (request failed or timed out; the warning
  says which), or `invalid_response` (output did not match the schema, was truncated or filtered,
  or could not be grounded). No AI failure raises out of the call.
- **Fabricated source IDs:** if any `source_id` is not present in the evidence package that was
  sent, **the whole response is rejected** as `invalid_response`. Its summary, findings and actions
  are discarded, and the rejected IDs are recorded in `warnings`. The calculated evidence stays
  visible. Partial acceptance is deliberately not offered: `source_ids` belongs to the response
  as a whole, not to individual claims, so when one citation is fabricated there is no way to know
  which sentence it was meant to support.
- **Identifiers in prose:** every record-identifier-shaped token written in the summary, findings
  or actions, such as `P-002` or `CR-042`, must appear in the evidence that was sent. Otherwise
  the whole response is rejected. This closes the gap where a reply cites a genuine record while
  naming an invented one in its text. Scenario explanations additionally reject numbers that are
  absent from the deterministic result.
- **Empty evidence is never explained.** When a supported question matches no records, the API
  answers deterministically and makes no model call. Narrating an empty package invites invention.
- **Secrets:** the API key is read only by name from the environment and is never logged, echoed or
  included in any message. Error messages name the missing variable (for example
  "API_KEY is not configured") and never any value. `.env` is never read for display.
- **Timeout:** 30 seconds, surfaced as the `error` status with a "Request timed out" warning. The
  API then shows the calculated evidence without an AI narrative.
- **Evidence is built once per API request.** The Ask EPOS API builds the package a single time;
  that same object is both displayed and sent for explanation (`ask_epos(..., evidence=...)`).
  An exactly selected advertised question skips semantic classification when the local rules
  agree on its intent, because its fixed wording carries no selector to extract.
- **Product-knowledge sources are cached** and keyed by each file's modification time and size.
  An edited document or test file is reread on the next question, with no restart required.
- **Streamlit evidence is rebuilt on every render, deliberately.** Unlike the cached deterministic pages, the
  Ask EPOS page does not cache its evidence construction. This is intentional: the evidence handed
  to the model must always reflect the current state of the deterministic results, because the
  entire grounding guarantee rests on the AI explaining exactly what the dashboard shows. The cost
  is two additional deterministic engine calls per render on the two-project portfolio
  (one per project), which is sub-second and acceptable at Version 1 scale. This is accepted
  behaviour, not a defect, and is measured by `tests/test_caching.py`.

Validation rules:
- Response must be parseable JSON matching the schema, else it is rejected safely.
- **Every `source_id` must exist in the supplied evidence package**; unknown IDs are rejected.
- `disclaimer` must equal `AI-generated decision-support draft; human review required.`

## Human oversight & approval
- All AI output is displayed as a **draft** with the standard disclaimer and a human-review
  warning, inside a visually distinct bordered container, with the deterministic evidence shown
  first.
- **Version 1 does not persist an approval decision.** A reviewer reads the draft alongside its
  evidence and acts outside the tool. A stored approve/edit/reject log is Version 2 scope; the
  earlier `approval_log.py` placeholder has been removed rather than left as an empty module.

## Error handling & privacy
- Missing `API_KEY`/`ENDPOINT` ⇒ show the safe message:
  *"AI capability is unavailable because Azure OpenAI configuration is missing. Core deterministic
  portfolio analysis remains available."* Deterministic features keep working.
- Network failures and malformed/unsupported responses are caught and reported readably; the app
  never crashes.
- The API key is read only from the environment; it is never logged, echoed or written to disk.
- `.env` is never read for display, never overwritten, and is git-ignored.

## Testing the AI layer
- Tests never call the real API. A mock/injected transport returns canned responses.
- Tests cover: missing configuration handled safely; malformed response handled safely; and the
  rule that all AI `source_ids` must exist in the supplied evidence package.
- `tests/test_ai_transport.py` pins the transport boundary. It covers:
  - token limits
  - timeout, HTTP, truncation, filter and malformed-body classification
  - secret-free warnings
  - token usage capture
  - per-thread session reuse
  - trace content
  - prose-identifier grounding
- `tests/api/test_copilot_pipeline.py` runs every analytical intent through the real orchestration.
  It checks that each accepts a grounded reply, builds evidence exactly once, and rejects each of
  these replies:
  - fabricated citations
  - invented identifiers in prose
  - missing citations
  - extra properties
  - malformed JSON
  - truncated replies

  It also checks that the model cannot waive review or rewrite the disclaimer, and that timeouts
  and HTTP 503 fall back to calculated facts. Further cases cover the model-call budget, false
  project scoping, prompt injection in questions and in record text, knowledge-cache invalidation,
  and the trace header.
- `scripts/benchmark_ai_pipeline.py` is an offline benchmark over the 238-question evaluation
  corpus. Its counts and local timings are measured through a fake transport. Its end-to-end
  latency is **simulated** from a stated cost model and is not a live Azure measurement.

## Live Verification
Performed **2026-08-26** against the project's real Azure OpenAI deployment using
`scripts/live_verify_ai.py`. This is separate from the automated suite, which is always mocked and
never touches the network. The script lives outside `tests/` precisely so `pytest` cannot collect
it, and it must be run manually by someone holding their own credentials.

All **seven** supported question types were exercised once each against the live endpoint, plus one
additional minimal-evidence observation. Result: **7 of 7 passed** every criterion.

| Question type | Status | Result |
|---------------|--------|--------|
| projects_needing_attention | ok | PASS |
| why_project_band | ok | PASS |
| risks_without_owner | ok | PASS |
| milestones_at_risk | ok | PASS |
| requirements_without_verification | ok | PASS |
| change_request_impact | ok | PASS |
| weekly_executive_update | ok | PASS |

Criteria applied to each call: the reply parsed and validated as a `CopilotResponse`; the
disclaimer matched the required text exactly; at least one `source_id` was returned; every returned
`source_id` existed in the evidence package that was sent; and `human_review_required` was true.

Notable observations:
- **No fabricated source IDs were returned in any call**, so the filtering safeguard never had to
  remove anything and no grounding warning was raised.
- The `json_schema` structured-output mode was accepted by the deployment on every call; no schema
  or response-shape mismatch occurred.
- The model correctly used only supplied facts, for example citing the 51-day stale status of
  P-007 and the 15 calendar-day estimate for CR-042, both of which came from the evidence rather
  than from the model.
- **Minimal-evidence scenario:** the sparsest question (`risks_without_owner`, two alert records
  plus two risk records) still grounded correctly. The model returned no unsupported identifiers
  and added no content beyond the supplied evidence.

No issue was found, so no change was made to `src/ai_assistant.py` as a result of this run.
