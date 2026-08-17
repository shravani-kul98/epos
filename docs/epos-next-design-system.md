# EPOS Next — Design System

The product should read as a calm, dense, professional engineering tool. Not a dashboard demo, not a
consumer app. Information density is a feature; decoration is not.

## Tone
- Neutral surfaces, restrained colour. Colour carries **meaning only** — health, confidence, severity.
- Every number is traceable to records. Nothing is shown without a way to see why.
- No emojis anywhere in the product surface.

## Colour tokens

Defined once as CSS custom properties in `frontend/src/index.css` and consumed through Tailwind.

| Token | Light | Meaning |
| --- | --- | --- |
| `--color-health-green` | `#15803d` | Health 70–100, on track |
| `--color-health-amber` | `#b45309` | Health 50–69, needs attention |
| `--color-health-red` | `#b91c1c` | Health below 50, intervention needed |
| `--color-confidence-high` | `#0f766e` | Confidence 70–100, evidence is solid |
| `--color-confidence-medium` | `#a16207` | Confidence 40–69, gaps present |
| `--color-confidence-low` | `#9a3412` | Confidence below 40, treat as unreliable |
| `--color-surface` | `#ffffff` | Cards, panels, table backgrounds |
| `--color-surface-muted` | `#f6f7f9` | App background, table striping |
| `--color-border` | `#e3e6ea` | Hairline dividers and card edges |
| `--color-sidebar` | `#111827` | Persistent left navigation |
| `--color-primary` | `#1d4ed8` | Primary actions, active nav, links |

Health and confidence colours are intentionally distinct hue families (green/amber/red versus
teal/ochre/burnt-orange) so the two scores are never confused at a glance.

Severity reuses the health ramp: Critical `--color-health-red`, High `--color-health-amber`,
Medium `--color-confidence-medium`, Low neutral text.

## Typography
- One family: `Inter`, falling back to the system UI stack.
- Scale: page title 20px/600, section 15px/600, body 14px/400, table and metadata 13px, numeric
  callouts 28px/600 with tabular figures.
- Numbers use `font-variant-numeric: tabular-nums` so columns align.

## Layout
- Persistent 240px sidebar, dark surface, grouped: **Workspace**, **Control**, **Intelligence**.
- Content max width 1440px, 24px gutters, 16px grid gap.
- Cards: 1px border, 8px radius, no drop shadow at rest.
- Tables are the primary data surface: sticky headers, 40px rows, right-aligned numerics.

## Component conventions
- **ScoreBadge** — number plus band word, coloured by band. Always shows the band, never colour alone,
  so it stays readable without colour vision.
- **EvidenceDrawer** — right-side panel listing the source records behind any conclusion. Reachable
  from every score, alert and AI answer.
- **AiDisclaimer** — fixed text `AI-generated decision-support draft; human review required.`
  rendered on every AI surface. Not dismissible.
- **EmptyState** — explains what is missing and the next action; never a bare "No data".
- Destructive actions require typed confirmation of the record id.

## Accessibility
- Contrast at least 4.5:1 for text on its surface.
- Band words accompany every colour signal.
- Full keyboard traversal; visible focus ring in `--color-primary`.
- Charts carry an adjacent table or accessible summary.
