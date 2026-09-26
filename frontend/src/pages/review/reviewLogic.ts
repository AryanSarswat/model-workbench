// Pure logic for the review screen: filtering/counting the case list, picking the next
// unreviewed case, and building the PATCH body for a verdict save. Kept separate from
// the page so the rules can be unit tested without rendering anything.
import { resultPassed } from '../../lib/evalPass'
import type { EvalResult, ManualVerdict, TestCase } from '../../api/types'

export type CaseFilter = 'all' | 'failed' | 'unreviewed'

export function filterResults(results: EvalResult[], filter: CaseFilter): EvalResult[] {
  if (filter === 'failed') return results.filter((result) => !resultPassed(result))
  if (filter === 'unreviewed') return results.filter((result) => result.manual_verdict == null)
  return results
}

export interface ResultCounts {
  total: number
  passed: number
  failed: number
  unreviewed: number
}

export function countByStatus(results: EvalResult[]): ResultCounts {
  let passed = 0
  let unreviewed = 0
  for (const result of results) {
    if (resultPassed(result)) passed++
    if (result.manual_verdict == null) unreviewed++
  }
  return { total: results.length, passed, failed: results.length - passed, unreviewed }
}

// The case_id of the next unreviewed result after `afterCaseId`, wrapping around the
// full result list (independent of any active filter). Null if none are unreviewed.
export function nextUnreviewedCaseId(results: EvalResult[], afterCaseId: string | null): string | null {
  const startIndex = afterCaseId == null ? -1 : results.findIndex((result) => result.case_id === afterCaseId)
  for (let offset = 1; offset <= results.length; offset++) {
    const candidate = results[(startIndex + offset) % results.length]
    if (candidate.manual_verdict == null) return candidate.case_id
  }
  return null
}

export type VerdictChoice = ManualVerdict | 'clear'

export function verdictUpdatePayload(verdict: VerdictChoice, notes: string) {
  const trimmed = notes.trim()
  return {
    manual_verdict: verdict === 'clear' ? null : verdict,
    manual_notes: trimmed === '' ? null : trimmed,
  }
}

export function lastUserMessage(testCase: TestCase): string | null {
  const userMessages = testCase.messages.filter((message) => message.role === 'user')
  return userMessages.length > 0 ? userMessages[userMessages.length - 1].content : null
}
