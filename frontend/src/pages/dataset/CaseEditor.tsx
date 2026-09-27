import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createCase, updateCase, deleteCase } from '../../api/endpoints'
import { queryKeys } from '../../api/hooks'
import type { TestCase, ToolSpec } from '../../api/types'
import { Button } from '../../components/Button'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Field } from '../../components/Field'
import { cx } from '../../lib/cx'
import styles from './DatasetPage.module.css'
import { AssertionsEditor } from './AssertionsEditor'
import { RemoveIcon } from './RemoveIcon'
import {
  duplicateForm,
  formToCase,
  type CaseFormState,
} from './testCaseForm'

const ROLE_OPTIONS: CaseFormState['messages'][number]['role'][] = ['user', 'assistant', 'system']

export function CaseEditor({
  initialForm,
  isNew,
  tools,
  onSaved,
  onDuplicated,
  onDeleted,
}: {
  initialForm: CaseFormState
  isNew: boolean
  tools: ToolSpec[]
  onSaved: (saved: TestCase) => void
  onDuplicated: (draft: CaseFormState) => void
  onDeleted: () => void
}) {
  const queryClient = useQueryClient()
  // The parent remounts this component (via `key={caseParam}`) whenever the case being
  // edited changes, so this only ever initializes once per case -- no sync effect needed.
  const [form, setForm] = useState<CaseFormState>(initialForm)
  const [validationErrors, setValidationErrors] = useState<string[]>([])

  const saveMutation = useMutation({
    mutationFn: (testCase: TestCase) => (isNew ? createCase(testCase) : updateCase(testCase)),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.datasetCases })
      onSaved(saved)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCase(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.datasetCases })
      onDeleted()
    },
  })

  function handleSave() {
    const { testCase, errors } = formToCase(form)
    setValidationErrors(errors)
    if (!testCase) return
    saveMutation.mutate(testCase)
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
            className={cx(styles.mono, !isNew && styles.readonlyField, 'field')}
            value={form.id}
            readOnly={!isNew}
            onChange={(e) => setForm({ ...form, id: e.target.value })}
          />
        </Field>
        <Field label="Category" htmlFor="case-category">
          <input
            id="case-category"
            className={cx(styles.mono, 'field')}
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
                  Message {index + 1} role
                </label>
                <select
                  id={`msg-role-${index}`}
                  className={cx(styles.mono, 'field')}
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
                  Message {index + 1} content
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
            className={cx(styles.area, styles.schemaArea)}
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

      <AssertionsEditor
        assertions={form.assertions}
        onUpdate={updateAssertion}
        onRemove={removeAssertion}
        onAdd={addAssertion}
      />

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
        <Button type="submit" variant="solid" className={styles.saveButton} disabled={saveMutation.isPending}>
          Save
        </Button>
        <Button onClick={() => onDuplicated(duplicateForm(form))}>Duplicate</Button>
        <span className={styles.footerNote}>
          {isNew ? 'Writes data/test_cases/<id>.json' : `Writes data/test_cases/${form.id}.json`}
        </span>
        {!isNew && (
          <Button className={styles.deleteButton} onClick={handleDelete}>
            Delete case
          </Button>
        )}
      </div>
    </form>
  )
}
