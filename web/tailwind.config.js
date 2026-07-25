/** @type {import('tailwindcss').Config} */
const c = (v) => `rgb(var(${v}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Theme-aware: values resolve from CSS vars in index.css and flip
        // with the `.dark` class. Alpha modifiers (e.g. bg-panel/80) work.
        bg: c("--bg"),
        panel: c("--panel"),
        card: c("--card"),
        cardhi: c("--cardhi"),
        line: c("--line"),
        ink: c("--ink"),
        muted: c("--muted"),
        faint: c("--faint"),
        accent: c("--accent"),
        up: c("--up"),
        down: c("--down"),

        // ── shadcn token bridge ──────────────────────────────────────────
        // shadcn components ship hardcoded semantic class names (bg-card,
        // text-muted-foreground, border-input...). Rather than rewrite every
        // component or migrate the existing palette, we alias shadcn's names
        // onto the SAME CSS vars. One source of truth, so the .dark class keeps
        // flipping both systems together and nothing regresses visually.
        border: c("--line"),
        input: c("--line"),
        ring: c("--faint"),
        background: c("--bg"),
        foreground: c("--ink"),
        primary: { DEFAULT: c("--ink"), foreground: c("--bg") },
        secondary: { DEFAULT: c("--cardhi"), foreground: c("--ink") },
        destructive: { DEFAULT: c("--down"), foreground: c("--bg") },
        popover: { DEFAULT: c("--panel"), foreground: c("--ink") },
        // `card` already exists above as a flat color; adding the foreground
        // pair here would clobber it, so card-foreground is declared separately.
        "card-foreground": c("--ink"),
        "muted-foreground": c("--muted"),
        "accent-foreground": c("--ink"),
      },
      borderRadius: {
        lg: "0.5rem",
        md: "calc(0.5rem - 2px)",
        sm: "calc(0.5rem - 4px)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
