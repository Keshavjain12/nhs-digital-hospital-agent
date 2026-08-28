import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * A link that looks like a button.
 *
 * Navigation is a link, not a button: it belongs in the browser's link semantics, opens in
 * a new tab on middle-click, and is announced correctly. Using a <button> with
 * window.location would also force a full page reload, which discards the in-memory access
 * token and costs an extra refresh round-trip.
 */
export function ButtonLink({
  href,
  children,
  variant = "primary",
  size = "md",
  className,
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary";
  size?: "md" | "lg";
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "relative inline-flex items-center justify-center gap-2 rounded font-bold no-underline",
        "transition-colors focus-visible:outline-3",
        variant === "primary" &&
          "bg-nhs-green text-white shadow-[inset_0_-4px_0_0_#00401e] hover:bg-[#00662f] hover:text-white",
        variant === "secondary" &&
          "bg-nhs-pale-grey text-nhs-black shadow-[inset_0_-4px_0_0_#b6bfc2] hover:bg-[#d8dfe0] hover:text-nhs-black",
        size === "md" && "min-h-[44px] px-4 py-2 text-base",
        size === "lg" && "min-h-[52px] px-6 py-3 text-lg",
        className,
      )}
    >
      {children}
    </Link>
  );
}
