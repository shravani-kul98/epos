import { BookOpen, CornerDownRight, ExternalLink, Filter, ShieldCheck, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { CopilotAnswer } from "@/types/api";

export function CopilotAnswerCard({ answer, onOpenSources, onFollowUp, busy }: {
  answer: CopilotAnswer;
  onOpenSources: () => void;
  onFollowUp: (question: string) => void;
  busy: boolean;
}): JSX.Element {
  const guidance = answer.status === "clarification";
  const failed = !["ok", "clarification"].includes(answer.status);
  const deterministic = !answer.human_review_required;
  const heading = guidance ? "Scope guidance" : failed ? "Explanation unavailable" : deterministic ? "Calculated answer" : "AI decision-support explanation";
  return <section className={cn("copilot-answer", failed && "copilot-answer-error")} aria-label="Answer">
    <header><span className="copilot-answer-mark" aria-hidden="true">{deterministic ? <ShieldCheck size={18} /> : <Sparkles size={18} />}</span>
      <h2>{heading}</h2><span>{guidance ? "Choose the next step" : deterministic ? "From current records" : "Human review required"}</span>
    </header>
    <div className="copilot-answer-body">
      <p className="copilot-answer-summary">{answer.executive_summary}</p>
      {(answer.applied_filters?.length ?? 0) > 0 || (answer.unapplied_filters?.length ?? 0) > 0 ? <ul className="mb-3 flex flex-wrap gap-2" aria-label="Filters applied to this answer">
        {(answer.applied_filters ?? []).map(filter => <li key={`${filter.field}-${String(filter.excluded)}`} className="inline-flex items-center gap-1 rounded-full border border-line bg-surface-subtle px-2.5 py-1 text-meta text-ink">
          <Filter size={12} aria-hidden="true" />
          <span className="text-ink-secondary">{filter.label}{filter.excluded ? " excludes" : ""}:</span> {filter.values.join(", ")}
          {filter.interpreted_from ? <span className="text-ink-secondary">(read from “{filter.interpreted_from}”)</span> : null}
        </li>)}
        {(answer.unapplied_filters ?? []).map(phrase => <li key={`unapplied-${phrase}`} className="inline-flex items-center gap-1 rounded-full border border-critical/30 bg-critical-tint px-2.5 py-1 text-meta text-ink">
          Not recognised: {phrase}
        </li>)}
      </ul> : null}
      {answer.project_references && answer.project_references.length > 0 ? <div className="copilot-project-links" aria-label="Projects in this answer">
        {answer.project_references.map(project => <Link key={project.project_id} to={`/projects/${encodeURIComponent(project.project_id)}`}><ExternalLink size={13} aria-hidden="true" />{project.project_name}</Link>)}
      </div> : null}
      {answer.key_findings.length > 0 ? <div className="copilot-answer-section"><h3>Key findings</h3><ul>{answer.key_findings.map((finding, index) => <li key={`${index}-${finding}`}>{finding}</li>)}</ul></div> : null}
      {answer.recommended_actions.length > 0 ? <div className="copilot-answer-section copilot-next-steps"><h3>Recommended next steps</h3><ul>{answer.recommended_actions.map((action, index) => <li key={`${index}-${action}`}>{action}</li>)}</ul></div> : null}
      {answer.warnings.length > 0 ? <details className="copilot-answer-notes"><summary>Evidence notes · {answer.warnings.length}</summary><ul>{answer.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul></details> : null}
      {answer.suggested_questions.length > 0 ? <div className="copilot-followups">{answer.suggested_questions.slice(0, 3).map(question => <Button size="sm" key={question} disabled={busy} onClick={() => onFollowUp(question)}><CornerDownRight size={14} aria-hidden="true" />{question}</Button>)}</div> : null}
    </div>
    {!guidance ? <footer>
      {answer.evidence.length > 0 ? <Button size="sm" onClick={onOpenSources}><BookOpen size={14} aria-hidden="true" /> Sources ({answer.evidence.length})</Button> : null}
      <p>{deterministic ? "Calculated from the records you can access. No AI wrote this answer." : answer.disclaimer}</p>
    </footer> : null}
  </section>;
}