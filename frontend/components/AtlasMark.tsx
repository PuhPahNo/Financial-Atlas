// Atlas brand mark — the emerald globe encircled by an ascending market arrow
// and candlestick orbit. Rendered from /public/atlas-mark.png (a transparent
// PNG that glows on dark surfaces, so no tile is needed).
//
// `size` is the rendered height in px; width follows the artwork's aspect ratio.
// `tile`/`title` are kept for backwards-compatibility with existing call sites.

const RATIO = 531 / 480; // intrinsic width / height of atlas-mark.png

export default function AtlasMark({ size = 28, title = "Atlas" }: { size?: number; tile?: boolean; title?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/atlas-mark.png"
      alt={title}
      width={Math.round(size * RATIO)}
      height={size}
      draggable={false}
      style={{ height: size, width: "auto", display: "block" }}
    />
  );
}
