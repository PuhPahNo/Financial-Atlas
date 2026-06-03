// Atlas brand mark — an "armillary A": two converging meridian strokes (the
// letter A / a navigator's dividers) crossed by a tilted orbital ring (the
// celestial sphere Atlas bears + the analytics band), capped by an emerald
// pole-star node where analysis and the market meet. Monoline, two flat brand
// colors — no gradient, no chart squiggle.
//
// `tile` wraps it in a deep-ink rounded square (used for the favicon and the
// header lockup); without it the glyph is transparent for use on dark surfaces.

export default function AtlasMark({ size = 28, tile = true, title = "Atlas" }: { size?: number; tile?: boolean; title?: string }) {
  const legW = tile ? 6.6 : 7.4;
  const ringW = tile ? 3.3 : 3.8;
  const node = tile ? 5.2 : 5.8;
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label={title}>
      {tile && (
        <>
          <rect x="0.75" y="0.75" width="98.5" height="98.5" rx="24" fill="#0E0E16" />
          <rect x="1.5" y="1.5" width="97" height="97" rx="23.25" fill="none" stroke="rgba(124,108,255,0.30)" strokeWidth="1.5" />
        </>
      )}
      <g stroke="#7C6CFF" fill="none" strokeLinecap="round" strokeLinejoin="round">
        {/* orbital / meridian ring — tilted for motion (the celestial sphere + the A's crossbar) */}
        <ellipse cx="50" cy="55" rx="30" ry="11" transform="rotate(-19 50 55)" strokeWidth={ringW} opacity="0.9" />
        {/* converging meridian strokes — the letter A / navigator's dividers */}
        <path d="M50 25 L30.5 79" strokeWidth={legW} />
        <path d="M50 25 L69.5 79" strokeWidth={legW} />
      </g>
      {/* pole-star node — where analytics and the market converge */}
      <circle cx="50" cy="24.5" r={node} fill="#3ECF8E" />
    </svg>
  );
}
