import type { SVGProps } from 'react'

// Stroked 16x16 icons in currentColor. Decorative (aria-hidden) unless given an
// aria-label; size and any SVG attribute can be overridden per call site.
type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Icon({ size = 16, children, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      aria-hidden={props['aria-label'] ? undefined : true}
      {...props}
    >
      {children}
    </svg>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <Icon size={13} strokeWidth={2} {...props}>
      <path d="M3 8.5l3 3 7-7" />
    </Icon>
  )
}

export function CrossIcon(props: IconProps) {
  return (
    <Icon size={12} strokeWidth={2} {...props}>
      <path d="M4 4l8 8M12 4l-8 8" />
    </Icon>
  )
}

export function PlusIcon(props: IconProps) {
  return (
    <Icon size={13} strokeWidth={2} {...props}>
      <path d="M8 3v10M3 8h10" />
    </Icon>
  )
}

export function TrashIcon(props: IconProps) {
  return (
    <Icon size={14} strokeWidth={1.6} {...props}>
      <path d="M2.5 4h11M6 4V2.5h4V4M4 4l.8 9.5h6.4L12 4" />
    </Icon>
  )
}

export function RefreshIcon(props: IconProps) {
  return (
    <Icon size={14} strokeWidth={1.6} {...props}>
      <path d="M13 2.5v4H9M3 13.5v-4h4M12.6 6.5A5 5 0 0 0 3.8 5M3.4 9.5A5 5 0 0 0 12.2 11" />
    </Icon>
  )
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Icon size={13} strokeWidth={1.8} {...props}>
      <path d="M3 8h10M9 4l4 4-4 4" />
    </Icon>
  )
}

export function ExternalLinkIcon(props: IconProps) {
  return (
    <Icon size={13} strokeWidth={1.6} {...props}>
      <path d="M7 3H3v10h10V9M10 3h3v3M13 3L7.5 8.5" />
    </Icon>
  )
}

// Filled square, used for "Stop".
export function StopIcon(props: IconProps) {
  return (
    <Icon size={12} fill="currentColor" stroke="none" {...props}>
      <rect x="3" y="3" width="10" height="10" />
    </Icon>
  )
}
