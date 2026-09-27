// Joins class names, skipping falsy ones: cx('btn', active && 'btn-solid', className).
export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ')
}
