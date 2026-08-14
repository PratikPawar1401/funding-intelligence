import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/layout/theme-toggle";

/**
 * Shell topbar: the search input itself is Phase 2 work (lives in the
 * Opportunities view, since it drives that view's URL-state filtering) --
 * this just reserves the row and carries the theme toggle so every view has
 * one from Phase 0 onward.
 */
export function Topbar({ children }: { children?: ReactNode }) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border bg-background px-6">
      <div className="flex-1">{children}</div>
      <ThemeToggle />
    </header>
  );
}
