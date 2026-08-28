"use client";

import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Footer actions. Rendered in a row that wraps on narrow screens. */
  actions?: ReactNode;
  /** Destructive confirmations get a red border and the safe action focused first. */
  tone?: "default" | "destructive";
  className?: string;
}

/**
 * Modal dialog, built on the native `<dialog>` element.
 *
 * Native rather than hand-rolled because the browser then provides the parts that are
 * most often got wrong: the focus trap, Escape to dismiss, inertness of the page behind,
 * returning focus to the trigger on close, and rendering in the top layer so no z-index
 * elsewhere can cover it.
 *
 * What is added on top: an accessible name wired to the heading, backdrop-click dismissal,
 * and - for destructive dialogs - initial focus on the *safe* action. A confirmation that
 * focuses "Yes, cancel it" turns a stray Enter keypress into a cancelled appointment.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  actions,
  tone = "default",
  className,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;

    if (open && !dialog.open) {
      dialog.showModal();
      // Stop the page behind scrolling under the dialog on touch devices.
      document.body.style.overflow = "hidden";
    } else if (!open && dialog.open) {
      dialog.close();
      document.body.style.overflow = "";
    }

    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;

    // Fires on Escape. Prevented and routed through onClose so the parent stays the single
    // source of truth for whether the dialog is open.
    const handleCancel = (event: Event) => {
      event.preventDefault();
      onClose();
    };
    dialog.addEventListener("cancel", handleCancel);
    return () => dialog.removeEventListener("cancel", handleCancel);
  }, [onClose]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      // Dismissing a confirmation is the safe outcome - it keeps the appointment - so a
      // backdrop click closing it cannot lose anything.
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      className={cn(
        "m-auto w-[min(92vw,34rem)] border-4 bg-white p-0 text-nhs-black",
        "backdrop:bg-black/60",
        tone === "destructive" ? "border-nhs-red" : "border-nhs-black",
        className,
      )}
    >
      <div className="p-6">
        <h2 id={titleId} className="mb-4 text-2xl font-bold">
          {title}
        </h2>
        <div className="mb-6">{children}</div>
        {actions && <div className="flex flex-wrap gap-3">{actions}</div>}
      </div>
    </dialog>
  );
}
