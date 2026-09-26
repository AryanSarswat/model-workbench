import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createCase, updateCase, deleteCase } from '../../api/endpoints'
import type { ToolSpec } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Field } from '../../components/Field'
import styles from './DatasetPage.module.css'
import {
  ASSERTION_TYPES,
  assertionArgPlaceholder,
  assertionNeedsArgument,
  duplicateForm,
  formToCase,
  type CaseFormState,
} from './testCaseForm'

const ROLE_OPTIONS: CaseFormState['messages'][number]['role'][] = ['user', 'assistant', 'system']

export function CaseEditor({
  form,
  setForm,
  isNew,
  tools,
  onSaved,
  onDuplicated,
  onDeleted,
}: {
  form: CaseFormState
  setForm: (form: CaseFormState) => void
  isNew: boolean
  tools: ToolSpec[]
  onSaved: (id: string, category: string) => void
  onDuplicated: (form: CaseFormState) => void
  onDeleted: () => void
}) {
  const queryClient = useQueryClient()
  // DatasetPage remounts this component (via `key`) whenever the case being edited
  // changes, so this never needs to be reset explicitly.
  const [validationErrors, setValidationErrors] = useState<string[]>([])

  const saveMutation = useMutation({
    mutationFn: (payload: typeof form) => {
      const { testCase } = formToCase(payload)
      if (!testCase) throw new Error('Invalid form state')
      return isNew ? createCase(testCase) : updateCase(testCase)
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ['dataset', 'cases'] })
      onSaved(saved.id, saved.category)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCase(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['dataset', 'cases'] })
      onDeleted()
    },
  })

  function handleSave() {
    const { testCase, errors } = formToCase(form)
    setValidationErrors(errors)
    if (!testCase) return
    saveMutation.mutate(form)
  }

  function updateMessage(index: number, patch: Partial<CaseFormState['messages'][number]>) {
    setForm({
      ...form,
      messages: form.messages.map((m, i) => (i === index ? { ...m, ...patch } : m)),
    })
  }

  function addMessage() {
    setForm({ ...form, messages: [...form.messages, { role: 'user', content: '' }] })
  }

  function removeMessage(index: number) {
    setForm({ ...form, messages: form.messages.filter((_, i) => i !== index) })
  }

  function updateAssertion(index: number, patch: Partial<CaseFormState['assertions'][number]>) {
    setForm({
      ...form,
      assertions: form.assertions.map((a, i) => (i === index ? { ...a, ...patch } : a)),
    })
  }

  function addAssertion() {
    setForm({ ...form, assertions: [...form.assertions, { type: 'schema_valid', argument: '' }] })
  }

  function removeAssertion(index: number) {
    setForm({ ...form, assertions: form.assertions.filter((_, i) => i !== index) })
  }

  function toggleTool(name: string, checked: boolean) {
    setForm({
      ...form,
      expectedTools: checked ? [...form.expectedTools, name] : form.expectedTools.filter((t) => t !== name),
    })
  }

  function handleDelete() {
    if (!window.confirm(`Delete test case "${form.id}"? This cannot be undone.`)) return
    deleteMutation.mutate(form.id)
  }

  return (
    <form
      aria-label={isNew ? 'New case' : `Edit ${form.id}`}
      className={styles.editor}
      onSubmit={(e) => {
        e.preventDefault()
        handleSave()
      }}
    >
      <div className={styles.idRow}>
        <Field label="ID" htmlFor="case-id">
          <input
            id="case-id"
            className={[styles.mono, isNew ? '' : styles.readonlyField, 'field'].filter(Boolean).join(' ')}
            value={form.id}
            readOnly={!isNew}
            onChange={(e) => setForm({ ...form, id: e.target.value })}
          />
        </Field>
        <Field label="Category" htmlFor="case-category">
          <input
            id="case-category"
            className={[styles.mono, 'field'].filter(Boolean).join(' ')}
            list="dataset-categories"
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          />
        </Field>
        <Field label="Tags" htmlFor="case-tags">
          <input
            id="case-tags"
            className="field"
            value={form.tags}
            placeholder="comma, separated"
            onChange={(e) => setForm({ ...form, tags: e.target.value })}
          />
        </Field>
      </div>

      <div className={styles.column}>
        <div>
          <span className="eyebrow">Messages</span>
          <div className={styles.messages} style={{ marginTop: 8 }}>
            {form.messages.map((message, index) => (
              <div key={index} className={form.messages.length > 1 ? styles.messageRowWithRemove : styles.messageRow}>
                <label htmlFor={`msg-role-${index}`} className={styles.srOnly}>
                  Role
                </label>
                <select
                  id={`msg-role-${index}`}
                  className={[styles.mono, 'field'].filter(Boolean).join(' ')}
                  value={message.role}
                  onChange={(e) => updateMessage(index, { role: e.target.value as CaseFormState['messages'][number]['role'] })}
                >
                  {ROLE_OPTIONS.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
                <label htmlFor={`msg-content-${index}`} className={styles.srOnly}>
                  Content
                </label>
                <textarea
                  id={`msg-content-${index}`}
                  className={styles.area}
                  rows={2}
                  style={{ height: 60 }}
                  value={message.content}
                  onChange={(e) => updateMessage(index, { content: e.target.value })}
                />
                {form.messages.length > 1 && (
                  <button
                    type="button"
                    aria-label={`Remove message ${index + 1}`}
                    className={styles.iconButton}
                    onClick={() => removeMessage(index)}
                  >
                    <RemoveIcon />
                  </button>
                )}
              </div>
            ))}
          </div>
          <button type="button" className={styles.linkButton} onClick={addMessage}>
            Add message
          </button>
        </div>
        <Field label="System prompt · optional" htmlFor="case-system">
          <textarea
            id="case-system"
            className={styles.area}
            rows={1}
            style={{ height: 40 }}
            placeholder="None"
            value={form.systemPrompt}
            onChange={(e) => setForm({ ...form, systemPrompt: e.target.value })}
          />
        </Field>
        <Field label="Judge criteria · optional" htmlFor="case-judge">
          <textarea
            id="case-judge"
            className={styles.area}
            rows={2}
            style={{ height: 60 }}
            value={form.judgeCriteria}
            onChange={(e) => setForm({ ...form, judgeCriteria: e.target.value })}
          />
        </Field>
      </div>

      <div className={styles.column}>
        <Field label="Output schema · optional" htmlFor="case-schema">
          <textarea
            id="case-schema"
            className={[styles.area, styles.schemaArea].join(' ')}
            rows={7}
            placeholder="{}"
            value={form.outputSchema}
            onChange={(e) => setForm({ ...form, outputSchema: e.target.value })}
          />
        </Field>
        <div>
          <span className="eyebrow">Expected tools · optional</span>
          <div className={styles.tools} style={{ marginTop: 8 }}>
            {tools.length === 0 && <p className={styles.footerNote}>No tools registered.</p>}
            {tools.map((tool) => (
              <label key={tool.name} className={styles.toolCheckbox}>
                <input
                  type="checkbox"
                  checked={form.expectedTools.includes(tool.name)}
                  onChange={(e) => toggleTool(tool.name, e.target.checked)}
                />
                <span className={styles.mono}>{tool.name}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <fieldset className={styles.assertions}>
        <legend className={['eyebrow', styles.assertionLegend].join(' ')}>Assertions</legend>
        {form.assertions.map((assertion, index) => (
          <div key={index} className={styles.assertionRow}>
            <select
              className={[styles.mono, 'field'].filter(Boolean).join(' ')}
              aria-label="Assertion type"
              value={assertion.type}
              onChange={(e) => updateAssertion(index, { type: e.target.value as CaseFormState['assertions'][number]['type'] })}
            >
              {ASSERTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <input
              className={[styles.mono, 'field'].filter(Boolean).join(' ')}
              aria-label="Assertion value"
              value={assertion.argument}
              placeholder={assertionArgPlaceholder(assertion.type)}
              disabled={!assertionNeedsArgument(assertion.type)}
              onChange={(e) => updateAssertion(index, { argument: e.target.value })}
            />
            <button
              type="button"
              aria-label="Remove assertion"
              className={styles.iconButton}
              onClick={() => removeAssertion(index)}
            >
              <RemoveIcon />
            </button>
          </div>
        ))}
        <button type="button" className={styles.linkButton} onClick={addAssertion}>
          Add assertion
        </button>
      </fieldset>

      {validationErrors.length > 0 && (
        <div className={styles.errors}>
          {validationErrors.map((error) => (
            <ErrorNotice key={error} error={new Error(error)} />
          ))}
        </div>
      )}
      {saveMutation.isError && <ErrorNotice error={saveMutation.error} className={styles.errorRow} />}
      {deleteMutation.isError && <ErrorNotice error={deleteMutation.error} className={styles.errorRow} />}

      <div className={styles.footer}>
        <button type="submit" className={['btn', 'btn-solid', styles.saveButton].join(' ')} disabled={saveMutation.isPending}>
          Save
        </button>
        <button type="button" className="btn" onClick={() => onDuplicated(duplicateForm(form))}>
          Duplicate
        </button>
        <span className={styles.footerNote}>
          {isNew ? 'Writes data/test_cases/<id>.json' : `Writes data/test_cases/${form.id}.json`}
        </span>
        {!isNew && (
          <button type="button" className={['btn', styles.deleteButton].join(' ')} onClick={handleDelete}>
            Delete case
          </button>
        )}
      </div>
    </form>
  )
}

function RemoveIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  )
}
