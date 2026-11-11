import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '../../lib'

const variants = cva('button', {
  variants: { variant: { default: 'button-default', secondary: 'button-secondary', ghost: 'button-ghost' }, size: { default: '', sm: 'button-sm', icon: 'button-icon' } },
  defaultVariants: { variant: 'secondary', size: 'default' },
})
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof variants> { asChild?: boolean }
export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button'
  return <Comp className={cn(variants({ variant, size }), className)} {...props} />
}
