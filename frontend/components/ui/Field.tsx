"use client";

import { forwardRef, useId } from "react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

interface FieldShellProps {
  label: string;
  /** Guidance shown under the label. Wired to the input via aria-describedby. */
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  children: (ids: { inputId: string; describedBy: string | undefined }) => ReactNode;
}

/**
 * The label / hint / error wrapper every form control shares.
 *
 * Centralising it is what makes the accessibility guarantees hold: the label is always a
 * real `<label for>`, hint and error are always joined into `aria-describedby`, and the
 * error is always announced. Per-component markup is where those quietly get dropped.
 */
function FieldShell({ label, hint, error, required, children }: FieldShellProps) {
  const inputId = useId();
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;

  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cn("mb-6", error && "border-l-4 border-nhs-red pl-4")}>
      <label htmlFor={inputId} className="mb-1 block text-base font-bold text-nhs-black">
        {label}
        {required ? (
          <span className="ml-1 font-normal text-nhs-dark-grey">(required)</span>
        ) : (
          // Optional is stated explicitly. Marking only required fields leaves the user
          // guessing what an unmarked field means.
          <span className="ml-1 font-normal text-nhs-dark-grey">(optional)</span>
        )}
      </label>

      {hint && (
        <p id={hintId} className="mb-2 text-base text-nhs-dark-grey">
          {hint}
        </p>
      )}

      {error && (
        <p id={errorId} className="mb-2 font-bold text-nhs-red">
          {/* Prefixed with a word, not just a colour and an icon: colour is never the
              sole carrier of meaning (WCAG 1.4.1). */}
          <span className="mr-1" aria-hidden="true">
            ⚠
          </span>
          <span className="sr-only">Error: </span>
          {error}
        </p>
      )}

      {children({ inputId, describedBy })}
    </div>
  );
}

export interface TextInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "aria-describedby"> {
  label: string;
  hint?: ReactNode;
  error?: string;
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(function TextInput(
  { label, hint, error, required, className, ...props },
  ref,
) {
  return (
    <FieldShell label={label} hint={hint} error={error} required={required}>
      {({ inputId, describedBy }) => (
        <input
          ref={ref}
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          // `required` is deliberately not set on the DOM node. Native validation
          // bubbles are unstyleable, vanish on blur, and are not reliably announced;
          // validation is handled in the app so every error behaves identically.
          className={cn(
            "block w-full min-h-[44px] rounded-none border-2 bg-white px-3 py-2 text-base",
            "border-nhs-black",
            error && "border-nhs-red",
            "disabled:cursor-not-allowed disabled:bg-nhs-pale-grey",
            className,
          )}
          {...props}
        />
      )}
    </FieldShell>
  );
});

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id" | "aria-describedby"> {
  label: string;
  hint?: ReactNode;
  error?: string;
  options: ReadonlyArray<{ value: string; label: string }>;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, required, options, className, ...props },
  ref,
) {
  return (
    <FieldShell label={label} hint={hint} error={error} required={required}>
      {({ inputId, describedBy }) => (
        <select
          ref={ref}
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={cn(
            "block w-full min-h-[44px] rounded-none border-2 border-nhs-black bg-white px-3 py-2 text-base",
            error && "border-nhs-red",
            className,
          )}
          {...props}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
});
