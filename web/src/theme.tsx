import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "dark" | "light";

// Recharts renders SVG and can't read CSS variables, so chart colors are
// duplicated here per theme (the one place the palette isn't in index.css).
export interface ChartTheme {
  grid: string;
  axis: string;      // faint tick labels
  axisStrong: string;
  accent: string;    // bars
  accentTop: string; // bar gradient top
  wa: string;        // WhatsApp line
  tg: string;        // Telegram line
  tooltipBg: string;
  tooltipBorder: string;
  tooltipInk: string;
  glow: string;      // drop-shadow color for the step lines
}

export const CHART: Record<Theme, ChartTheme> = {
  dark: {
    grid: "#1c1c20", axis: "#5a5a62", axisStrong: "#8b8b93",
    accent: "#6366f1", accentTop: "#a5b4fc",
    wa: "#22c55e", tg: "#3b82f6",
    tooltipBg: "#17171b", tooltipBorder: "#232327", tooltipInk: "#fafafa",
    glow: "rgba(255,255,255,0.35)",
  },
  light: {
    grid: "#e6e9ee", axis: "#94a3b8", axisStrong: "#64748b",
    accent: "#4f46e5", accentTop: "#818cf8",
    wa: "#16a34a", tg: "#2563eb",
    tooltipBg: "#ffffff", tooltipBorder: "#e2e8f0", tooltipInk: "#0f172a",
    glow: "rgba(37,99,235,0.30)",
  },
};

type Ctx = { theme: Theme; setTheme: (t: Theme) => void; toggle: () => void; chart: ChartTheme };
const ThemeContext = createContext<Ctx | null>(null);
const STORAGE_KEY = "aznet.theme";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  });

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem(STORAGE_KEY, t);
  }, []);
  const toggle = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme, setTheme]);

  // Tailwind darkMode:"class" reads this class on <html>.
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggle, chart: CHART[theme] }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
