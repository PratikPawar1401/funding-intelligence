"use client";

import { flexRender } from "@tanstack/react-table";
import {
  getCoreRowModel,
  legacyCreateColumnHelper,
  useLegacyTable,
  type LegacyColumnDef,
} from "@tanstack/react-table/legacy";
import type { SortingState } from "@tanstack/table-core";
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { StatusBadge } from "@/components/opportunities/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { buildSearchParams } from "@/lib/search-params";
import type { FoaListItem } from "@/lib/types";

/**
 * TanStack Table v9 replaced useReactTable with a new reactive/store-based
 * API (useTable) that has no ecosystem precedent yet -- @tanstack/react-table/legacy
 * is the officially shipped v8-compatible surface (useLegacyTable,
 * getCoreRowModel, flexRender), used deliberately here instead of chasing
 * the brand-new API on a deadline.
 *
 * No getSortedRowModel(): sorting is manual/server-driven via the URL
 * (sort/order params, read by the opportunities page's Server Component
 * fetch), not client-side. The `sorting` state below is derived FRESH from
 * the URL on every render rather than tracked independently, so the URL
 * stays the single source of truth -- back/forward navigation and shared
 * links can't drift out of sync with what TanStack thinks the sort is.
 */

const SORTABLE_COLUMNS = new Set([
  "posted_date",
  "close_date",
  "title",
  "agency",
  "award_ceiling",
  "award_floor",
]);

const columnHelper = legacyCreateColumnHelper<FoaListItem>();

function formatDate(value: string | null): string {
  if (!value) return "Continuous";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatMoney(value: number | null): string {
  if (value === null || value === undefined) return "—";
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value}`;
}

function awardRange(floor: number | null, ceiling: number | null): string {
  if (floor === null && ceiling === null) return "Not specified";
  if (floor === null) return `Up to ${formatMoney(ceiling)}`;
  if (ceiling === null) return `From ${formatMoney(floor)}`;
  if (floor === ceiling) return formatMoney(floor);
  return `${formatMoney(floor)} – ${formatMoney(ceiling)}`;
}

// Each column below has its own concrete TValue (string, string | null,
// number | null, a union of accessor return types...). ColumnDef's render
// functions take TValue as a parameter, a contravariant position, so a
// heterogeneous array can never satisfy LegacyColumnDef<FoaListItem> (which
// defaults TValue to `unknown`, not `any` -- unknown is only safely WIDER,
// not usable where a narrower parameter type is expected). Widening to
// `any` here is TanStack Table's own documented pattern for exactly this
// case, not a shortcut around a real type error.
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- see comment above: TanStack's own pattern for a heterogeneous column array, not a shortcut
const columns: LegacyColumnDef<FoaListItem, any>[] = [
  columnHelper.accessor("close_date", {
    header: "Close Date",
    cell: (info) => formatDate(info.getValue()),
  }),
  columnHelper.accessor("status", {
    header: "Status",
    cell: (info) => <StatusBadge status={info.getValue()} />,
  }),
  columnHelper.accessor("title", {
    header: "Title",
    cell: (info) => {
      const foa = info.row.original;
      // Phase 3 gives every FOA a real /opportunities/[foa_id] detail page;
      // until then, the title links straight to the source listing so the
      // table is useful today rather than shipping a dead link.
      return foa.source_url ? (
        <a
          href={foa.source_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-start gap-1.5 font-medium text-foreground hover:text-primary hover:underline"
        >
          {info.getValue()}
          <ExternalLink className="mt-1 size-3 shrink-0 text-muted-foreground" />
        </a>
      ) : (
        <span className="font-medium text-foreground">{info.getValue()}</span>
      );
    },
  }),
  columnHelper.accessor("opportunity_number", {
    header: "Opportunity #",
    cell: (info) => info.getValue() ?? "—",
    enableSorting: false,
  }),
  columnHelper.accessor((row) => row.agency_code ?? row.agency, {
    id: "agency",
    header: "Agency",
    cell: (info) => info.getValue() ?? "Unknown",
  }),
  columnHelper.accessor("posted_date", {
    header: "Posted",
    cell: (info) => formatDate(info.getValue()),
  }),
  columnHelper.accessor("expected_awards", {
    header: "Expected Awards",
    cell: (info) => info.getValue() ?? "—",
    enableSorting: false,
  }),
  columnHelper.display({
    id: "award_range",
    header: "Award Range",
    cell: (info) => awardRange(info.row.original.award_floor, info.row.original.award_ceiling),
  }),
];

export function OpportunitiesTable({ items }: { items: FoaListItem[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const sorting: SortingState = useMemo(() => {
    const sort = searchParams.get("sort");
    if (!sort || !SORTABLE_COLUMNS.has(sort)) return [];
    return [{ id: sort === "agency_code" ? "agency" : sort, desc: searchParams.get("order") !== "ASC" }];
  }, [searchParams]);

  const table = useLegacyTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    state: { sorting },
    onSortingChange: (updater) => {
      const next = typeof updater === "function" ? updater(sorting) : updater;
      const first = next[0];
      const qs = buildSearchParams(Object.fromEntries(searchParams.entries()), {
        sort: first?.id,
        order: first ? (first.desc ? "DESC" : "ASC") : undefined,
      });
      router.push(`${pathname}${qs}`, { scroll: false });
    },
  });

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
                const sortable = header.column.getCanSort();
                const direction = header.column.getIsSorted();
                return (
                  <TableHead
                    key={header.id}
                    className={sortable ? "cursor-pointer select-none whitespace-nowrap" : "whitespace-nowrap"}
                    onClick={sortable ? header.column.getToggleSortingHandler() : undefined}
                  >
                    <span className="inline-flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {sortable &&
                        (direction === "desc" ? (
                          <ArrowDown className="size-3.5" />
                        ) : direction === "asc" ? (
                          <ArrowUp className="size-3.5" />
                        ) : (
                          <ArrowUpDown className="size-3.5 text-muted-foreground/50" />
                        ))}
                    </span>
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                No opportunities found matching your criteria.
              </TableCell>
            </TableRow>
          ) : (
            table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
