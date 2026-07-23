/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // efferd-style neutral surface + single indigo accent
        surface: "#f7f8fa",
        card: "#ffffff",
        ink: "#0f172a",
        muted: "#64748b",
        line: "#e8ebef",
        accent: "#4f46e5",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
