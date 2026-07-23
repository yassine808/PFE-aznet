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
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
