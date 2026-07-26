import type { ReactNode } from "react";

interface Props {
  title: string;
  lead: ReactNode;
  meta?: ReactNode;
  error?: string | null;
  testId?: string;
  ariaLabel: string;
  /** Omitted by banners that are purely informational (loading shell, gate notices). */
  actions?: ReactNode;
  loading?: boolean;
}

export function ReviewGateBannerShell({
  title,
  lead,
  meta,
  error,
  testId,
  ariaLabel,
  actions,
  loading,
}: Props) {
  if (loading) {
    return (
      <section className="tr-gate-banner tr-gate-banner--loading panel-inset" aria-busy>
        <p className="hint">Loading review status…</p>
      </section>
    );
  }

  return (
    <section
      className="tr-gate-banner panel-inset tr-gate-banner--sticky"
      aria-label={ariaLabel}
      data-testid={testId}
    >
      <div className="tr-gate-banner-copy">
        <h3 className="tr-gate-banner-title">{title}</h3>
        <p className="hint sm tr-gate-banner-lead">{lead}</p>
        {meta ? <p className="hint sm tr-gate-banner-meta">{meta}</p> : null}
      </div>
      <div className="tr-gate-banner-actions">{actions}</div>
      {error ? <p className="tr-gate-banner-error">{error}</p> : null}
    </section>
  );
}
