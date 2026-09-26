import type { ButtonHTMLAttributes } from 'react'
import { Link, type LinkProps } from 'react-router'

type Variant = 'outline' | 'solid'

export type ButtonProps = { variant?: Variant } & (
  | ({ to: LinkProps['to'] } & Omit<LinkProps, 'to'>)
  | ({ to?: undefined } & ButtonHTMLAttributes<HTMLButtonElement>)
)

// The design's .btn / .btn-solid. Renders a router Link when `to` is given, else a
// <button type="button">.
export function Button({ variant = 'outline', className, ...props }: ButtonProps) {
  const classes = ['btn', variant === 'solid' && 'btn-solid', className].filter(Boolean).join(' ')
  if (props.to !== undefined) return <Link {...props} className={classes} />
  return <button type="button" {...props} className={classes} />
}
