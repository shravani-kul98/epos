import { useId, useState } from "react";
import { Activity, ArrowRight, CheckCheck, FileCheck2, GitBranch, Layers3, ListChecks, ShieldAlert, Sparkles, UserCheck } from "lucide-react";
import { MagicTab } from "@/components/godui/magic-tab";
import { SpotlightCard } from "@/components/godui/spotlight-card";

const CAPABILITIES = [
  {
    value: "health", label: "Health Score", icon: Activity, eyebrow: "See the bigger picture",
    title: "Understand the position. Not just the number.",
    text: "Explore project health alongside confidence and the factors behind each score. Follow the explanation back to the recorded evidence.",
    sources: ["Delivery work", "Milestones", "Reporting"], outcome: "Health & confidence", detail: "Factors and source records", hub: "Health",
  },
  {
    value: "risk", label: "Risk Intelligence", icon: ShieldAlert, eyebrow: "Bring uncertainty into view",
    title: "Know what needs a closer look.",
    text: "Review delivery warnings, recorded risks and their supporting evidence together. Keep the conversation focused on what needs attention.",
    sources: ["Recorded risks", "Dependencies", "Open actions"], outcome: "Delivery warnings", detail: "Severity and evidence", hub: "Risk",
  },
  {
    value: "trace", label: "Traceability", icon: GitBranch, eyebrow: "Keep the thread",
    title: "See how the work connects.",
    text: "Follow links between requirements, delivery work and verification. Find the gaps without losing the context of the project around them.",
    sources: ["Requirements", "Delivery work", "Verification"], outcome: "Connected evidence", detail: "Links and coverage gaps", hub: "Traceability",
  },
  {
    value: "ai", label: "AI Copilot", icon: Sparkles, eyebrow: "Ask. Understand. Review.",
    title: "A clearer explanation. The same recorded facts.",
    text: "Ask about your project in everyday language. When configured, AI explains selected evidence; it does not calculate scores or make decisions for you.",
    sources: ["Your question", "Selected records", "Calculated facts"], outcome: "Grounded explanation", detail: "Source-backed context", hub: "AI Copilot",
  },
] as const;

export function ProductTour(): JSX.Element {
  const [selected, setSelected] = useState<string>("health");
  const prefix = useId();
  const active = CAPABILITIES.find(item => item.value === selected) ?? CAPABILITIES[0];
  const Icon = active.icon;
  const sourceIcons = [FileCheck2, ListChecks, CheckCheck];
  return (
    <SpotlightCard as="section" className="product-tour" aria-label="Explore EPOS capabilities" border={false}>
      <div className="product-tour-topline"><span><Layers3 size={16} aria-hidden="true" /> Inside EPOS</span><span>Interactive overview · no live project data</span></div>
      <MagicTab className="product-tour-tabs" aria-label="Product capabilities" value={selected} onValueChange={setSelected}
        variant="secondary" items={CAPABILITIES.map(item => ({
          value: item.value, id: `${prefix}-${item.value}-tab`, controls: `${prefix}-${item.value}-panel`,
          label: <><item.icon size={17} strokeWidth={1.7} aria-hidden="true" /><span>{item.label}</span></>,
        }))} />
      {CAPABILITIES.map(item => (
        <div key={item.value} role="tabpanel" id={`${prefix}-${item.value}-panel`}
          aria-labelledby={`${prefix}-${item.value}-tab`} hidden={item.value !== active.value} tabIndex={0}
          className="product-tour-panel" data-tone={item.value}>
          {item.value === active.value ? <>
            <div className="product-tour-copy">
              <span className="product-tour-symbol"><Icon size={27} strokeWidth={1.5} aria-hidden="true" /></span>
              <p className="public-eyebrow">{active.eyebrow}</p>
              <h3>{active.title}</h3>
              <p>{active.text}</p>
              <span className="product-tour-hint">Built around your evidence <ArrowRight size={15} aria-hidden="true" /></span>
            </div>
            <figure className="product-map" aria-label={`${active.label}: records connect to insight and human review`}>
              <div className="product-map-canvas">
                <svg className="product-map-lines" viewBox="0 0 640 300" preserveAspectRatio="none" aria-hidden="true">
                  <path d="M140 54 C225 54 210 150 270 150 M140 150 H270 M140 246 C225 246 210 150 270 150 M370 150 C425 150 420 98 495 98 M370 150 C425 150 420 206 495 206" />
                </svg>
                <div className="product-map-records">
                  {active.sources.map((source, index) => {
                    const SourceIcon = sourceIcons[index] ?? FileCheck2;
                    return <div className="product-map-record" key={source}><SourceIcon size={18} strokeWidth={1.6} aria-hidden="true" /><span>{source}</span></div>;
                  })}
                </div>
                <div className="product-map-hub"><span className="product-map-halo" aria-hidden="true" /><Layers3 size={34} strokeWidth={1.5} aria-hidden="true" /><strong>EPOS</strong><span>{active.hub}</span></div>
                <div className="product-map-outcomes">
                  <div className="product-map-insight"><Icon size={20} strokeWidth={1.6} aria-hidden="true" /><strong>{active.outcome}</strong><span>{active.detail}</span></div>
                  <div className="product-map-review"><UserCheck size={20} strokeWidth={1.6} aria-hidden="true" /><strong>Human review</strong><span>Your team decides</span></div>
                </div>
              </div>
              <figcaption>Records <span aria-hidden="true">→</span> Understanding <span aria-hidden="true">→</span> Decisions</figcaption>
            </figure>
          </> : null}
        </div>
      ))}
    </SpotlightCard>
  );
}