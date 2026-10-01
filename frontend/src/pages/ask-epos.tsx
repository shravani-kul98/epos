import { useEffect, useRef, useState } from "react";
import { ArrowUp, Clock3, Database, History, MessageSquareText, Plus, Search, Sparkles, Trash2 } from "lucide-react";
import { CopilotAnswerCard } from "@/components/copilot-answer";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/shadcn/empty";
import { Button } from "@/components/ui/button";
import { ProgressFoldButton } from "@/components/godui/progress-fold-button";
import { EvidenceDrawer } from "@/components/ui/evidence-drawer";
import { ErrorState } from "@/components/ui/error-state";
import { Select, TextArea, TextInput } from "@/components/ui/form";
import { PageHeader } from "@/components/ui/page-header";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useAskCopilot, useConversation, useConversations, useCopilotQuestions, useDeleteConversation, usePortfolio } from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";
import type { CopilotAnswer, ConversationDetail, EvidenceRecord } from "@/types/api";

interface Turn {
  id: number;
  question: string;
  scope: string;
  projectId: string;
  conversationId: number | null;
  answer?: CopilotAnswer;
  error?: string;
  savedAt?: string;
}

function positiveId(value: string | null): number | null {
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function savedTurns(detail: ConversationDetail, nameFor: (id: string) => string): Turn[] {
  const turns: Turn[] = [];
  for (const message of detail.messages) {
    if (message.role === "user") turns.push({ id: message.id, question: message.content,
      projectId: detail.project_id ?? "", scope: "Saved conversation", conversationId: detail.id, savedAt: message.created_at });
    else if (message.role === "assistant" && turns.length > 0) {
      const previous = turns[turns.length - 1]!;
      const answer = message.answer ?? undefined;
      const projectId = answer?.context?.project_id ?? "";
      previous.answer = answer;
      previous.projectId = projectId;
      previous.scope = projectId ? nameFor(projectId) : "Portfolio context";
      if (!answer) previous.error = "This older answer is incomplete. Ask the question again to review current evidence.";
    }
  }
  return turns;
}

export function AskEposPage(): JSX.Element {
  const portfolio = usePortfolio();
  const questions = useCopilotQuestions();
  const history = useConversations();
  const ask = useAskCopilot();
  const remove = useDeleteConversation();
  const { params, update } = useViewParams();
  const routeId = positiveId(params.get("conversation"));
  const projectId = params.get("project") ?? "";
  const [conversationId, setConversationId] = useState<number | null>(routeId);
  const [loadId, setLoadId] = useState<number | null>(routeId);
  const detail = useConversation(loadId);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [context, setContext] = useState<Record<string, string>>({});
  const [resetContext, setResetContext] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceRecord[] | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const nextId = useRef(0);
  const requestGeneration = useRef(0);
  const projects = portfolio.data?.projects ?? [];
  const restoring = loadId !== null && (detail.isPending || detail.isFetching);
  const busy = ask.isPending || restoring || remove.isPending;
  const nameFor = (id: string): string => projects.find(project => project.project_id === id)?.project_name ?? id;
  const contextProject = projectId || context.project_id || "";
  const scopeLabel = contextProject ? nameFor(contextProject) : "Whole portfolio";
  // The latest answer's recorded filters are what a follow-up question keeps, so they are shown.
  const carriedFilters = resetContext ? [] : ([...turns].reverse().find(turn => turn.answer)?.answer?.applied_filters ?? []);
  const filterSummary = carriedFilters.map(filter => `${filter.label}${filter.excluded ? " excludes" : ""}: ${filter.values.join(", ")}`).join(" · ");
  const conversations = Array.isArray(history.data) ? history.data : [];
  const matchingConversations = conversations.filter(item => item.title.toLowerCase().includes(historySearch.trim().toLowerCase()));

  useEffect(() => {
    if (routeId === conversationId) return;
    requestGeneration.current += 1;
    setConversationId(routeId); setLoadId(routeId); setTurns([]); setContext({}); setConfirmDelete(false);
  }, [routeId, conversationId]);

  useEffect(() => {
    if (loadId === null || detail.isFetching || detail.isError || !detail.data || detail.data.id !== loadId) return;
    setTurns(savedTurns(detail.data, id => portfolio.data?.projects.find(project => project.project_id === id)?.project_name ?? id));
    nextId.current = Math.max(0, ...detail.data.messages.map(message => message.id));
    setContext(detail.data.context ?? {});
    setLoadId(null);
  }, [detail.data, detail.isFetching, detail.isError, loadId, portfolio.data]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "auto", block: "nearest" }); }, [turns, ask.isPending]);

  function openConversation(id: number | null): void {
    if (busy) return;
    requestGeneration.current += 1;
    setConversationId(id); setLoadId(id); setTurns([]); setDraft(""); setContext({}); setResetContext(false);
    setConfirmDelete(false); setHistoryOpen(false); ask.reset();
    update({ conversation: id ? String(id) : undefined, project: undefined });
  }

  function submit(text?: string, previous?: Turn): void {
    const question = (text ?? draft).trim();
    if (!question || question.length > 1000 || busy || (loadId !== null && detail.isError)) return;
    const id = previous?.id ?? ++nextId.current;
    const generation = ++requestGeneration.current;
    const turn: Turn = { id, question, projectId: previous?.projectId ?? projectId,
      scope: previous?.scope ?? scopeLabel, conversationId: previous?.conversationId ?? conversationId };
    setTurns(current => previous ? current.map(item => item.id === id ? turn : item) : [...current, turn]);
    setDraft("");
    ask.mutate({ question, ...(turn.projectId ? { project_id: turn.projectId } : {}),
      ...(turn.conversationId ? { conversation_id: turn.conversationId } : {}), ...(resetContext ? { reset_context: true } : {}) }, {
      onSuccess: answer => {
        if (generation !== requestGeneration.current) return;
        if (answer.conversation_id) { setConversationId(answer.conversation_id); update({ conversation: String(answer.conversation_id), project: undefined }); }
        setContext(answer.context ?? {}); setResetContext(false);
        setTurns(current => current.map(item => item.id === id ? { ...item, answer } : item));
      },
      onError: caught => {
        if (generation !== requestGeneration.current) return;
        const message = caught instanceof ApiError && caught.status === 503
          ? "EPOS intelligence is temporarily unavailable. Your project workspaces remain available."
          : "EPOS could not complete this request. Your project information is unchanged.";
        setTurns(current => current.map(item => item.id === id ? { ...item, error: message } : item));
        setDraft(current => current || question);
      },
    });
  }

  return <div className="copilot-workspace">
    <PageHeader title="Ask EPOS" description="Your projects, their evidence, and a conversation that stays connected."
      scope="Project copilot · read-only decision support"
      actions={<><Button size="sm" onClick={() => setHistoryOpen(value => !value)} aria-expanded={historyOpen} aria-controls="copilot-history" className="copilot-history-toggle"><History size={15} aria-hidden="true" />History</Button>
        <Button size="sm" disabled={busy} onClick={() => openConversation(null)}><Plus size={15} aria-hidden="true" />New conversation</Button></>} />
    <div className="copilot-layout" data-history-open={historyOpen}>
      <aside id="copilot-history" className="copilot-history" aria-label="Conversation history">
        <div className="copilot-history-heading"><History size={16} aria-hidden="true" /><h2>Your conversations</h2></div>
        <TextInput type="search" aria-label="Search conversations" value={historySearch} onChange={event => setHistorySearch(event.target.value)} placeholder="Find a conversation…" leadingIcon={<Search size={15} />} />
        <p className="copilot-history-notice">Saved to your account. Access to evidence is checked when reopened.</p>
        {history.isPending ? <p role="status" className="copilot-history-notice">Loading history…</p> : history.isError ? <Button size="sm" onClick={() => void history.refetch()}>Retry history</Button> : <ul>
          {matchingConversations.map(item => <li key={item.id}>
            <button type="button" disabled={busy} aria-current={item.id === conversationId ? "page" : undefined} onClick={() => openConversation(item.id)}>
              <MessageSquareText size={15} aria-hidden="true" /><span><strong>{item.title}</strong><small>{formatDate(item.updated_at)} · {item.message_count} {item.message_count === 1 ? "message" : "messages"}</small></span>
            </button>
          </li>)}
        </ul>}
        {!history.isPending && !history.isError && conversations.length === 0 ? <p className="copilot-history-notice">Your first conversation will appear here.</p> : null}
        {!history.isPending && !history.isError && conversations.length > 0 && matchingConversations.length === 0 ? <p role="status" className="copilot-history-notice">No saved conversation matches “{historySearch.trim()}”.</p> : null}
        {conversationId ? <div className="copilot-history-delete">
          {confirmDelete ? <><p>Delete this saved conversation? Project records will not change.</p><Button variant="danger" size="sm" disabled={busy} onClick={() => remove.mutate(conversationId, { onSuccess: () => { setConversationId(null); setLoadId(null); setTurns([]); setContext({}); setConfirmDelete(false); update({ conversation: undefined }); } })}>Confirm delete</Button><Button size="sm" onClick={() => setConfirmDelete(false)}>Cancel</Button></>
            : <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmDelete(true)}><Trash2 size={14} aria-hidden="true" />Delete conversation</Button>}
          {remove.isError ? <p role="alert">The conversation could not be deleted. Try again.</p> : null}
        </div> : null}
      </aside>
      <div className="copilot-main">
        <div className="copilot-context-bar"><span><Database size={15} aria-hidden="true" />{scopeLabel}{filterSummary ? <><span aria-hidden="true">·</span><span>Filtered by {filterSummary}</span></> : null}</span><span>{conversationId ? "Conversation context retained" : "Start with current evidence"}</span></div>
        <div className="copilot-thread">
          {restoring ? <p className="copilot-loading" role="status">Opening saved conversation…</p> : loadId !== null && detail.isError ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> : turns.length === 0 ? <Empty className="copilot-empty">
            <EmptyHeader><EmptyMedia><Sparkles size={25} strokeWidth={1.5} aria-hidden="true" /></EmptyMedia><p className="copilot-eyebrow">A clearer view of your work</p><h2>What would you like to understand?</h2>
              <EmptyDescription>Explore delivery, risks and requirements. Ask follow-ups without repeating the project. Every new answer checks current records.</EmptyDescription></EmptyHeader>
            <EmptyContent><div className="copilot-starters">{(questions.data ?? []).filter(item => !item.requires_context).slice(0, 4).map(item => <button type="button" key={item.intent} disabled={busy} onClick={() => submit(item.question)}><MessageSquareText size={17} aria-hidden="true" /><span>{item.question}</span></button>)}</div></EmptyContent>
          </Empty> : <ol className="copilot-turns">{turns.map(turn => <li key={turn.id}>
            <div className="copilot-question"><p>{turn.scope}</p><div>{turn.question}</div>{turn.savedAt ? <span><Clock3 size={12} aria-hidden="true" />Saved {formatDate(turn.savedAt)} · not a new calculation</span> : null}</div>
            {turn.error ? <div className="copilot-failure" role="alert"><p>{turn.error}</p><Button size="sm" disabled={busy} onClick={() => submit(turn.question, turn)}>Retry question</Button></div> : turn.answer ? <CopilotAnswerCard answer={turn.answer} busy={busy}
              onOpenSources={() => setEvidence(turn.answer?.evidence ?? [])} onFollowUp={question => { setDraft(question); composerRef.current?.focus(); }} />
              : <div className="copilot-loading" role="status"><Sparkles size={17} aria-hidden="true" />Reviewing current project information…</div>}
          </li>)}</ol>}
          <div ref={endRef} />
        </div>
        <form className="copilot-composer" onSubmit={event => { event.preventDefault(); submit(); }}>
          <TextArea ref={composerRef} aria-label="Ask a question" rows={3} maxLength={1000} value={draft} onChange={event => setDraft(event.target.value)}
            onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(); } }}
            placeholder={turns.length ? "Ask a follow-up, or name another project…" : "Which projects need attention, and why?"} />
          <div className="copilot-composer-tools"><Select aria-label="Question scope" value={projectId || (context.project_id && !resetContext ? "__context__" : "")} disabled={busy}
            onChange={event => { update({ project: event.target.value }); setResetContext(true); setContext({}); }}>
            {context.project_id && !resetContext ? <option value="__context__">Continue with {nameFor(context.project_id)}</option> : null}
            <option value="">Whole portfolio</option>
            {projects.map(project => <option key={project.project_id} value={project.project_id}>{project.project_name}</option>)}
          </Select><span>{draft.length}/1000 · Shift + Enter for a new line</span><ProgressFoldButton type="submit" variant="primary" size="sm" status={ask.isPending ? "loading" : "idle"} progressLabel="Reviewing current project information" disabled={busy || !draft.trim() || (loadId !== null && detail.isError)}><ArrowUp size={17} aria-hidden="true" />Ask EPOS</ProgressFoldButton></div>
          <p className="copilot-composer-note">Read-only access to your permitted records. AI explanations need human review.</p>
        </form>
      </div>
    </div>
    {evidence !== null ? <EvidenceDrawer records={evidence} onClose={() => setEvidence(null)} /> : null}
  </div>;
}
