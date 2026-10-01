import { Link, useNavigate } from "react-router-dom";
import { ArrowDown, ArrowRight, ArrowUpRight, Fingerprint, GitBranch, Layers3, ScanEye, ShieldCheck } from "lucide-react";
import { LightRays } from "@/components/godui/light-rays";
import { ShimmerButton } from "@/components/godui/shimmer-button";
import { ProductTour } from "@/components/layout/product-tour";
import { PublicThemeToggle, PublicWordmark, useBackgroundMotion } from "@/components/layout/public-controls";

const PRINCIPLES = [
  { icon: ScanEye, title: "See what deserves attention.", text: "Bring project health, confidence and delivery warnings into the same conversation." },
  { icon: GitBranch, title: "Keep the evidence within reach.", text: "Follow the connections between requirements, work and verification—not another trail of spreadsheets." },
  { icon: ShieldCheck, title: "Leave the decisions with people.", text: "EPOS calculates from recorded facts. AI helps explain them. Your team reviews what happens next." },
] as const;

export function WelcomePage(): JSX.Element {
  const navigate = useNavigate();
  const motion = useBackgroundMotion();
  return (
    <div className="public-page" data-motion-paused={motion.paused}>
      <a href="#welcome-main" className="skip-link">Skip to content</a>
      <header className="public-header">
        <PublicWordmark />
        <nav className="public-nav" aria-label="Public navigation">
          <a href="#capabilities" className="public-nav-link">Capabilities</a>
          <a href="#approach" className="public-nav-link">Our approach</a>
          <PublicThemeToggle />
          <Link to="/login" className="public-nav-signin">Sign in <ArrowRight size={15} aria-hidden="true" /></Link>
        </nav>
      </header>
      <main id="welcome-main" tabIndex={-1}>
        <section className="welcome-hero" aria-labelledby="welcome-title">
          <LightRays paused={motion.paused} intensity={0.2} />
          <div className="welcome-copy">
            <p className="welcome-intro"><Layers3 size={15} strokeWidth={1.7} aria-hidden="true" /> A little perspective changes everything.</p>
            <h1 id="welcome-title">Complex projects.<br />A clearer <em>perspective.</em></h1>
            <p className="welcome-tagline">One explainable view over your engineering programme</p>
            <p className="welcome-description">Connect delivery, risk and requirements. See what matters,<br className="welcome-desktop-break" /> understand the why, and move forward together.</p>
            <div className="welcome-actions">
              <ShimmerButton size="lg" onClick={() => navigate("/login")}>Sign in <ArrowRight size={18} aria-hidden="true" /></ShimmerButton>
              <ShimmerButton size="lg" variant="outline" onClick={() => navigate("/register")}>Create account <ArrowUpRight size={17} aria-hidden="true" /></ShimmerButton>
            </div>
            <p className="welcome-assurance"><Fingerprint size={15} aria-hidden="true" /> Evidence-led. Explainable. People in control.</p>
          </div>
          <div className="welcome-hero-foot"><a href="#capabilities">See how it connects <ArrowDown size={15} aria-hidden="true" /></a>{motion.control}</div>
        </section>
        <section id="capabilities" className="welcome-capabilities" aria-labelledby="capabilities-title">
          <div className="welcome-section-heading"><h2 id="capabilities-title">One workspace. Every connection.</h2><p>Take a closer look. Choose a capability below.</p></div>
          <ProductTour />
        </section>
        <section id="approach" className="welcome-approach" aria-labelledby="approach-title">
          <div className="welcome-approach-heading"><p className="public-eyebrow">Built for the work behind the work</p><h2 id="approach-title">Less chasing updates.<br /><em>More understanding.</em></h2><p>Engineering is complex enough.<br />Making sense of it should feel clearer.</p></div>
          <div className="welcome-principle-list">
            {PRINCIPLES.map(({ icon: Icon, title, text }) => <article key={title}><span className="welcome-principle-icon"><Icon size={23} strokeWidth={1.5} aria-hidden="true" /></span><div><h3>{title}</h3><p>{text}</p></div></article>)}
          </div>
        </section>
        <section className="welcome-closing" aria-labelledby="closing-title">
          <span className="welcome-closing-mark" aria-hidden="true"><Layers3 size={30} strokeWidth={1.4} /></span>
          <div><p className="public-eyebrow">A clearer place to start</p><h2 id="closing-title">Bring your next decision into focus.</h2><p>Your projects. Their evidence. One considered view.</p></div>
          <Link to="/register" className="welcome-text-link">Create your account <ArrowUpRight size={18} aria-hidden="true" /></Link>
        </section>
      </main>
      <footer className="public-footer"><PublicWordmark /><span>Engineering Portfolio Operating System</span><span>Clarity, with context.</span></footer>
    </div>
  );
}