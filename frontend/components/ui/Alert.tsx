"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "warning" | "error";

const TONES: Record<Tone, { border: string; icon: string; label: string }> = {
  // Each tone carries an icon and a word as well as a colour. A red border alone is
  // invisible to a screen reader and ambiguous to a colour-blind user.
  info: { border: "border-nhs-blue", icon: "i", label: "Information" },
  success: { border: "border-nhs-green", icon: "✓", label: "Success" },
  warning: { border: "border-nhs-warm-yellow", icon: "!", label: "Important" },
  error: { border: "border-nhs-red", icon: "⚠", label: "Error" },
};

export interface AlertProps {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  /** Moves keyboard focus here on mount. Use for form-level errors after a failed submit. */
  focusOnMount?: boolean;
  className?: string;
}

export function Alert({
  tone = "info",
  title,
  children,
  focusOnMount = false,
  className,
}: AlertProps) {
  const ref = useRef<HTMLDivElement>(null);
  const { border, icon, label } = TONES[tone];

  useEffect(() => {
    if (focusOnMount) ref.current?.focus();
  }, [focusOnMount]);

  return (
    <div
      ref={ref}
      // assertive for errors: the user has just submitted and is waiting on the outcome,
      // so interrupting is correct. Anything else waits its turn.
      role={tone === "error" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
      tabIndex={focusOnMount ? -1 : undefined}
      className={cn(
        "mb-6 border-l-8 bg-white p-4 focus-visible:outline-3",
        border,
        className,
      )}
    >
      <div className="flex gap-3">
        <span
          aria-hidden="true"
          className={cn(
            "flex size-6 shrink-0 items-center justify-center rounded-full font-bold text-white",
            tone === "info" && "bg-nhs-blue",
            tone === "success" && "bg-nhs-green",
            tone === "warning" && "bg-nhs-warm-yellow text-nhs-black",
            tone === "error" && "bg-nhs-red",
          )}
        >
          {icon}
        </span>
        <div>
          {/* The tone is stated in text for screen reader users, who get no colour. */}
          <span className="sr-only">{label}: </span>
          {title && <h2 className="mb-1 text-lg font-bold">{title}</h2>}
          <div className="text-base">{children}</div>
        </div>
      </div>
    </div>
  );
}

export interface ErrorSummaryProps {
  errors: ReadonlyArray<{ field: string; message: string }>;
  title?: string;
}

/**
 * The NHS.UK error summary pattern: one block at the top of the form listing every
 * problem, each linking to the field that caused it.
 *
 * This exists because a user with a screen magnifier may never see an inline error
 * further down a long form, and because keyboard users need a way to jump straight to
 * the first problem rather than tabbing through the whole form to find it.
 */
export function ErrorSummary({ errors, title = "There is a problem" }: ErrorSummaryProps) {
  if (errors.length === 0) return null;

  return (
    <Alert tone="error" title={title} focusOnMount>
      <ul className="list-none space-y-1">
        {errors.map((error) => (
          <li key={error.field}>
            <a
              href={`#${error.field}`}
              className="font-bold text-nhs-red underline"
              onClick={(event) => {
                event.preventDefault();
                const target = document.querySelector<HTMLElement>(
                  `[name="${error.field}"]`,
                );
                target?.focus();
                target?.scrollIntoView({ block: "center" });
              }}
            >
              {error.message}
            </a>
          </li>
        ))}
      </ul>
    </Alert>
  );
}
