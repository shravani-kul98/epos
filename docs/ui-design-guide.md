# EPOS UI design guide

AI-generated decision-support draft; human review required.

## Active product: EPOS Next

The React application is the active interface. Its design system is implemented, not a set of
mockups. Preserve FastAPI authorization, resource scope, concurrency tokens, deterministic engine
outputs, source records and the legacy Streamlit entry point.

### Foundations and tokens

- `frontend/src/styles/tokens.css` is the only frontend raw-color source. Light mode uses cool
  neutral surfaces, a navy navigation rail and cobalt controls; dark mode has independently chosen
  navy/slate surfaces, lighter accents and contrasting action text. It is not a color inversion.
- Semantic colors: healthy/complete green, attention amber, elevated orange, critical red,
  schedule blue, requirements violet, traceability indigo, verification emerald, scenarios teal,
  capacity cyan, AI explanations purple, governance slate. Text and icons accompany status colors.
- Typography: page title 26px, section 18px, card 15px, body/table 14px, metadata/identifiers 13px,
  KPI 30px. Font family, sizes and line heights are shared CSS tokens. Tabular numerals apply to
  tables, dates, numeric inputs and explicit figures. Project names lead; IDs are supporting context.
- Layout: 248px expanded / 72px compact navigation; 64px header; 24px page and 32px section spacing;
  8px controls / 12px surfaces / 16px overlays. Breakpoints are centralized in Tailwind configuration:
  640, 768, 1024, 1280 and 1536px. Analytical views use the available content width.
- Most surfaces have borders without shadows. Only raised/overlay surfaces use elevation. Motion
  uses shared short durations. Reduced-motion CSS removes transitions, pulsing and smooth scrolling.
- `cn()` explicitly recognizes EPOS typography tokens so class merging cannot discard a semantic
  foreground color when a text-size class follows it. Regression tests cover every named size.

### Shell and page structure

- Navigation groups are Analysis, Execution, Governance, Engineering and Administration. Only
  implemented routes are linked. Execution subviews (projects, blocked items, actions) share the
  Projects route; project tabs contain delivery, gates, assumptions, capacity and audit detail.
- The desktop rail has visible active state and an accessible collapsed mode. Mobile navigation is
  a modal with focus containment, Escape, background isolation and focus restoration.
- The top bar provides breadcrumbs, search, role/account, true portfolio alert count, theme control
  and the permitted create action. Notification previews state their limit; they are not the total.
  An unavailable/loading summary is never announced as zero alerts. Onboarding describes a local
  preference, not an unimplemented home-page rearrangement. Missing routes retain a page heading
  and a single keyboard-operable recovery action, without nested interactive elements.
- `PageHeader` reads explicit/context scope and the API analysis date. The date is not presented as
  today's date. Project tabs have a compact mobile selector instead of an overflowing strip.
- Position comes first, attention second, analysis third, records/evidence afterward. Working,
  assumptions and methodology are disclosed on demand. Avoid a card inside every other card.

### Shared interaction patterns

| Pattern | Implementation and use |
| --- | --- |
| Section / StatTile | Named page regions and compact actionable position strips. |
| MetricCard | Label, authoritative value, optional unit, context and route/filter action. |
| StatusBadge | Text + icon + semantic color; exact trace-state mapping distinguishes “Not verified” from “Verified”. |
| AttentionList | Existing engine order, project/manager context, severity, explanation, source IDs and project navigation. No invented alert age or owner. |
| FilterBar / useViewParams | Scoped controls, clear action and copyable URL. Unrelated query parameters survive changes. |
| DataTable | Search, clear, sortable headers with `aria-sort`, 15-row client paging, bounded scroll, sticky header, named keyboard row actions and distinct loading/empty/error states. |
| Field | Associated label, required marker, hint/error IDs, `aria-describedby`, `aria-invalid`; works with text, password, select and multiline controls. |
| Drawer / useModalFocus | Portal-based modal, focus trap/restoration, scroll lock, nested layers, sticky actions and optional dirty/busy guards. |
| EvidenceDrawer / SourceList | Inspect exact accessible source matches or supplied evidence; never turn a guessed ID into an authorized record link. |
| MethodologyPopover | Native keyboard-operable disclosure of limitations and reading guidance; no hidden critical blocker. |
| EmptyState / ErrorState / Skeleton | Calm, specific states; failures do not render as zero/empty results. Loading does not claim a score or record count. |
| RouteErrorBoundary | Calm recovery for unavailable lazy chunks/runtime view failures; never display stack traces. |

### Data, filters and visualizations

- Portfolio filters are handled by the API over already-authorized, already-calculated results.
  Project, band, confidence, manager, phase, domain, priority, alert severity and forecast-date range
  do not modify calculation rules. Tallies and all charts share the scoped response. Tests compare
  filtered project objects byte-for-byte with the unfiltered result and verify scope cannot widen.
- Donut/phase/domain/bar/scatter selections can filter the register. Keyboard controls and table
  alternatives provide the same actions. Charts expose units, source data and honest axes.
- Risk matrix cells display the stored probability/impact coordinates and record count. Selection
  filters actual records. Cell color is not a new risk severity. Residual risk is not shown because
  the current contract has no residual-risk fields.
- Delivery timeline uses stored baseline/planned, forecast and actual dates. A missing start is a
  date marker, never an invented duration. The table includes every record; parent-child grouping
  uses only recorded links. Milestone variance comes from the API. Completed milestones are not
  labelled overdue merely because their forecast date is in the past.
- Requirements explorer groups recorded project → requirement → test links; it does not fabricate
  requirement parents. The detail matrix distinguishes linked tests from verified evidence and
  keeps missing/unknown states explicit. Source inspection uses the authorized search API.
- Capacity matrix renders supplied utilization, overload flags and hours by resource/week. Missing
  cells say “Not recorded”; no unstaffed-demand or skill-gap estimate is inferred.
- Scenario outcome leads. Baseline/scenario dates, dependency hand-offs, supplied factor changes,
  contribution waterfall and sensitivity use API facts. Waterfall connector arithmetic only places
  graphical marks; the final health score is the API value, not a sum calculated in React. The
  documented task-threshold artefact remains visible in limitations; no score is silently corrected.
- No historical curve is fabricated. Existing What Changed/report history states remain explicit
  when snapshots are insufficient. Calendar dates are labelled forecast/due/raised, not guessed
  review dates. Agenda is the mobile and text alternative.

### Governed forms and AI

- Task/risk edits retain drafts on recoverable failures, associate API field errors, prevent
  duplicate submissions, and require discard confirmation. Decisions/changes add an explicit
  confirmation step before the existing authorized, versioned endpoint is called.
- Meeting capture/review drawers protect edited content. All backend lifecycle checks remain
  authoritative. Read-only Issues/Assumptions detail does not imply new write capability.
- Gate readiness shows mandatory blockers before percentages. Null readiness is “unavailable,”
  not zero; a completion percentage cannot override a blocker or substitute for human review.
- Ask EPOS preserves each turn's project scope and history, restores failed questions, supports
  retry and separates API-declared deterministic lookups from AI explanations. Purple AI surfaces
  display the supplied human-review disclaimer and evidence. No AI action approves or edits data.

### Accessibility and responsive rules

- Every dialog/search/drawer must have a name, contained focus, Escape handling and a restored
  opener; stacked evidence dialogs must not unlock the parent or page behind them.
- Inputs need programmatic labels and hint/error relationships. Consequential forms must not
  lose user input on a network failure. Button labels remain available on narrow screens.
- Every interactive table row needs a real keyboard button; native links remain independent of
  row actions. Table headings expose sort state. Scroll regions are keyboard focusable.
- `tokens.test.ts` measures WCAG AA 4.5:1 text contrast for body/secondary/muted surfaces, status
  tints, actions and navigation in both themes; control borders require 3:1. Runtime checks must
  also verify actual composed classes, not only token values.
- Test 390px mobile, 768px tablet, 1024px laptop and 1440px desktop. Document-level horizontal
  overflow is not acceptable; complex matrices may have explicitly labelled local scroll regions.
- Prefer native disclosures and semantic landmarks. Avoid color-only status, hidden focus outlines,
  tiny metadata, blanket opacity on text, and floating tooltips with inaccessible content.

### Performance and DevOps

- Keep TanStack Query as server-state owner. Risk mutations invalidate scoped/global registers,
  filtered portfolio, reports, search and scenario inputs. Permission-denied responses never retry
  as if they were transient data errors. No optimistic score is invented.
- Routes load lazily; the shell persists between pages. Chart bundles load with analytical pages,
  not because the sign-in view exists. No new dependency or package-manager change was introduced.
- Frontend gates: `npm ci` → strict TypeScript → ESLint → production build → single-run Vitest
  with JUnit/HTML reports.
- The API serves the compiled `frontend/dist`; rebuild it after any frontend change. Keep local
  databases, test output and secrets out of version control.
- Backend gates: Black, Ruff, route authorization, fresh migrations with no drift, authenticated
  throwaway-database smoke journey, and the complete network-free test suite.

---

## Legacy EPOS Lite / Streamlit conventions

The following applies only to the retained Streamlit presentation layer; it does not override
the active React tokens, routing or interaction patterns above.

## No emojis
No emojis anywhere in the UI: not in labels, headers, button text, captions, chart titles or help
text. Icons, where used, are neutral Material icon references (for example `:material/dashboard:`),
never emoji.

## Colour palette
Muted, semantic colours are defined once as named constants in `src/ui_formatting.py` and reused;
never hardcode hex values in a page.

| Meaning | Band / severity | Colour |
|---------|-----------------|--------|
| Healthy / trustworthy | Health Green, Confidence High | muted green `#2E7D32` |
| Caution | Health Amber, Confidence Medium | amber `#ED6C02` |
| Adverse | Health Red, Confidence Low | red `#C62828` |
| Alert severity | Critical / High / Medium / Low | `#B71C1C` / `#E65100` / `#F9A825` / `#616161` |

Health and Confidence share the green/amber/red semantics; alert severities use a distinct scale so
they are not confused with band colours.

## Number and date formatting
- Scores: one decimal place (`format_score`).
- Percentages: one decimal place with a percent sign (`format_percent`).
- Dates: unambiguous `YYYY-MM-DD` (`format_date`); a missing date renders as `Not set`.

## The UI never recalculates engine facts
Pages present values already returned by `calculate_project_health`,
`calculate_project_confidence`, and `generate_early_warnings` /
`generate_portfolio_early_warnings`. Portfolio-level tallies (for example counting projects per
Health band) operate only on those returned values and live in small, unit-tested helpers in
`src/ui_formatting.py`. No scoring formula, threshold comparison, banding or alert rule is ever
duplicated in a page.

## Evidence-panel convention
An "evidence panel" is a reusable section layout for showing why a result is what it is, reused on
Project Intelligence and intended for future Requirements Traceability and Change Impact pages:
1. a section header phrased as the question it answers (for example "Why is this project in this
   Health band");
2. a factor table (Factor / Weight / Score), ordered most-penalised-first via
   `factors_by_ascending_score`;
3. the engine's `factor_explanations`, rendered verbatim;
4. a severity-grouped findings block (drivers or issues) ordered Critical, High, Medium, Low using
   `group_by_severity`, each item showing its message and source IDs as returned;
5. a clearly-labelled "Assumptions and limitations" sub-section (context, not findings).

Two evidence panels shown together must be visually distinguishable. Convention: keep the delivery
(Health) panel as a plain section and wrap the data-reliability (Confidence) panel in a bordered
container (`st.container(border=True)`), so a reader immediately sees they are two different kinds
of evidence.

## Severity ordering
Any severity-grouped content (critical drivers, data-quality issues, alerts) is always ordered
Critical, then High, then Medium, then Low, matching the ordering used across the engines.

## Trace status badge
The Requirements Traceability page labels the **observed state of the loaded records** for a
requirement's `verified_by` test link. This is a description of the data, not a verification
verdict; the verdict is the Risk engine's `requirement_missing_verification` alert, shown
separately. States and colours reuse the existing palette (no new colour scheme):

| State | Meaning | Colour |
|-------|---------|--------|
| Verified | A linked test case is Passed and has verification evidence | Green `#2E7D32` |
| Test not run | A linked test case exists and is Not Run | Medium `#F9A825` |
| Not verified | A linked test case exists but is not Passed-with-evidence | High `#E65100` |
| No linked test case | No `verified_by` link to an existing test case | Critical `#B71C1C` |

## Deterministic versus AI-generated content
Every AI-generated section must be visually distinguishable from deterministic sections. The
implemented convention on the Ask EPOS page is:
- the AI output sits inside a bordered container (`st.container(border=True)`) under an
  "AI-generated draft" subheader;
- a caption immediately states that the content below is drafted by GPT-4o from the evidence above;
- the deterministic evidence that was sent is shown **first**, in its own plain section, so a reader
  sees the facts before the explanation;
- the standard disclaimer, "AI-generated decision-support draft; human review required.", is always
  rendered inside the AI container;
- grounding warnings (for example filtered source IDs) appear inside the same container.

Reuse this pattern for any future AI surface.

## Layout and readability
- Structure pages with `st.header` / `st.subheader`, not spacing alone.
- The KPI row must remain readable at typical laptop widths without horizontal scrolling.
- Explain each first-use term (Health, Confidence, alert severity) in nearby caption or `help` text,
  because a first-time reviewer will not have read the documentation.
- Avoid decorative elements, animations and filler text. Do not truncate data silently; use an
  explicit "show more" control and state how many of how many items are shown.
