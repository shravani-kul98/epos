import { useId, useState } from "react";

import { RequirementFormDrawer } from "@/components/requirement-form-drawer";
import { Button } from "@/components/ui/button";
import { Field, Select, TextInput } from "@/components/ui/form";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { ApiError } from "@/lib/api";
import {
  useCreateTestCase,
  useCreateTraceLink,
  useDeleteTraceLink,
  useMilestones,
  useRecordTestResult,
  useRequirementRegister,
  useTasks,
  useTestCases,
  useTraceLinks,
} from "@/lib/queries";
import type { TestCase, TestResultStatus, TraceLink, TraceTargetType } from "@/types/api";

const TARGET_TYPES: readonly TraceTargetType[] = ["Task", "TestCase", "Milestone"];
const TARGET_LABELS: Record<TraceTargetType, string> = { Task: "Task", TestCase: "Test case", Milestone: "Milestone" };
const RESULTS: readonly TestResultStatus[] = ["Passed", "Failed", "Not Run"];

interface LinkOption {
  id: string;
  name: string;
}

/** Opens the requirement record, with its version, for editing. */
export function RequirementEditAction({ projectId, requirementId }: { projectId: string; requirementId: string }): JSX.Element {
  const requirements = useRequirementRegister(projectId);
  const [editing, setEditing] = useState(false);
  const record = requirements.data?.find(item => item.requirement_id === requirementId);

  return <div className="space-y-2">
    <Button size="sm" disabled={!record || record.row_version == null} onClick={() => setEditing(true)}>
      {requirements.isLoading ? "Loading requirement" : "Edit requirement"}
    </Button>
    {requirements.isError ? <p role="alert" className="text-meta text-critical">{requirements.error.message}</p> : null}
    {requirements.data && !record ? <p className="text-meta text-ink-secondary">This requirement is not available for editing.</p> : null}
    {editing && record ? <RequirementFormDrawer projectId={projectId} requirement={record} onClose={() => setEditing(false)} /> : null}
  </div>;
}

function TestResultForm({ testCase, projectId, onSaved }: {
  testCase: TestCase;
  projectId: string;
  onSaved: (message: string) => void;
}): JSX.Element {
  const formId = useId();
  const recordResult = useRecordTestResult(projectId);
  const [status, setStatus] = useState<TestResultStatus>(() => RESULTS.find(result => result === testCase.status) ?? "Not Run");
  const [evidence, setEvidence] = useState("");
  const trimmed = evidence.trim();
  const needsEvidence = status === "Passed";
  const fieldErrors = recordResult.error instanceof ApiError ? recordResult.error.fieldErrors : {};

  async function save(): Promise<void> {
    if (testCase.row_version == null || (needsEvidence && !trimmed)) return;
    try {
      await recordResult.mutateAsync({ testCase, status, evidence: trimmed || undefined });
      onSaved(`Recorded ${status} for ${testCase.test_case_id}.`);
    } catch {
      // The refusal stays beside the result so it can be corrected.
    }
  }

  return <div id={`result-${testCase.test_case_id}`} className="mt-3 space-y-3 rounded-control border border-line bg-surface-subtle p-3">
    <Field label="Result" htmlFor={`${formId}-status`}>
      <Select id={`${formId}-status`} value={status} onChange={event => setStatus(event.target.value as TestResultStatus)}>
        {RESULTS.map(result => <option key={result} value={result}>{result}</option>)}
      </Select>
    </Field>
    <Field label="Verification evidence" htmlFor={`${formId}-evidence`} error={fieldErrors.verification_evidence}
      hint={needsEvidence ? "Required for a pass. Name the report, log or run that shows it." : "Optional. Earlier evidence is not kept with a new result."}>
      <TextInput id={`${formId}-evidence`} maxLength={500} required={needsEvidence} value={evidence} onChange={event => setEvidence(event.target.value)} />
    </Field>
    <Button size="sm" variant="primary" disabled={recordResult.isPending || testCase.row_version == null || (needsEvidence && !trimmed)} onClick={() => void save()}>
      {recordResult.isPending ? "Saving" : "Save result"}
    </Button>
    {recordResult.isError ? <p role="alert" className="text-meta text-critical">{recordResult.error.message}</p> : null}
  </div>;
}

/** The tasks, tests and milestones traced to a requirement, with the controls to maintain them. */
export function RequirementLinks({ projectId, requirementId }: { projectId: string; requirementId: string }): JSX.Element {
  const baseId = useId();
  const links = useTraceLinks(projectId);
  const tasks = useTasks(projectId);
  const testCases = useTestCases(projectId);
  const milestones = useMilestones(projectId);
  const createLink = useCreateTraceLink();
  const deleteLink = useDeleteTraceLink(projectId);
  const createTest = useCreateTestCase();
  const [linkType, setLinkType] = useState<TraceTargetType>("TestCase");
  const [targetId, setTargetId] = useState("");
  const [newTest, setNewTest] = useState("");
  const [recording, setRecording] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const options: Record<TraceTargetType, LinkOption[]> = {
    Task: (tasks.data ?? []).map(task => ({ id: task.task_id, name: task.task_name })),
    TestCase: (testCases.data ?? []).map(test => ({ id: test.test_case_id, name: test.test_case_name })),
    Milestone: (milestones.data ?? []).map(milestone => ({ id: milestone.milestone_id, name: milestone.milestone_name })),
  };
  const loading: Record<TraceTargetType, boolean> = { Task: tasks.isLoading, TestCase: testCases.isLoading, Milestone: milestones.isLoading };
  const linked = (links.data ?? []).filter(link => link.source_type === "Requirement" && link.source_id === requirementId);
  const available = options[linkType].filter(option => !linked.some(link => link.target_type === linkType && link.target_id === option.id));

  function nameOf(link: TraceLink): string | undefined {
    return options[link.target_type as TraceTargetType]?.find(option => option.id === link.target_id)?.name;
  }

  async function addLink(): Promise<void> {
    if (!targetId) return;
    setNotice("");
    try {
      await createLink.mutateAsync({ project_id: projectId, requirement_id: requirementId, target_type: linkType, target_id: targetId });
      setNotice(`Linked ${targetId} to ${requirementId}.`);
      setTargetId("");
    } catch {
      // The refusal is shown beside the control.
    }
  }

  async function removeLink(link: TraceLink): Promise<void> {
    setNotice("");
    try {
      await deleteLink.mutateAsync(link);
      setNotice(`Removed the link to ${link.target_id}.`);
      if (recording === link.target_id) setRecording(null);
    } catch {
      // The refusal is shown above the list.
    }
  }

  /** A test that does not exist yet is defined and traced in one step, so it is never orphaned. */
  async function defineAndLink(): Promise<void> {
    const name = newTest.trim();
    if (!name) return;
    setNotice("");
    try {
      const testCase = await createTest.mutateAsync({ project_id: projectId, test_case_name: name, owner: null });
      await createLink.mutateAsync({ project_id: projectId, requirement_id: requirementId, target_type: "TestCase", target_id: testCase.test_case_id });
      setNewTest("");
      setNotice(`Defined ${testCase.test_case_id} and linked it to ${requirementId}. Record its result once it has run.`);
    } catch {
      // The refusal is shown beside the control.
    }
  }

  return <section aria-labelledby={`${baseId}-heading`} className="space-y-4 border-t border-line pt-4">
    <h3 id={`${baseId}-heading`} className="text-card font-medium">Linked work and tests</h3>
    {notice ? <p role="status" className="text-meta text-ok">{notice}</p> : null}
    {deleteLink.isError ? <p role="alert" className="text-meta text-critical">{deleteLink.error.message}</p> : null}
    {links.isError ? <p role="alert" className="text-meta text-critical">{links.error.message}</p>
      : links.isLoading ? <p className="text-meta text-ink-secondary">Loading links…</p>
      : linked.length === 0 ? <p className="text-meta text-ink-secondary">Nothing is linked to this requirement yet.</p>
      : <ul className="space-y-2">
        {linked.map(link => {
          const testCase = link.target_type === "TestCase" ? testCases.data?.find(test => test.test_case_id === link.target_id) : undefined;
          const open = testCase !== undefined && recording === testCase.test_case_id;
          return <li key={link.trace_link_id} className="rounded-control border border-line px-3 py-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-body text-ink">{nameOf(link) ?? link.target_id}</p>
                <p className="text-meta text-ink-secondary">{TARGET_LABELS[link.target_type as TraceTargetType] ?? link.target_type} · <code>{link.target_id}</code></p>
                {testCase ? <div className="mt-1 flex flex-wrap items-center gap-2">
                  <StatusBadge label={testCase.status} tone={statusTone(testCase.status)} />
                  {testCase.verification_evidence ? <span className="text-meta text-ink-secondary">Evidence: {testCase.verification_evidence}</span> : null}
                </div> : null}
              </div>
              <div className="flex flex-wrap gap-2">
                {testCase ? <Button size="sm" aria-expanded={open} aria-controls={open ? `result-${testCase.test_case_id}` : undefined}
                  aria-label={`Record result for ${testCase.test_case_id}`}
                  onClick={() => setRecording(open ? null : testCase.test_case_id)}>Record result</Button> : null}
                <Button size="sm" variant="ghost" aria-label={`Remove link to ${link.target_id}`}
                  disabled={link.row_version == null || deleteLink.isPending} onClick={() => void removeLink(link)}>Remove</Button>
              </div>
            </div>
            {open && testCase ? <TestResultForm key={testCase.test_case_id} testCase={testCase} projectId={projectId}
              onSaved={message => { setNotice(message); setRecording(null); }} /> : null}
          </li>;
        })}
      </ul>}

    <div role="group" aria-labelledby={`${baseId}-add`} className="space-y-3 rounded-control border border-line p-3">
      <p id={`${baseId}-add`} className="text-meta font-semibold text-ink">Add link</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Link to" htmlFor={`${baseId}-type`}>
          <Select id={`${baseId}-type`} value={linkType} onChange={event => { setLinkType(event.target.value as TraceTargetType); setTargetId(""); createLink.reset(); }}>
            {TARGET_TYPES.map(type => <option key={type} value={type}>{TARGET_LABELS[type]}</option>)}
          </Select>
        </Field>
        <Field label="Record" htmlFor={`${baseId}-target`}>
          <Select id={`${baseId}-target`} value={targetId} disabled={loading[linkType]} onChange={event => setTargetId(event.target.value)}>
            <option value="">{loading[linkType] ? "Loading records" : available.length > 0 ? "Choose a record" : "Nothing left to link"}</option>
            {available.map(option => <option key={option.id} value={option.id}>{option.name} · {option.id}</option>)}
          </Select>
        </Field>
      </div>
      <Button size="sm" disabled={!targetId || createLink.isPending} onClick={() => void addLink()}>
        {createLink.isPending ? "Linking" : "Add link"}
      </Button>
      {createLink.isError ? <p role="alert" className="text-meta text-critical">{createLink.error.message}</p> : null}
      {linkType === "TestCase" ? <div className="space-y-2 border-t border-line pt-3">
        <Field label="Or define a new test case" htmlFor={`${baseId}-new-test`} hint="It starts Not Run and is linked to this requirement straight away.">
          <TextInput id={`${baseId}-new-test`} maxLength={200} value={newTest} onChange={event => { setNewTest(event.target.value); createTest.reset(); }} />
        </Field>
        <Button size="sm" disabled={!newTest.trim() || createTest.isPending || createLink.isPending} onClick={() => void defineAndLink()}>
          {createTest.isPending ? "Defining" : "Define and link"}
        </Button>
        {createTest.isError ? <p role="alert" className="text-meta text-critical">{createTest.error.message}</p> : null}
      </div> : null}
    </div>
  </section>;
}
