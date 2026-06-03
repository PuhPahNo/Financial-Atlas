"use client";

interface Article { headline: string; source?: string | null; url: string; published_at?: string | null; image?: string | null }

function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const days = Math.floor((Date.now() - then) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

// Recent company news (Finnhub). External links shown with full host (link safety).
export default function NewsList({ articles, limit = 6 }: { articles: Article[]; limit?: number }) {
  if (!articles?.length) return <div className="text-sm text-muted">No recent news available.</div>;
  return (
    <ul className="space-y-3">
      {articles.slice(0, limit).map((a, i) => (
        <li key={i}>
          <a href={a.url} target="_blank" rel="noopener noreferrer" className="group block">
            <div className="text-sm leading-snug text-text transition-colors group-hover:text-accent-2">{a.headline}</div>
            <div className="mt-0.5 text-xs text-faint">{a.source}{a.source && a.published_at ? " · " : ""}{timeAgo(a.published_at)}</div>
          </a>
        </li>
      ))}
    </ul>
  );
}
