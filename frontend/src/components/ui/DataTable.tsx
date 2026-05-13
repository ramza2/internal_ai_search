import type { ReactNode, TableHTMLAttributes } from "react";

export function DataTable({
  children,
  className,
  ...rest
}: TableHTMLAttributes<HTMLTableElement> & { children: ReactNode }) {
  return (
    <div className="tableWrap">
      <table className={["dataTable", className].filter(Boolean).join(" ")} {...rest}>
        {children}
      </table>
    </div>
  );
}
