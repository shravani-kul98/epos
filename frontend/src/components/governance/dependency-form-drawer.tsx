import { useId, useState } from "react";

import { MutationError } from "@/components/governance/lifecycle-section";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { useCreateDependency, useMilestones, useTasks } from "@/lib/queries";
import type { Dependency, DependencyEndpointType } from "@/types/api";

type Relationship = NonNullable<Dependency["relationship_type"]>;

const ENDPOINTS: readonly DependencyEndpointType[] = ["Task", "Milestone", "Supplier", "External", "Customer"];
const RELATIONSHIPS: readonly Relationship[] = ["Finish-to-Start", "Start-to-Start", "Finish-to-Finish", "Start-to-Finish"];
const STATUSES: readonly string[] = ["On Track", "At Risk", "Delayed", "Blocked"];
const CRITICALITIES: readonly string[] = ["Critical", "High", "Medium", "Low"];

function isInternal(type: DependencyEndpointType): boolean {
  return type === "Task" || type === "Milestone";
}

/** Record a hand-off the plan depends on. EPOS rejects cycles and duplicate edges. */
export function DependencyFormDrawer({ projectId, onClose, onSaved }: {
  projectId: string;
  onClose: () => void;
  onSaved?: (dependency: Dependency) => void;
}): JSX.Element {
  const formId = useId();
  const tasks = useTasks(projectId);
  const milestones = useMilestones(projectId);
  const create = useCreateDependency();
  const [name, setName] = useState("");
  const [predecessorType, setPredecessorType] = useState<DependencyEndpointType>("Task");
  const [predecessorId, setPredecessorId] = useState("");
  const [successorType, setSuccessorType] = useState<"Task" | "Milestone">("Milestone");
  const [successorId, setSuccessorId] = useState("");
  const [relationship, setRelationship] = useState<Relationship | "">("Finish-to-Start");
  const [lag, setLag] = useState("0");
  const [status, setStatus] = useState("On Track");
  const [delay, setDelay] = useState("0");
  const [criticality, setCriticality] = useState("High");
  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};
  const internal = isInternal(predecessorType);
  const options = (type: DependencyEndpointType) => type === "Task"
    ? (tasks.data ?? []).map(task => ({ id: task.task_id, name: task.task_name }))
    : (milestones.data ?? []).map(milestone => ({ id: milestone.milestone_id, name: milestone.milestone_name }));
  const lagValue = lag.trim() === "" ? null : Number(lag);
  const delayValue = Number(delay);
  const scheduleComplete = relationship !== "" && lagValue !== null && Number.isInteger(lagValue);
  const scheduleValid = internal ? scheduleComplete : relationship === "" ? lag.trim() === "" : scheduleComplete;
  const canSave = Boolean(name.trim() && predecessorId.trim() && successorId)
    && scheduleValid && Number.isInteger(delayValue) && delayValue >= 0 && !create.isPending;
  const dirty = Boolean(name || predecessorId || successorId);

  async function save(): Promise<void> {
    if (!canSave) return;
    try {
      const dependency = await create.mutateAsync({
        project_id: projectId,
        predecessor_type: predecessorType,
        predecessor_id: predecessorId.trim(),
        successor_type: successorType,
        successor_id: successorId,
        dependency_name: name.trim(),
        relationship_type: relationship === "" ? null : relationship,
        lag_days: relationship === "" ? null : lagValue,
        status,
        delay_days: delayValue,
        criticality,
      });
      onSaved?.(dependency);
      onClose();
    } catch {
      // Server validation stays beside the entered values.
    }
  }

  return <Drawer open onClose={onClose} dirty={dirty} busy={create.isPending} title="Add dependency"
    description="Something this project's work waits on. It feeds dependency health and scenario analysis."
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={!canSave}>{create.isPending ? "Saving" : "Add dependency"}</Button></>}>
    <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <Field label="Dependency" htmlFor={`${formId}-name`} error={fieldErrors.dependency_name} hint="For example Supplier sample delivery before qualification.">
        <TextInput id={`${formId}-name`} required maxLength={300} value={name} onChange={event => setName(event.target.value)} />
      </Field>
      <fieldset className="space-y-3 rounded-control border border-line p-3">
        <legend className="px-1 text-meta font-medium text-ink">Predecessor · must happen first</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Type" htmlFor={`${formId}-predecessor-type`} error={fieldErrors.predecessor_type}>
            <Select id={`${formId}-predecessor-type`} value={predecessorType} onChange={event => {
              const next = event.target.value as DependencyEndpointType;
              setPredecessorType(next);
              setPredecessorId("");
              if (!isInternal(next)) { setRelationship(""); setLag(""); } else if (relationship === "") { setRelationship("Finish-to-Start"); setLag("0"); }
            }}>
              {ENDPOINTS.map(value => <option key={value} value={value}>{value}</option>)}
            </Select>
          </Field>
          <div className="sm:col-span-2">
            {internal ? <Field label="Record" htmlFor={`${formId}-predecessor`} error={fieldErrors.predecessor_id}>
              <Select id={`${formId}-predecessor`} required value={predecessorId} onChange={event => setPredecessorId(event.target.value)}>
                <option value="">Choose a {predecessorType.toLowerCase()}</option>
                {options(predecessorType).map(option => <option key={option.id} value={option.id}>{option.name} · {option.id}</option>)}
              </Select>
            </Field> : <Field label="Reference" htmlFor={`${formId}-predecessor`} error={fieldErrors.predecessor_id}
              hint="The supplier, customer or external party's own reference.">
              <TextInput id={`${formId}-predecessor`} required maxLength={100} value={predecessorId} onChange={event => setPredecessorId(event.target.value)} />
            </Field>}
          </div>
        </div>
      </fieldset>
      <fieldset className="space-y-3 rounded-control border border-line p-3">
        <legend className="px-1 text-meta font-medium text-ink">Successor · waits on it</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Type" htmlFor={`${formId}-successor-type`} error={fieldErrors.successor_type}>
            <Select id={`${formId}-successor-type`} value={successorType} onChange={event => { setSuccessorType(event.target.value as "Task" | "Milestone"); setSuccessorId(""); }}>
              <option value="Task">Task</option>
              <option value="Milestone">Milestone</option>
            </Select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Record" htmlFor={`${formId}-successor`} error={fieldErrors.successor_id}>
              <Select id={`${formId}-successor`} required value={successorId} onChange={event => setSuccessorId(event.target.value)}>
                <option value="">Choose a {successorType.toLowerCase()}</option>
                {options(successorType).map(option => <option key={option.id} value={option.id}>{option.name} · {option.id}</option>)}
              </Select>
            </Field>
          </div>
        </div>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Relationship" htmlFor={`${formId}-relationship`} error={fieldErrors.relationship_type}
          hint={internal ? "Required between two planned records." : "Optional for an outside party; record it with a lag or not at all."}>
          <Select id={`${formId}-relationship`} value={relationship} onChange={event => {
            const next = event.target.value as Relationship | "";
            setRelationship(next);
            if (next === "") setLag(""); else if (lag.trim() === "") setLag("0");
          }}>
            {internal ? null : <option value="">Not recorded</option>}
            {RELATIONSHIPS.map(value => <option key={value} value={value}>{value}</option>)}
          </Select>
        </Field>
        <Field label="Lag (days)" htmlFor={`${formId}-lag`} error={fieldErrors.lag_days} hint="Negative for a lead.">
          <TextInput id={`${formId}-lag`} type="number" step={1} disabled={relationship === ""} required={relationship !== ""} value={lag} onChange={event => setLag(event.target.value)} />
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Status" htmlFor={`${formId}-status`} error={fieldErrors.status}>
          <Select id={`${formId}-status`} value={status} onChange={event => setStatus(event.target.value)}>
            {STATUSES.map(value => <option key={value} value={value}>{value}</option>)}
          </Select>
        </Field>
        <Field label="Current delay (days)" htmlFor={`${formId}-delay`} error={fieldErrors.delay_days}
          hint="Counts towards health and alerts. It does not move the successor's forecast; update that date on the milestone or task.">
          <TextInput id={`${formId}-delay`} type="number" min={0} step={1} required value={delay} onChange={event => setDelay(event.target.value)} />
        </Field>
        <Field label="Criticality" htmlFor={`${formId}-criticality`} error={fieldErrors.criticality}>
          <Select id={`${formId}-criticality`} value={criticality} onChange={event => setCriticality(event.target.value)}>
            {CRITICALITIES.map(value => <option key={value} value={value}>{value}</option>)}
          </Select>
        </Field>
      </div>
      <MutationError error={create.error} />
    </form>
  </Drawer>;
}
