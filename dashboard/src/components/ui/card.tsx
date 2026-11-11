import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib'
export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) { return <section className={cn('card', className)} {...props} /> }
export function CardHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="card-header"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>
}
