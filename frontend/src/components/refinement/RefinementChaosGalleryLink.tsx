/** Optional dogfood link to chaos/fixture tape types for the Refinement pillar. */
export function RefinementChaosGalleryLink() {
  return (
    <p className="hint sm refinement-chaos-link" data-testid="refinement-chaos-gallery-link">
      Dogfood tape shapes: short_clean, asymmetric_technical, panel_multi_guest, long_meander —
      see <code>tests/fixtures/refinement_chaos/</code> and{" "}
      <a href="/docs/cross-cutting/refinement-passes.md">refinement-passes.md</a>.
    </p>
  );
}
