import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // shadcn components import from "@/..."; the alias must be declared here for
  // the bundler AND in tsconfig.json paths for the type-checker — both, or the
  // editor and `npm run build` disagree about the same import.
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
