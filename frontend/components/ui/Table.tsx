import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** Hidden below md, shown as a labelled line in the stacked card instead. */
  secondary?: boolean;
}

export interface TableProps<T> {
  caption: string;
  columns: ReadonlyArray<Column<T>>;
  rows: readonly T[];
  rowKey: (row: T) => string;
  emptyMessage?: string;
}

/**
 * Responsive data table.
 *
 * Below md it becomes a list of stacked cards, each cell labelled with its column header.
 * A horizontally scrolling table on a phone is technically responsive and practically
 * unusable - brief §2 asks for intentional layouts per breakpoint, not a shrunk desktop.
 *
 * The `<caption>` is not decoration: it is how a screen reader user knows what the table
 * contains before stepping into it.
 */
export function Table<T>({
  caption,
  columns,
  rows,
  rowKey,
  emptyMessage = "No results found.",
}: TableProps<T>) {
  if (rows.length === 0) {
    return (
      <p className="border border-nhs-mid-grey bg-nhs-pale-grey p-6 text-center">
        {emptyMessage}
      </p>
    );
  }

  return (
    <>
      {/* Desktop and tablet */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b-2 border-nhs-black">
              {columns.map((column) => (
                <th key={column.key} scope="col" className="p-3 font-bold">
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)} className="border-b border-nhs-pale-grey">
                {columns.map((column) => (
                  <td key={column.key} className="p-3 align-top">
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile */}
      <ul className="space-y-4 md:hidden">
        <li className="sr-only">{caption}</li>
        {rows.map((row) => (
          <li key={rowKey(row)} className="border border-nhs-mid-grey p-4">
            <dl className="space-y-2">
              {columns.map((column) => (
                <div key={column.key}>
                  <dt className="text-sm font-bold text-nhs-dark-grey">{column.header}</dt>
                  <dd>{column.cell(row)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}

export function Badge({
  children,
  tone = "neutral",
  icon,
}: {
  children: ReactNode;
  tone?: "neutral" | "info" | "attention" | "success";
  icon?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 border-2 px-2 py-0.5 text-sm font-bold",
        tone === "neutral" && "border-nhs-mid-grey text-nhs-dark-grey",
        tone === "info" && "border-nhs-blue text-nhs-blue",
        tone === "attention" && "border-nhs-red text-nhs-red",
        tone === "success" && "border-nhs-green text-nhs-green",
      )}
    >
      {/* The icon is decorative; the text carries the meaning, so colour is never alone. */}
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </span>
  );
}
