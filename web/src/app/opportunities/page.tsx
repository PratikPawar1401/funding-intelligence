import { Topbar } from "@/components/layout/topbar";
import { listOpportunities } from "@/lib/api/opportunities";

/**
 * Phase 0 placeholder: proves the server-to-server fetch path (Server
 * Component -> API_BASE_URL, no CORS involved) works end-to-end against the
 * real backend. Phase 2 replaces the list below with the sortable table +
 * facet sidebar; the data fetch itself does not change shape.
 */
export default async function OpportunitiesPage() {
  const { items, total } = await listOpportunities({ status: "open", size: 20 });

  return (
    <>
      <Topbar>
        <h1 className="font-heading text-lg font-semibold">Funding Opportunities</h1>
      </Topbar>
      <main className="flex-1 overflow-y-auto p-6">
        <p className="mb-4 text-sm text-muted-foreground">{total} open opportunities</p>
        <ul className="flex flex-col gap-2">
          {items.map((foa) => (
            <li
              key={foa.foa_id}
              className="rounded-md border border-border bg-card p-4 text-card-foreground"
            >
              <div className="text-xs font-medium uppercase tracking-wide text-primary">
                {foa.agency_code ?? foa.agency ?? "Unknown agency"}
              </div>
              <div className="font-heading font-medium">{foa.title}</div>
            </li>
          ))}
        </ul>
      </main>
    </>
  );
}
