import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { listCases, listTools } from '../../api/endpoints'
import { Button } from '../../components/Button'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import styles from './DatasetPage.module.css'
import { CaseEditor } from './CaseEditor'
import {
  caseBadges,
  caseToForm,
  emptyForm,
  firstUserMessage,
  matchesSearch,
  type CaseFormState,
} from './testCaseForm'

const NEW_CASE = 'new'

export default function DatasetPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [newCategoryDraft, setNewCategoryDraft] = useState('')
  const [form, setForm] = useState<CaseFormState | null>(null)
  // Which case (or NEW_CASE, or none) `form` was loaded for. Compared against the URL's
  // `case` param during render (see below) so a route change re-derives the draft, without
  // clobbering an in-progress edit or a just-duplicated draft on every re-render.
  const [loadedCaseKey, setLoadedCaseKey] = useState<string | null>(null)

  const casesQuery = useQuery({ queryKey: ['dataset', 'cases'], queryFn: () => listCases() })
  const toolsQuery = useQuery({ queryKey: ['dataset', 'tools'], queryFn: () => listTools() })
  const cases = useMemo(() => casesQuery.data ?? [], [casesQuery.data])
  const tools = toolsQuery.data ?? []

  const categories = useMemo(() => {
    const counts = new Map<string, number>()
    for (const c of cases) counts.set(c.category, (counts.get(c.category) ?? 0) + 1)
    return [...counts.entries()].map(([name, count]) => ({ name, count }))
  }, [cases])

  const selectedCategory = searchParams.get('category') ?? categories[0]?.name ?? ''
  const caseParam = searchParams.get('case')

  const casesInCategory = useMemo(
    () => cases.filter((c) => c.category === selectedCategory && matchesSearch(c, search)),
    [cases, selectedCategory, search],
  )

  // Adjust the draft during render when the URL's case param no longer matches what's
  // loaded (React's documented alternative to a sync-on-prop-change effect: calling
  // setState directly in the render body is safe here since it converges in one extra
  // render once loadedCaseKey catches up to caseParam).
  if (caseParam !== loadedCaseKey) {
    if (!caseParam) {
      setLoadedCaseKey(null)
      setForm(null)
    } else if (caseParam === NEW_CASE) {
      setLoadedCaseKey(NEW_CASE)
      setForm(emptyForm(selectedCategory))
    } else {
      const match = cases.find((c) => c.id === caseParam)
      if (match) {
        setLoadedCaseKey(caseParam)
        setForm(caseToForm(match))
      } // else: cases still loading -- retried next render once they arrive
    }
  }

  function updateParams(mutate: (params: URLSearchParams) => void) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      mutate(next)
      return next
    })
  }

  function selectCategory(name: string) {
    setSearch('')
    updateParams((params) => {
      params.set('category', name)
      params.delete('case')
    })
  }

  function openNewCase() {
    setLoadedCaseKey(null) // force a blank draft even if one is already open
    updateParams((params) => {
      params.set('category', selectedCategory)
      params.set('case', NEW_CASE)
    })
  }

  function openCase(id: string) {
    updateParams((params) => params.set('case', id))
  }

  function handleSaved(id: string, category: string) {
    setLoadedCaseKey(id)
    updateParams((params) => {
      params.set('category', category)
      params.set('case', id)
    })
  }

  function handleDuplicated(draft: CaseFormState) {
    setForm(draft)
    setLoadedCaseKey(NEW_CASE)
    updateParams((params) => params.set('case', NEW_CASE))
  }

  function handleDeleted() {
    setLoadedCaseKey(null)
    updateParams((params) => params.delete('case'))
  }

  const isEmptyDataset = casesQuery.isSuccess && cases.length === 0 && caseParam !== NEW_CASE

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <div className="eyebrow">data/test_cases/ · private · never committed</div>
          <h1 className={styles.title}>Your test cases</h1>
        </div>
        <Button variant="solid" onClick={openNewCase}>
          <PlusIcon /> New case
        </Button>
      </header>

      {casesQuery.isError && (
        <div style={{ padding: '16px 40px' }}>
          <ErrorNotice error={casesQuery.error} />
        </div>
      )}

      {isEmptyDataset ? (
        <div className={styles.editorEmpty}>
          No test cases yet. Start from <code>data/test_cases.template.json</code>, or click &ldquo;New case&rdquo;.
        </div>
      ) : (
        <div className={styles.body}>
          <nav aria-label="Categories" className={styles.nav}>
            <div className={['eyebrow', styles.navHeading].join(' ')}>Categories</div>
            {categories.map((cat) => (
              <button
                key={cat.name}
                type="button"
                className={[styles.category, cat.name === selectedCategory && styles.categoryActive]
                  .filter(Boolean)
                  .join(' ')}
                aria-current={cat.name === selectedCategory ? 'true' : undefined}
                onClick={() => selectCategory(cat.name)}
              >
                <span>{cat.name}</span>
                <span className={styles.categoryCount}>{cat.count}</span>
              </button>
            ))}
            <div className={styles.newCategory}>
              <label htmlFor="new-category" className="eyebrow">
                New category
              </label>
              <input
                id="new-category"
                className="field"
                placeholder="any name"
                value={newCategoryDraft}
                onChange={(e) => setNewCategoryDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== 'Enter') return
                  const name = newCategoryDraft.trim()
                  if (!name) return
                  selectCategory(name)
                  setNewCategoryDraft('')
                }}
              />
            </div>
          </nav>

          <section aria-label={`Cases in ${selectedCategory || 'category'}`} className={styles.list}>
            <div className={styles.search}>
              <label htmlFor="case-search" className="eyebrow">
                Search {selectedCategory}
              </label>
              <input
                id="case-search"
                className="field"
                placeholder="Prompt text, tag or assertion type"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className={styles.cases}>
              {casesInCategory.length === 0 && <p className={styles.empty}>No cases match.</p>}
              {casesInCategory.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={[styles.case, c.id === caseParam && styles.caseActive].filter(Boolean).join(' ')}
                  aria-current={c.id === caseParam ? 'true' : undefined}
                  onClick={() => openCase(c.id)}
                >
                  <span className={styles.caseTop}>
                    <span className={styles.caseId}>{c.id}</span>
                    <span className={styles.caseBadges}>
                      {caseBadges(c).map((badge) => (
                        <Chip key={badge} tone="idle">
                          {badge}
                        </Chip>
                      ))}
                    </span>
                  </span>
                  <span className={styles.casePrompt}>{firstUserMessage(c)}</span>
                </button>
              ))}
            </div>
          </section>

          {form ? (
            <CaseEditor
              key={caseParam}
              form={form}
              setForm={setForm}
              isNew={caseParam === NEW_CASE}
              tools={tools}
              onSaved={handleSaved}
              onDuplicated={handleDuplicated}
              onDeleted={handleDeleted}
            />
          ) : (
            <div className={styles.editorEmpty}>Select a case, or click &ldquo;New case&rdquo;.</div>
          )}
        </div>
      )}

      <datalist id="dataset-categories">
        {categories.map((cat) => (
          <option key={cat.name} value={cat.name} />
        ))}
      </datalist>
    </main>
  )
}

function PlusIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M8 3v10M3 8h10" />
    </svg>
  )
}
