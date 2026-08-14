"use client";

import { Brain, Table2, Tags, WandSparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType } from "react";

import { cn } from "@/lib/utils";

const NAV_ITEMS: { href: string; label: string; icon: ComponentType<{ className?: string }> }[] = [
  { href: "/opportunities", label: "Opportunities", icon: Table2 },
  { href: "/match", label: "AI Match", icon: WandSparkles },
  { href: "/tags", label: "Ontology Tags", icon: Tags },
];

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
      <Link href="/opportunities" className="flex items-center gap-2 px-5 py-6">
        <Brain className="size-6 text-primary" />
        <span className="font-heading text-lg font-semibold text-sidebar-foreground">
          ISSR<span className="text-primary">Intel</span>
        </span>
      </Link>

      <nav className="flex flex-col gap-1 px-3">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname?.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-sidebar-primary text-sidebar-primary-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              )}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
