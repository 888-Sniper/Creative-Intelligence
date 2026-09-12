import type { ButtonHTMLAttributes, ReactNode } from "react";

interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** True while this button's own async action is in flight. The
   *  animated spinner renders ONLY on this button — a shared/global
   *  busy flag may disable siblings but must never light up their
   *  spinners, so pass a per-action flag here. */
  loading: boolean;
  /** Label shown beside the spinner while loading
   *  (e.g. "Signing In…", "Preparing…"). */
  loadingLabel: ReactNode;
  /** Idle content (label, icons). */
  children: ReactNode;
  /** Spinner tone: "spinner" on filled/dark buttons, "spinner dark"
   *  on light/outline buttons. */
  spinnerClass?: string;
}

/** One global async-button system: spinner + loading label while this
 *  button's action runs, automatic disable to avoid double submit.
 *  Dimension stability: idle and loading faces share one grid cell and
 *  the hidden face stays in layout (visibility, not display), so the
 *  button keeps max(idle, loading) width and never shrinks or shifts
 *  surrounding content mid-request. */
export function LoadingButton({
  loading,
  loadingLabel,
  children,
  spinnerClass = "spinner",
  ...buttonProps
}: LoadingButtonProps) {
  const { disabled, ...rest } = buttonProps;
  return (
    <button {...rest} disabled={disabled || loading} aria-busy={loading}>
      <span className="lb-stack">
        <span className="lb-face" aria-hidden={loading || undefined}>
          {children}
        </span>
        <span className="lb-face" aria-hidden={loading ? undefined : true}>
          <span className={spinnerClass} aria-hidden="true" />
          <span>{loadingLabel}</span>
        </span>
      </span>
    </button>
  );
}
