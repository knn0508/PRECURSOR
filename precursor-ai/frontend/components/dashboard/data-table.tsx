import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  emptyMessage: string;
  caption?: string;
}

export function DataTable<T>({ columns, rows, rowKey, emptyMessage, caption }: DataTableProps<T>) {
  if (rows.length === 0) {
    return <p className="px-1 py-6 text-center text-sm text-ink-faint">{emptyMessage}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wider text-ink-faint">
            {columns.map((c) => (
              <th key={c.key} scope="col" className={cn("px-3 py-2 font-medium", c.className)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-line/60 last:border-0">
              {columns.map((c) => (
                <td key={c.key} className={cn("px-3 py-2.5 text-ink-muted", c.className)}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
