import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Field, Select, TextInput } from "@/components/ui/form";
import { PageHeader } from "@/components/ui/page-header";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { ApiError } from "@/lib/api";
import { useProjectCreateOptions } from "@/lib/people-queries";
import { useCreateProject, useCreateMilestone, useCreateRisk } from "@/lib/queries";
import { saveFeedback } from "@/lib/save-feedback";
import type { Project } from "@/types/api";

const PHASES = ["Concept", "Definition", "Development", "Validation", "Qualification", "Ramp-up"];
const PRIORITIES = ["Critical", "High", "Medium", "Low"];

// A starter suggestion prefills a first milestone name only; nothing else is created from it.
const TEMPLATES = [
  {
    id: "engineering",
    label: "Engineering delivery",
    description: "Hardware or software delivery. Suggests “Design Review Complete” as the first milestone.",
    milestone: "Design Review Complete",
  },
  {
    id: "digital",
    label: "Digital transformation",
    description: "System rollout or migration. Suggests “Pilot Go-Live” as the first milestone.",
    milestone: "Pilot Go-Live",
  },
  {
    id: "product",
    label: "Product development",
    description: "Concept to launch. Suggests “Concept Sign-Off” as the first milestone.",
    milestone: "Concept Sign-Off",
  },
  {
    id: "sustainability",
    label: "Sustainability programme",
    description: "Baselines and reporting cycles. Suggests “Baseline Established” as the first milestone.",
    milestone: "Baseline Established",
  },
  { id: "blank", label: "Blank project", description: "No suggested milestone.", milestone: "" },
] as const;

interface Draft {
  project_id: string;
  project_name: string;
  domain: string;
  project_manager: string;
  project_manager_user_id: number | null;
  business_priority: string;
  project_phase: string;
  start_date: string;
  baseline_end_date: string;
  forecast_end_date: string;
  template: string;
  milestone_name: string;
  milestone_date: string;
  risk_name: string;
  risk_probability: number;
  risk_impact: number;
}

const EMPTY: Draft = {
  project_id: "",
  project_name: "",
  domain: "",
  project_manager: "",
  project_manager_user_id: null,
  business_priority: "Medium",
  project_phase: "Definition",
  start_date: "",
  baseline_end_date: "",
  forecast_end_date: "",
  template: "engineering",
  milestone_name: "",
  milestone_date: "",
  risk_name: "",
  risk_probability: 3,
  risk_impact: 3,
};

const STEPS = ["Project basics", "Timeline and delivery", "Initial control setup", "Review and create"];

type Errors = Partial<Record<keyof Draft, string>>;

/** Suggest a reference from the name so the user never has to invent a database key. */
function suggestId(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length === 0) return "";
  const initials = words
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("");
  // Derived from the name so the suggestion stays stable while the user types.
  let hash = 0;
  for (const character of name) hash = (hash * 31 + character.charCodeAt(0)) % 900;
  return `${initials}-${String(hash + 100)}`;
}

export function ProjectCreatePage(): JSX.Element {
  const navigate = useNavigate();
  const createProject = useCreateProject();
  const createMilestone = useCreateMilestone();
  const createRisk = useCreateRisk();
  const options = useProjectCreateOptions();

  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [addingDomain, setAddingDomain] = useState(false);
  const [referenceEdited, setReferenceEdited] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [partial, setPartial] = useState<string[]>([]);
  // Once the project exists, a retry adds only what is still missing and never creates it again.
  const [created, setCreated] = useState<Project | null>(null);
  const [added, setAdded] = useState<{ milestone: boolean; risk: boolean }>({ milestone: false, risk: false });
  const selectedManager = options.data?.managers.find(person => person.user_id === draft.project_manager_user_id);

  function update<K extends keyof Draft>(key: K, value: Draft[K]): void {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function validateStep(index: number): boolean {
    const next: Errors = {};

    if (index === 0) {
      if (draft.project_name.trim().length < 3) {
        next.project_name = "Give the project a recognisable name.";
      }
      if (!/^[A-Za-z0-9-]{2,32}$/.test(draft.project_id.trim())) {
        next.project_id = "Use 2 to 32 letters, numbers or hyphens.";
      }
      if (!draft.domain.trim()) next.domain = "Domain is required.";
      else if (!addingDomain && !options.data?.domains.includes(draft.domain)) {
        next.domain = "Choose an available domain or explicitly add a new domain.";
      }
      if (!options.canLoad || options.isError || !selectedManager) {
        next.project_manager = "Choose an active registered project manager.";
      }
    }

    if (index === 1) {
      if (!draft.start_date) next.start_date = "A start date is required.";
      if (draft.baseline_end_date && draft.start_date && draft.baseline_end_date < draft.start_date) {
        next.baseline_end_date = "The target date cannot fall before the start date.";
      }
      if (draft.forecast_end_date && draft.start_date && draft.forecast_end_date < draft.start_date) {
        next.forecast_end_date = "The forecast date cannot fall before the start date.";
      }
      if (draft.milestone_name.trim() && !draft.milestone_date) {
        next.milestone_date = "Give the milestone a target date.";
      }
      if (draft.milestone_date && draft.start_date && draft.milestone_date < draft.start_date) {
        next.milestone_date = "The milestone cannot fall before the project starts.";
      }
    }

    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function goNext(): void {
    if (!validateStep(step)) return;
    setStep((value) => Math.min(value + 1, STEPS.length - 1));
  }

  async function create(): Promise<void> {
    setSubmitError(null);
    setPartial([]);
    if (!validateStep(0) || !selectedManager) {
      setStep(0);
      return;
    }

    let project = created;
    if (!project) {
      try {
        project = await createProject.mutateAsync({
          project_id: draft.project_id.trim(),
          project_name: draft.project_name.trim(),
          domain: draft.domain.trim(),
          project_manager: selectedManager.full_name,
          project_manager_user_id: selectedManager.user_id,
          start_date: draft.start_date,
          baseline_end_date: draft.baseline_end_date || null,
          forecast_end_date: draft.forecast_end_date || null,
          status_update_date: null,
          project_phase: draft.project_phase,
          business_priority: draft.business_priority,
        });
        setCreated(project);
      } catch (caught) {
        if (caught instanceof ApiError) {
          const managerError = caught.fieldErrors.project_manager_user_id ?? caught.fieldErrors.project_manager;
          if (managerError || caught.fieldErrors.domain) {
            setErrors({ project_manager: managerError, domain: caught.fieldErrors.domain });
            setStep(0);
          }
        }
        setSubmitError(
          caught instanceof ApiError && caught.status === 409
            ? "A project already uses that identifier. Choose another."
            : caught instanceof ApiError
              ? caught.message
              : "The project could not be created.",
        );
        return;
      }
    }

    // The project now exists. Any child failure below is reported rather than hidden, because
    // there is no batch endpoint and therefore no rollback. References are allocated by the API.
    const failures: string[] = [];
    const done = { ...added };

    if (draft.milestone_name.trim() && draft.milestone_date && !done.milestone) {
      try {
        await createMilestone.mutateAsync({
          project_id: project.project_id,
          milestone_name: draft.milestone_name.trim(),
          baseline_date: draft.milestone_date,
          forecast_date: draft.milestone_date,
          status: "Not Started",
          criticality: "High",
          owner: selectedManager.full_name,
        });
        done.milestone = true;
      } catch {
        failures.push("the first milestone");
      }
    }

    if (draft.risk_name.trim() && !done.risk) {
      try {
        await createRisk.mutateAsync({
          project_id: project.project_id,
          risk_name: draft.risk_name.trim(),
          probability: draft.risk_probability,
          impact: draft.risk_impact,
          status: "Open",
          mitigation_owner: selectedManager.full_name,
          mitigation_status: "Not Started",
          due_date: draft.baseline_end_date || draft.start_date,
        });
        done.risk = true;
      } catch {
        failures.push("the initial risk");
      }
    }

    setAdded(done);
    if (failures.length > 0) {
      setPartial(failures);
      return;
    }
    saveFeedback.show("Project created.");
    navigate(`/projects/${project.project_id}?created=1`, { replace: true });
  }

  const busy = createProject.isPending || createMilestone.isPending || createRisk.isPending;
  const starter = TEMPLATES.find(item => item.id === draft.template);

  return (
    <>
      <PageHeader
        title="New project"
        description="Set up the plan, first milestone and initial risks. You can change everything later."
      />

      <ol className="mb-6 flex flex-wrap gap-2" aria-label="Progress">
        {STEPS.map((label, index) => (
          <li key={label} className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold",
                index < step
                  ? "bg-ok text-ink-onstatus"
                  : index === step
                    ? "bg-accent text-ink-onaccent"
                    : "bg-surface-subtle text-ink-muted",
              )}
              aria-current={index === step ? "step" : undefined}
            >
              {index < step ? <Check aria-hidden="true" className="h-3.5 w-3.5" /> : index + 1}
            </span>
            <span
              className={cn(
                "text-meta",
                index === step ? "font-medium text-ink" : "text-ink-muted",
              )}
            >
              {label}
            </span>
            {index < STEPS.length - 1 ? (
              <span aria-hidden="true" className="mx-1 hidden h-px w-6 bg-line sm:block" />
            ) : null}
          </li>
        ))}
      </ol>

      <div className="card max-w-4xl p-5 sm:p-6">
        {step === 0 ? (
          <div className="space-y-4">
            <Field
              label="Project name"
              htmlFor="project_name"
              required
              {...(errors.project_name ? { error: errors.project_name } : {})}
            >
              <TextInput
                id="project_name"
                autoFocus
                placeholder="Supplier Decarbonisation Programme"
                value={draft.project_name}
                onChange={(event) => {
                  const name = event.target.value;
                  update("project_name", name);
                  // Keep the suggestion in step with the name until the user edits it themselves.
                  if (!referenceEdited) update("project_id", suggestId(name));
                }}
              />
            </Field>

            <Field
              label="Project reference"
              htmlFor="project_id"
              required
              hint="Letters, numbers and hyphens, for example SDP-101. It prefixes every record in the project, such as SDP-101 risks and tasks, and cannot be changed later."
              {...(errors.project_id ? { error: errors.project_id } : {})}
            >
              <TextInput
                id="project_id"
                placeholder="SDP-101"
                value={draft.project_id}
                onChange={(event) => {
                  setReferenceEdited(true);
                  update("project_id", event.target.value);
                }}
              />
            </Field>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-3">
                <Field label="Domain" htmlFor="domain" required
                  hint="Choose an existing domain you can access, or add a new one."
                  error={addingDomain ? undefined : errors.domain}>
                  <Select id="domain" value={addingDomain ? "new" : draft.domain ? `domain:${draft.domain}` : ""}
                    disabled={!options.canLoad || options.isLoading || options.isError}
                    aria-busy={options.isFetching}
                    onChange={event => {
                      const isNew = event.target.value === "new";
                      setAddingDomain(isNew);
                      update("domain", isNew ? "" : event.target.value.replace(/^domain:/, ""));
                    }}>
                    <option value="">{options.isLoading ? "Loading domains" : "Choose a domain"}</option>
                    {!addingDomain && draft.domain && !options.data?.domains.includes(draft.domain) ? (
                      <option value={`domain:${draft.domain}`} disabled>{draft.domain} — no longer available</option>
                    ) : null}
                    {(options.canLoad ? options.data?.domains ?? [] : []).map(domain => (
                      <option key={domain} value={`domain:${domain}`}>{domain}</option>
                    ))}
                    <option value="new">Add new domain…</option>
                  </Select>
                </Field>
                {addingDomain ? <Field label="New domain" htmlFor="new-domain" required error={errors.domain}>
                  <TextInput id="new-domain" required value={draft.domain}
                    onChange={event => update("domain", event.target.value)} />
                </Field> : null}
              </div>
              <Field
                label="Project manager"
                htmlFor="project_manager"
                required
                hint="Choose an active registered user with project-management permissions. Creating the project grants this person project access."
                {...(errors.project_manager ? { error: errors.project_manager } : {})}
              >
                <Select
                  id="project_manager"
                  required
                  value={draft.project_manager_user_id ?? ""}
                  disabled={!options.canLoad || options.isLoading || options.isError}
                  aria-busy={options.isFetching}
                  onChange={(event) => {
                    const manager = options.data?.managers.find(person => String(person.user_id) === event.target.value);
                    setDraft(current => ({ ...current, project_manager: manager?.full_name ?? "", project_manager_user_id: manager?.user_id ?? null }));
                  }}
                >
                  <option value="">{options.isLoading ? "Loading managers" : "Choose a project manager"}</option>
                  {draft.project_manager_user_id !== null && !selectedManager ? (
                    <option value={draft.project_manager_user_id} disabled>{draft.project_manager} — no longer available</option>
                  ) : null}
                  {(options.canLoad ? options.data?.managers ?? [] : []).map(person => (
                    <option key={person.user_id} value={person.user_id}>{person.full_name} · {person.email} · {person.role_label}</option>
                  ))}
                </Select>
              </Field>
            </div>

            {options.canLoad && options.isError ? <p role="alert" className="text-meta text-critical">{options.error.message}</p> : null}
            {options.canLoad ? <Button size="sm" disabled={options.isFetching} onClick={() => void options.refetch()}>
              {options.isError ? "Retry project options" : "Refresh project options"}
            </Button> : <p className="text-meta text-ink-secondary">Sign in with project creation permission to load domains and managers.</p>}
            {options.canLoad && !options.isLoading && !options.isError && options.data?.managers.length === 0 ? (
              <p className="text-meta text-ink-secondary">No active project managers are available. Ask a workspace administrator to review user roles.</p>
            ) : null}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Business priority" htmlFor="business_priority">
                <Select
                  id="business_priority"
                  value={draft.business_priority}
                  onChange={(event) => update("business_priority", event.target.value)}
                >
                  {PRIORITIES.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Current phase" htmlFor="project_phase">
                <Select
                  id="project_phase"
                  value={draft.project_phase}
                  onChange={(event) => update("project_phase", event.target.value)}
                >
                  {PHASES.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </Select>
              </Field>
            </div>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="space-y-4">
            <fieldset>
              <legend className="text-meta font-medium text-ink">Starter suggestion</legend>
              <p className="mt-1 text-meta text-ink-muted">
                Choose the closest kind of project to prefill a first milestone name. Nothing else is
                created, and no progress or delivery figures are set for you.
              </p>
              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {TEMPLATES.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      update("template", item.id);
                      if (item.milestone && !draft.milestone_name) {
                        update("milestone_name", item.milestone);
                      }
                    }}
                    aria-pressed={draft.template === item.id}
                    className={cn(
                      "rounded-card border p-3 text-left transition-colors",
                      draft.template === item.id
                        ? "border-accent bg-accent-tint"
                        : "border-line bg-surface hover:border-line-strong",
                    )}
                  >
                    <p className="text-body font-medium text-ink">{item.label}</p>
                    <p className="mt-0.5 text-meta text-ink-secondary">{item.description}</p>
                  </button>
                ))}
              </div>
            </fieldset>

            <div className="grid grid-cols-1 gap-3 border-t border-line pt-4 sm:grid-cols-3">
              <Field label="Start date" htmlFor="start_date" required {...(errors.start_date ? { error: errors.start_date } : {})}>
                <TextInput
                  id="start_date"
                  type="date"
                  value={draft.start_date}
                  onChange={(event) => update("start_date", event.target.value)}
                />
              </Field>
              <Field
                label="Target completion"
                htmlFor="baseline_end_date"
                {...(errors.baseline_end_date ? { error: errors.baseline_end_date } : {})}
              >
                <TextInput
                  id="baseline_end_date"
                  type="date"
                  value={draft.baseline_end_date}
                  onChange={(event) => update("baseline_end_date", event.target.value)}
                />
              </Field>
              <Field
                label="Forecast completion"
                htmlFor="forecast_end_date"
                {...(errors.forecast_end_date ? { error: errors.forecast_end_date } : {})}
              >
                <TextInput
                  id="forecast_end_date"
                  type="date"
                  value={draft.forecast_end_date}
                  onChange={(event) => update("forecast_end_date", event.target.value)}
                />
              </Field>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field
                label="First milestone"
                htmlFor="milestone_name"
                hint="Optional. Milestones drive the schedule view."
              >
                <TextInput
                  id="milestone_name"
                  placeholder="Design freeze"
                  value={draft.milestone_name}
                  onChange={(event) => update("milestone_name", event.target.value)}
                />
              </Field>
              <Field
                label="Milestone target date"
                htmlFor="milestone_date"
                {...(errors.milestone_date ? { error: errors.milestone_date } : {})}
              >
                <TextInput
                  id="milestone_date"
                  type="date"
                  value={draft.milestone_date}
                  onChange={(event) => update("milestone_date", event.target.value)}
                />
              </Field>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-5">
            <div>
              <Field
                label="First risk"
                htmlFor="risk_name"
                hint="Optional. A project with no recorded risks lowers reporting confidence rather than raising health."
              >
                <TextInput
                  id="risk_name"
                  placeholder="Supplier data quality is incomplete"
                  value={draft.risk_name}
                  onChange={(event) => update("risk_name", event.target.value)}
                />
              </Field>

              {draft.risk_name.trim() ? (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <Field label="Probability" htmlFor="risk_probability" hint="1 unlikely, 5 near certain.">
                    <Select
                      id="risk_probability"
                      value={String(draft.risk_probability)}
                      onChange={(event) => update("risk_probability", Number(event.target.value))}
                    >
                      {[1, 2, 3, 4, 5].map((level) => (
                        <option key={level} value={level}>
                          {level}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Impact" htmlFor="risk_impact" hint="1 minor, 5 severe.">
                    <Select
                      id="risk_impact"
                      value={String(draft.risk_impact)}
                      onChange={(event) => update("risk_impact", Number(event.target.value))}
                    >
                      {[1, 2, 3, 4, 5].map((level) => (
                        <option key={level} value={level}>
                          {level}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div>
            <h2 className="text-card font-semibold text-ink">Review</h2>
            <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
              {[
                ["Project", draft.project_name],
                ["Reference", draft.project_id],
                ["Domain", draft.domain],
                ["Project manager", selectedManager ? `${selectedManager.full_name} · ${selectedManager.email}` : draft.project_manager],
                ["Priority", draft.business_priority],
                ["Phase", draft.project_phase],
                ["Starter", starter?.label ?? "Blank project"],
                ["Start", formatDate(draft.start_date)],
                ["Target completion", formatDate(draft.baseline_end_date)],
                ["Forecast completion", formatDate(draft.forecast_end_date)],
                [
                  "First milestone",
                  draft.milestone_name ? `${draft.milestone_name} (${formatDate(draft.milestone_date)})` : "None",
                ],
                [
                  "First risk",
                  draft.risk_name
                    ? `${draft.risk_name} (probability ${draft.risk_probability}, impact ${draft.risk_impact})`
                    : "None",
                ],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-meta text-ink-muted">{label}</dt>
                  <dd className="mt-0.5 text-body text-ink">{value}</dd>
                </div>
              ))}
            </dl>

            <p className="mt-4 text-meta text-ink-secondary">Creating the project grants the selected manager project access.</p>

            {submitError ? (
              <p
                className="mt-4 rounded-control border border-critical/25 bg-critical-tint px-3 py-2 text-meta text-critical"
                role="alert"
              >
                {submitError}
              </p>
            ) : null}

            {partial.length > 0 ? (
              <div
                className="mt-4 rounded-control border border-warn/25 bg-warn-tint px-3 py-2 text-meta text-warn"
                role="alert"
              >
                <p className="font-medium">The project was created.</p>
                <p className="mt-0.5">
                  {partial.join(" and ")} could not be added. Try again to add only what is missing, or open
                  the project and add {partial.length > 1 ? "them" : "it"} from the workspace.
                </p>
                <Button
                  size="sm"
                  variant="secondary"
                  className="mt-2"
                  onClick={() => navigate(`/projects/${created?.project_id ?? draft.project_id.trim()}`)}
                >
                  Open project
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
          <Button disabled={Boolean(created)} onClick={() => (step === 0 ? navigate("/projects") : setStep(step - 1))}>
            {step === 0 ? "Cancel" : "Back"}
          </Button>
          {step < STEPS.length - 1 ? (
            <Button variant="primary" onClick={goNext}>
              Continue
            </Button>
          ) : (
            <Button variant="primary" onClick={() => void create()} disabled={busy}>
              {busy ? (created ? "Adding the remaining steps" : "Creating project") : created ? "Try the remaining steps again" : "Create project"}
            </Button>
          )}
        </div>
      </div>
    </>
  );
}
