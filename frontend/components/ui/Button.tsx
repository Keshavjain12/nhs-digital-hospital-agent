import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "warning" | "ghost";
type Size = "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Shows a busy state and blocks repeat submits. */
  loading?: boolean;
  /** Announced to screen readers while loading. */
  loadingText?: string;
  fullWidth?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  // The 4px inset shadow is the NHS.UK button "lip". It is not decoration: it makes the
  // press state perceivable without relying on colour change alone.
  primary:
    "bg-nhs-green text-white shadow-[inset_0_-4px_0_0_#00401e] hover:bg-[#00662f] active:top-[2px] active:shadow-none",
  secondary:
    "bg-nhs-pale-grey text-nhs-black shadow-[inset_0_-4px_0_0_#b6bfc2] hover:bg-[#d8dfe0] active:top-[2px] active:shadow-none",
  warning:
    "bg-nhs-red text-white shadow-[inset_0_-4px_0_0_#7c1509] hover:bg-[#b31c12] active:top-[2px] active:shadow-none",
  ghost:
    "bg-transparent text-nhs-blue underline hover:text-nhs-dark-blue hover:decoration-[3px]",
};

const SIZES: Record<Size, string> = {
  // 44px minimum height. WCAG 2.5.5 target size, and the practical floor for a nurse
  // tapping a tablet with gloves on.
  md: "min-h-[44px] px-4 py-2 text-base",
  lg: "min-h-[52px] px-6 py-3 text-lg",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    loadingText = "Loading",
    fullWidth = false,
    disabled,
    className,
    children,
    type = "button",
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      // Disabled while loading so a double-click cannot submit a booking twice. The
      // backend also guards this, but the UI should not invite the mistake.
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "relative inline-flex items-center justify-center gap-2 rounded font-bold",
        "transition-colors focus-visible:outline-3",
        "disabled:opacity-60 disabled:cursor-not-allowed disabled:shadow-none",
        VARIANTS[variant],
        SIZES[size],
        fullWidth && "w-full",
        className,
      )}
      {...props}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      <span>{children}</span>
      {/* Announced politely rather than swapping the label, so the button's accessible
          name stays stable for anyone navigating by control name. */}
      {loading && <span className="sr-only">{loadingText}</span>}
    </button>
  );
});
