/**
 * Lets a keyboard user jump past the header straight to the page content.
 *
 * Visually hidden until focused, which is the first thing a keyboard user encounters on
 * every page. Without it, reaching the main content means tabbing through the whole
 * navigation on every single page load.
 */
export function SkipLink() {
  return (
    <a
      href="#main-content"
      className="sr-only-focusable absolute left-2 top-2 z-50 bg-nhs-focus px-4 py-3 font-bold text-nhs-black"
    >
      Skip to main content
    </a>
  );
}
