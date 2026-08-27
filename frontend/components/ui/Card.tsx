import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface CardProps {
  title?: string;
  /** Heading level. Never skip levels: screen reader users navigate by heading. */
  headingLevel?: 2 | 3 | 4;
  children: ReactNode;
  className?: string;
}

export function Card({ title, headingLevel = 2, children, className }: CardProps) {
  const Heading = `h${headingLevel}` as const;

  return (
    <section className={cn("border border-nhs-mid-grey bg-white p-6", className)}>
      {title && <Heading className="mb-4 text-2xl font-bold">{title}</Heading>}
      {children}
    </section>
  );
}
