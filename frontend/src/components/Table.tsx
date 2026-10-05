import {
  forwardRef,
  type HTMLAttributes,
  type ReactNode,
  type TableHTMLAttributes,
  type TdHTMLAttributes,
  type ThHTMLAttributes,
} from 'react'
import './components.css'

export interface TableProps extends TableHTMLAttributes<HTMLTableElement> {
  caption?: ReactNode
  wrapClassName?: string
}

export const Table = forwardRef<HTMLTableElement, TableProps>(
  ({ caption, className = '', wrapClassName = '', children, ...props }, ref) => (
    <div className={`ui-table-wrap ${wrapClassName}`.trim()}>
      <table ref={ref} className={`ui-table ${className}`.trim()} {...props}>
        {caption ? <caption className="ui-table__caption">{caption}</caption> : null}
        {children}
      </table>
    </div>
  ),
)

Table.displayName = 'Table'

export const TableHead = forwardRef<
  HTMLTableSectionElement,
  HTMLAttributes<HTMLTableSectionElement>
>(({ className = '', ...props }, ref) => (
  <thead ref={ref} className={`ui-table__head ${className}`.trim()} {...props} />
))
TableHead.displayName = 'TableHead'

export const TableBody = forwardRef<
  HTMLTableSectionElement,
  HTMLAttributes<HTMLTableSectionElement>
>(({ className = '', ...props }, ref) => (
  <tbody ref={ref} className={`ui-table__body ${className}`.trim()} {...props} />
))
TableBody.displayName = 'TableBody'

export const TableRow = forwardRef<
  HTMLTableRowElement,
  HTMLAttributes<HTMLTableRowElement>
>(({ className = '', ...props }, ref) => (
  <tr ref={ref} className={`ui-table__row ${className}`.trim()} {...props} />
))
TableRow.displayName = 'TableRow'

export const TableHeaderCell = forwardRef<
  HTMLTableCellElement,
  ThHTMLAttributes<HTMLTableCellElement>
>(({ className = '', ...props }, ref) => (
  <th ref={ref} className={`ui-table__th ${className}`.trim()} {...props} />
))
TableHeaderCell.displayName = 'TableHeaderCell'

export const TableCell = forwardRef<
  HTMLTableCellElement,
  TdHTMLAttributes<HTMLTableCellElement>
>(({ className = '', ...props }, ref) => (
  <td ref={ref} className={`ui-table__td ${className}`.trim()} {...props} />
))
TableCell.displayName = 'TableCell'
