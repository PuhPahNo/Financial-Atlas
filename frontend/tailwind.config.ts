import type { Config } from "tailwindcss";

// Financial Atlas design system — "Aurora × Meridian" (PRD 06).
// Single source of theme tokens. Dark only. Violet brand accent + aurora glow,
// editorial serif headlines, mono tabular numerals, emerald/coral financial semantics.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0f",
        "bg-2": "#0e0e15",
        surface: "#131319",
        "surface-2": "#1a1a22",
        line: "rgba(255,255,255,0.08)",
        "line-2": "rgba(255,255,255,0.14)",
        border: "rgba(255,255,255,0.08)", // alias for legacy `border-border` usages

        text: "#ECEAF2",
        muted: "#8c8a99",
        faint: "#5a5965",
        accent: "#7C6CFF",
        "accent-2": "#9d8bff",
        "accent-deep": "#5a48d6",
        positive: "#3ECF8E",
        negative: "#FF6B6B",
        gold: "#E0B341",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-fraunces)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        lg: "14px",
        xl: "18px",
        "2xl": "22px",
      },
      boxShadow: {
        panel: "0 10px 40px rgba(0,0,0,0.35)",
        pop: "0 20px 60px rgba(0,0,0,0.6)",
        glow: "0 0 30px rgba(124,108,255,0.45)",
      },
      letterSpacing: {
        tightest: "-0.03em",
      },
    },
  },
  plugins: [],
};
export default config;
