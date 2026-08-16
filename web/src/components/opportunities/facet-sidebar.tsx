"use client";

import { ChevronDown } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import { useState } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { buildSearchParams } from "@/lib/search-params";
import type { FacetOption } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  closed: "Closed",
  forecasted: "Forecasted",
};

// Shown before the "show more" toggle. The real corpus is heavily skewed
// (NSF ~114 of 136 records, everything else 1-4) -- a flat list of 16
// agencies would bury the one that matters. simpler.grants.gov's own agency
// facet uses the same collapsed-by-default pattern for the same reason.
const AGENCY_VISIBLE_COUNT = 5;

interface FacetSidebarProps {
  statusOptions: FacetOption[];
  agencyOptions: FacetOption[];
  activeStatus?: string;
  activeAgency?: string;
}

export function FacetSidebar({
  statusOptions,
  agencyOptions,
  activeStatus,
  activeAgency,
}: FacetSidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [agencyExpanded, setAgencyExpanded] = useState(false);

  // Each dimension is single-value on the backend (list_foas/get_facet_counts
  // take one status, one agency_code -- not arrays), so a facet click always
  // REPLACES that dimension's filter, or clears it if it was already active.
  // Checkbox visuals with single-select-per-group behaviour, not a lie about
  // what filtering supports.
  const toggle = (key: "status" | "agency", value: string, currentlyActive: boolean) => {
    const qs = buildSearchParams(Object.fromEntries(searchParams.entries()), {
      [key]: currentlyActive ? undefined : value,
    });
    router.push(`${pathname}${qs}`, { scroll: false });
  };

  const visibleAgencies = agencyExpanded
    ? agencyOptions
    : agencyOptions.slice(0, AGENCY_VISIBLE_COUNT);

  return (
    <nav aria-label="Filter opportunities" className="flex w-64 shrink-0 flex-col gap-6 pr-2">
      <FacetGroup title="Status">
        {statusOptions.map((opt) => (
          <FacetCheckbox
            key={opt.value}
            label={STATUS_LABEL[opt.value] ?? opt.value}
            count={opt.count}
            checked={activeStatus === opt.value}
            onCheckedChange={() => toggle("status", opt.value, activeStatus === opt.value)}
          />
        ))}
      </FacetGroup>

      {agencyOptions.length > 0 && (
        <FacetGroup title="Agency">
          {visibleAgencies.map((opt) => (
            <FacetCheckbox
              key={opt.value}
              label={opt.value}
              count={opt.count}
              checked={activeAgency === opt.value}
              onCheckedChange={() => toggle("agency", opt.value, activeAgency === opt.value)}
            />
          ))}
          {agencyOptions.length > AGENCY_VISIBLE_COUNT && (
            <Collapsible open={agencyExpanded} onOpenChange={setAgencyExpanded}>
              <CollapsibleTrigger className="flex items-center gap-1 pt-1 text-sm text-primary hover:underline">
                <ChevronDown
                  className={`size-3.5 transition-transform ${agencyExpanded ? "rotate-180" : ""}`}
                />
                {agencyExpanded
                  ? "Show fewer"
                  : `Show ${agencyOptions.length - AGENCY_VISIBLE_COUNT} more`}
              </CollapsibleTrigger>
              <CollapsibleContent />
            </Collapsible>
          )}
        </FacetGroup>
      )}
    </nav>
  );
}

function FacetGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 font-heading text-sm font-semibold text-foreground">{title}</h3>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  );
}

function FacetCheckbox({
  label,
  count,
  checked,
  onCheckedChange,
}: {
  label: string;
  count: number;
  checked: boolean;
  onCheckedChange: () => void;
}) {
  const id = `facet-${label}`;
  return (
    <label
      htmlFor={id}
      className="flex cursor-pointer items-center justify-between gap-2 text-sm text-foreground"
    >
      <span className="flex items-center gap-2">
        <Checkbox id={id} checked={checked} onCheckedChange={onCheckedChange} />
        {label}
      </span>
      <span className="text-muted-foreground">{count}</span>
    </label>
  );
}
