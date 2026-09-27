import type { ReactNode } from 'react'
import { cx } from '../lib/cx'

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
    <Tag id={id} className={cx('eyebrow', className)} style={{ margin: 0 }}>
      {children}
    </Tag>
  )
}
