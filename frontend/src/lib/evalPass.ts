import type { EvalResult } from '../api/types'

// Mirrors the backend's pass rule for GET /evals/report: a manual verdict wins;
// otherwise no error, every assertion passed, and a judge score (if any) of at least 0.5.
export function resultPassed(
  result: Pick<EvalResult, 'manual_verdict' | 'error' | 'assertions_passed' | 'assertions_total' | 'judge_score'>,
): boolean {
  if (result.manual_verdict === 'pass') return true
  if (result.manual_verdict === 'fail') return false
  return (
    result.error == null &&
    result.assertions_passed === result.assertions_total &&
    (result.judge_score == null || result.judge_score >= 0.5)
  )
}
