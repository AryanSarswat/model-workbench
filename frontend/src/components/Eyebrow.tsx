import type { ReactNode } from 'react'

// Small mono uppercase label. Use `as="h2"` where it titles a section.
export function Eyebrow({
  as: Tag = 'div',
  id,
  className,
  children,
}: {
  as?: 'div' | 'span' | 'h2' | 'p'
  id?: string
  className?: string
  children: ReactNode
}) {
  return (
    <Tag id={id} className={['eyebrow', className].filter(Boolean).join(' ')} style={{ margin: 0 }}>
      {children}
    </Tag>
  )
}
