/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    screens: { sm: "640px", md: "768px", lg: "1024px", xl: "1280px", "2xl": "1536px" },
    extend: {
      colors: {
        canvas: "var(--canvas)",
        surface: {
          DEFAULT: "var(--surface)",
          raised: "var(--surface-raised)",
          subtle: "var(--surface-subtle)",
        },
        line: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
        },
        ink: {
          DEFAULT: "var(--text)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
          onaccent: "var(--text-on-accent)",
          onstatus: "var(--text-on-status)",
        },
        nav: {
          DEFAULT: "var(--nav-surface)",
          text: "var(--nav-text)",
          strong: "var(--nav-text-strong)",
          hover: "var(--nav-hover)",
          active: "var(--nav-active)",
          marker: "var(--nav-marker)",
          border: "var(--nav-border)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          tint: "var(--accent-tint)",
          border: "var(--accent-border)",
        },
        steel: "var(--steel)",
        ok: { DEFAULT: "var(--ok)", tint: "var(--ok-tint)" },
        warn: { DEFAULT: "var(--warn)", tint: "var(--warn-tint)" },
        critical: { DEFAULT: "var(--critical)", tint: "var(--critical-tint)" },
        advisory: { DEFAULT: "var(--advisory)", tint: "var(--advisory-tint)" },
        muted: { DEFAULT: "var(--neutral)", tint: "var(--neutral-tint)" },
        teal: { DEFAULT: "var(--teal)", tint: "var(--teal-tint)" },
        purple: { DEFAULT: "var(--purple)", tint: "var(--purple-tint)" },
        indigo: { DEFAULT: "var(--indigo)", tint: "var(--indigo-tint)" },
        cyan: { DEFAULT: "var(--cyan)", tint: "var(--cyan-tint)" },
        violet: { DEFAULT: "var(--violet)", tint: "var(--violet-tint)" },
        overlay: "var(--overlay)",
        domain: {
          schedule: "var(--domain-schedule)", risk: "var(--domain-risk)",
          requirements: "var(--domain-requirements)", testing: "var(--domain-testing)",
          capacity: "var(--domain-capacity)", intelligence: "var(--domain-intelligence)",
          traceability: "var(--domain-traceability)", scenarios: "var(--domain-scenarios)",
          governance: "var(--domain-governance)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
      },
      fontSize: {
        meta: ["var(--font-meta)", { lineHeight: "var(--line-meta)" }],
        table: ["var(--font-table)", { lineHeight: "var(--line-body)" }],
        body: ["var(--font-body)", { lineHeight: "var(--line-body)" }],
        card: ["var(--font-card)", { lineHeight: "var(--line-body)" }],
        section: ["var(--font-section)", { lineHeight: "var(--line-heading)" }],
        title: ["var(--font-title)", { lineHeight: "var(--line-heading)" }],
        kpi: ["var(--font-kpi)", { lineHeight: "var(--line-heading)" }],
        identifier: ["var(--font-identifier)", { lineHeight: "var(--line-meta)" }],
      },
      borderRadius: {
        control: "var(--radius-control)",
        card: "var(--radius-card)",
        overlay: "var(--radius-overlay)",
      },
      spacing: {
        page: "var(--space-page)", section: "var(--space-section)",
        sidebar: "var(--layout-sidebar)", "sidebar-compact": "var(--layout-sidebar-compact)",
        topbar: "var(--layout-header)",
      },
      transitionDuration: { DEFAULT: "var(--motion-fast)", base: "var(--motion-base)" },
      boxShadow: {
        card: "var(--shadow-card)",
        raised: "var(--shadow-raised)",
        overlay: "var(--shadow-overlay)",
      },
      maxWidth: {
        content: "var(--content-max-width)",
      },
      transitionTimingFunction: {
        ease: "var(--motion-ease)",
      },
    },
  },
  plugins: [],
};
