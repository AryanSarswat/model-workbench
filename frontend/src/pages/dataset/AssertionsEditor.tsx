import styles from './DatasetPage.module.css'
import { RemoveIcon } from './RemoveIcon'
import { ASSERTION_TYPES, assertionArgPlaceholder, assertionNeedsArgument, type CaseFormState } from './testCaseForm'

type Assertion = CaseFormState['assertions'][number]

// The case editor's Assertions fieldset: one type/argument row per assertion.
export function AssertionsEditor({
  assertions,
  onUpdate,
  onRemove,
  onAdd,
}: {
  assertions: Assertion[]
  onUpdate: (index: number, patch: Partial<Assertion>) => void
  onRemove: (index: number) => void
  onAdd: () => void
}) {
  return (
    <fieldset className={styles.assertions}>
      <legend className={['eyebrow', styles.assertionLegend].join(' ')}>Assertions</legend>
      {assertions.map((assertion, index) => (
        <div key={index} className={styles.assertionRow}>
          <select
            className={[styles.mono, 'field'].filter(Boolean).join(' ')}
            aria-label={`Assertion ${index + 1} type`}
            value={assertion.type}
            onChange={(e) => onUpdate(index, { type: e.target.value as Assertion['type'] })}
          >
            {ASSERTION_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <input
            className={[styles.mono, 'field'].filter(Boolean).join(' ')}
            aria-label={`Assertion ${index + 1} value`}
            value={assertion.argument}
            placeholder={assertionArgPlaceholder(assertion.type)}
            disabled={!assertionNeedsArgument(assertion.type)}
            onChange={(e) => onUpdate(index, { argument: e.target.value })}
          />
          <button
            type="button"
            aria-label={`Remove assertion ${index + 1}`}
            className={styles.iconButton}
            onClick={() => onRemove(index)}
          >
            <RemoveIcon />
          </button>
        </div>
      ))}
      <button type="button" className={styles.linkButton} onClick={onAdd}>
        Add assertion
      </button>
    </fieldset>
  )
}
