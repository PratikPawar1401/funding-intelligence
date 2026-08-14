import { Topbar } from "@/components/layout/topbar";

export default function MatchPage() {
  return (
    <>
      <Topbar>
        <h1 className="font-heading text-lg font-semibold">AI Match</h1>
      </Topbar>
      <main className="flex-1 overflow-y-auto p-6">
        <p className="text-sm text-muted-foreground">Phase 4 builds this view.</p>
      </main>
    </>
  );
}
