// Instant route-transition skeleton — so tab clicks register immediately
// instead of freezing until the new view is ready.
export default function Loading() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="h-8 w-48 rounded-lg bg-surface-2/60" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 rounded-xl border border-line bg-surface/40" />
        ))}
      </div>
      <div className="h-72 rounded-xl border border-line bg-surface/40" />
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="h-56 rounded-xl border border-line bg-surface/40" />
        <div className="h-56 rounded-xl border border-line bg-surface/40" />
      </div>
    </div>
  );
}
