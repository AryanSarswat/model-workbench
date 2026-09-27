import { useState } from 'react'
import { ApiError } from '../../api/client'
import type { AssertionResult, EvalResult, TestCase } from '../../api/types'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import styles from './ReviewPage.module.css'
import { useCase, useUpdateEvalResult } from './queries'
import { lastUserMessage, verdictUpdatePayload, type VerdictChoice } from './reviewLogic'

export function CasePanel({ result }: { result: EvalResult }) {
  const caseQuery = useCase(result.case_id)
  const notFound = caseQuery.error instanceof ApiError && caseQuery.error.status === 404

  return (
    <section className={styles.panel} aria-label={`Case ${result.case_id}`}>
      <div className={styles.section}>
        <div className="eyebrow">Prompt</div>
        {caseQuery.isPending && <p className={styles.prompt}>Loading…</p>}
        {caseQuery.isError && (
          <p className={styles.prompt}>{notFound ? 'This case is no longer in the dataset.' : caseQuery.error.message}</p>
        )}
        {caseQuery.data && (
          <>
            <p className={styles.prompt}>{lastUserMessage(caseQuery.data) ?? '(no user message)'}</p>
            <PromptNote testCase={caseQuery.data} />
          </>
        )}
      </div>

      <div className={styles.section}>
        <div className="eyebrow">Response</div>
        {result.error ? <ErrorNotice error={new Error(result.error)} /> : <pre className={styles.code}>{prettyResponse(result.response)}</pre>}
      </div>

      <div className={styles.chipRow}>
        <Chip tone="idle">{result.structured_output_mode ? `JSON · ${result.structured_output_mode}` : 'JSON · none'}</Chip>
        <Chip tone="idle">{result.retries === 0 ? 'first try' : `${result.retries} retries`}</Chip>
        <Chip tone="idle">{result.tools_called ? `tools · ${result.tools_called}` : 'tools · none called'}</Chip>
        <Chip tone="idle">{result.native_tool_calling ? 'native tool calling' : 'no native tool calling'}</Chip>
      </div>
    </section>
  )
}

function prettyResponse(response: string): string {
  try {
    return JSON.stringify(JSON.parse(response), null, 2)
  } catch {
    return response
  }
}

function PromptNote({ testCase }: { testCase: TestCase }) {
  const required = Array.isArray(testCase.output_schema?.required) ? (testCase.output_schema.required as string[]) : []
  if (!testCase.system_prompt && !testCase.output_schema) return null
  return (
    <>
      {testCase.system_prompt && <div className={styles.note}>System prompt: {testCase.system_prompt}</div>}
      {testCase.output_schema && (
        <div className={styles.note}>
          {required.length > 0 ? (
            <>
              Output schema requires{' '}
              {required.map((field, i) => (
                <span key={field}>
                  {i > 0 && (i === required.length - 1 ? ' and ' : ', ')}
                  <code>{field}</code>
                </span>
              ))}
            </>
          ) : (
            'Response must match an output schema'
          )}
        </div>
      )}
    </>
  )
}

export function AssertionsSection({ result }: { result: EvalResult }) {
  let assertions: AssertionResult[]
  try {
    assertions = JSON.parse(result.assertions_detail) as AssertionResult[]
  } catch {
    assertions = []
  }
  return (
    <section className={styles.asideSection}>
      <h2 className="eyebrow">
        Assertions · {result.assertions_passed} of {result.assertions_total}
      </h2>
      {assertions.map((assertion, i) => (
        <div key={i} className={styles.assertion}>
          {assertion.passed ? <PassIcon /> : <FailIcon />}
          <div className={styles.assertionText}>
            <span className={styles.assertionType}>{assertion.type}</span>
            <span className={styles.assertionDetail}>{assertion.detail}</span>
          </div>
        </div>
      ))}
    </section>
  )
}

function PassIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="var(--fit)"
      strokeWidth="2.2"
      aria-label="passed"
      role="img"
      style={{ marginTop: 1 }}
    >
      <path d="M3 8.5l3 3 7-7" />
    </svg>
  )
}

function FailIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="var(--nofit)"
      strokeWidth="2.2"
      aria-label="failed"
      role="img"
      style={{ marginTop: 1 }}
    >
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  )
}

export function JudgeSection({ result }: { result: EvalResult }) {
  return (
    <section className={`${styles.asideSection} ${styles.bordered}`}>
      <h2 className="eyebrow">Judge</h2>
      {result.judge_score != null ? (
        <>
          <div className={styles.judgeScore}>
            <span className={styles.judgeScoreValue}>{result.judge_score.toFixed(2)}</span>
            <span className={styles.judgeScoreMax}>/ 1</span>
          </div>
          <p className={styles.judgeRationale}>{result.judge_rationale}</p>
        </>
      ) : (
        <p className={styles.judgeRationale}>No judge criteria</p>
      )}
    </section>
  )
}

export function VerdictForm({
  runId,
  result,
  onNextUnreviewed,
}: {
  runId: number
  result: EvalResult
  onNextUnreviewed: () => void
}) {
  const [verdict, setVerdict] = useState<VerdictChoice>(result.manual_verdict ?? 'clear')
  const [notes, setNotes] = useState(result.manual_notes ?? '')
  const updateResult = useUpdateEvalResult(runId)

  function handleSave() {
    updateResult.mutate({ resultId: result.id, update: verdictUpdatePayload(verdict, notes) })
  }

  const options: { value: VerdictChoice; label: string }[] = [
    { value: 'pass', label: 'Pass' },
    { value: 'fail', label: 'Fail' },
    { value: 'clear', label: 'Clear' },
  ]

  return (
    <form
      className={`${styles.verdictForm} ${styles.bordered}`}
      onSubmit={(e) => {
        e.preventDefault()
        handleSave()
      }}
    >
      <fieldset className={styles.fieldset}>
        <legend className={`eyebrow ${styles.legend}`}>Your verdict</legend>
        <div className={styles.verdictOptions}>
          {options.map((option) => (
            <label key={option.value} className={styles.verdictOption} data-selected={verdict === option.value}>
              <input type="radio" name="verdict" checked={verdict === option.value} onChange={() => setVerdict(option.value)} />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>
      <label htmlFor="verdict-notes" className="eyebrow">
        Notes
      </label>
      <textarea id="verdict-notes" className={styles.notes} value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className={styles.verdictActions}>
        <button type="submit" className="btn btn-solid" disabled={updateResult.isPending}>
          Save
        </button>
        <button type="button" className="btn" onClick={onNextUnreviewed}>
          Next unreviewed
        </button>
      </div>
      {updateResult.isError && <ErrorNotice error={updateResult.error} />}
    </form>
  )
}
