import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowLeft, ArrowRight, GitBranch, Layers3, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";
import { LightRays } from "@/components/godui/light-rays";
import { SpotlightCard } from "@/components/godui/spotlight-card";
import { PublicThemeToggle, PublicWordmark, useBackgroundMotion } from "@/components/layout/public-controls";

export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
}): JSX.Element {
  const motion = useBackgroundMotion();
  return (
    <div className="auth-page" data-motion-paused={motion.paused}>
      <a className="skip-link" href="#auth-main">Skip to content</a>
      <aside className="auth-story" aria-label="About EPOS">
        <LightRays paused={motion.paused} intensity={0.4} color="var(--public-story-glow)" />
        <div className="relative"><PublicWordmark /></div>
        <div className="auth-story-content">
          <p className="public-eyebrow">The space to see things clearly</p>
          {/* A tagline, not a heading: the form's h1 is the first heading on the page. */}
          <p className="auth-story-title">Good work deserves<br /><em>a clear view.</em></p>
          <p className="auth-story-description">Connect your projects, their evidence and the decisions ahead. Keep the bigger picture in sight.</p>
          <figure className="auth-story-constellation" aria-label="Health, risk, traceability and explanations connected through EPOS">
            <div className="auth-story-orbit" aria-hidden="true" />
            <span className="auth-story-node" data-node="health"><Activity size={21} strokeWidth={1.6} aria-hidden="true" /><span>Health</span></span>
            <span className="auth-story-node" data-node="risk"><ShieldAlert size={21} strokeWidth={1.6} aria-hidden="true" /><span>Risk</span></span>
            <span className="auth-story-center"><Layers3 size={42} strokeWidth={1.3} aria-hidden="true" /><strong>EPOS</strong></span>
            <span className="auth-story-node" data-node="trace"><GitBranch size={21} strokeWidth={1.6} aria-hidden="true" /><span>Traceability</span></span>
            <span className="auth-story-node" data-node="ai"><Sparkles size={21} strokeWidth={1.6} aria-hidden="true" /><span>Explanations</span></span>
            <figcaption>Connected records <ArrowRight size={13} aria-hidden="true" /> Considered decisions</figcaption>
          </figure>
        </div>
        <div className="auth-story-foot"><span>Evidence-led. Human-reviewed.</span>{motion.control}</div>
      </aside>
      <main className="auth-main" id="auth-main" tabIndex={-1}>
        <div className="auth-topline"><Link to="/" className="auth-back"><ArrowLeft size={15} aria-hidden="true" />Back to overview</Link><PublicThemeToggle /></div>
        <div className="auth-form-wrap">
          <div className="auth-mobile-brand"><PublicWordmark /></div>
          <SpotlightCard className="auth-form-card" border={false}>
            <span className="auth-form-symbol"><ShieldCheck size={24} strokeWidth={1.5} aria-hidden="true" /></span>
            <h1>{title}</h1>
            <p>{description}</p>
            {children}
          </SpotlightCard>
          {footer ? <div className="auth-form-foot">{footer}</div> : null}
        </div>
      </main>
    </div>
  );
}
