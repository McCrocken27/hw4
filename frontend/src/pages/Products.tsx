import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PAGE_SIZE, searchProducts, type ProductPage } from '../api'
import ProductCard from '../ProductCard'

const DEBOUNCE_MS = 150

const SORTS = {
  relevance: 'Best match',
  'price-desc': 'Price: high to low',
  'price-asc': 'Price: low to high',
  'name-asc': 'Name: A to Z',
  'name-desc': 'Name: Z to A',
} as const
type SortKey = keyof typeof SORTS

export default function Products() {
  // The search, sort and page live in the URL (?q=navy&sort=price-desc&page=2), so
  // back/forward and shared links keep them.
  const [params, setParams] = useSearchParams()
  const sortParam = params.get('sort') ?? 'relevance'
  const sort: SortKey = sortParam in SORTS ? (sortParam as SortKey) : 'relevance'
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [result, setResult] = useState<ProductPage | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  // Keep the box in sync if the URL changes (e.g. the back button).
  useEffect(() => {
    setQuery(params.get('q') ?? '')
  }, [params])

  // Search the catalogue as the shopper types. Waits a moment between keystrokes and
  // cancels the previous request, so results always match the latest text. The server
  // sorts before applying its 50-product cap, so sorting is right across every match.
  useEffect(() => {
    const controller = new AbortController()
    setSearching(true)
    const timer = setTimeout(() => {
      searchProducts(query.trim(), sort, controller.signal)
        .then((page) => {
          setResult(page)
          setError('')
        })
        .catch((err) => {
          if (err.name !== 'AbortError') setError('Could not load products. Is the backend running?')
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false)
        })
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, sort])

  function updateParams(changes: Record<string, string>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
  }

  function handleChange(value: string) {
    setQuery(value)
    // A new search starts back on page 1.
    updateParams({ q: value.trim() ? value : '', page: '' })
  }

  const trimmed = query.trim()
  const products = result?.products ?? []
  const pageCount = Math.max(1, Math.ceil(products.length / PAGE_SIZE))
  const page = Math.min(Math.max(Number(params.get('page')) || 1, 1), pageCount)
  const shown = products.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const first = (page - 1) * PAGE_SIZE + 1
  const last = first + shown.length - 1

  function goToPage(n: number) {
    updateParams({ page: n > 1 ? String(n) : '' })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <>
      <div className="products-header">
        <h1>Products</h1>
        <div className="search-bar" role="search">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <line x1="16.5" y1="16.5" x2="21" y2="21" />
          </svg>
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(e) => handleChange(e.target.value)}
            placeholder="Search hoodies, colleges, colors…"
            aria-label="Search products"
            maxLength={100}
            autoFocus
          />
          {query && (
            <button
              type="button"
              className="search-clear"
              onClick={() => {
                handleChange('')
                inputRef.current?.focus()
              }}
              aria-label="Clear search"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {!result && !error && <p className="muted">Loading products…</p>}

      {result && (
        <div className="results-bar">
          <p className="result-count" aria-live="polite">
            {trimmed
              ? `${result.total_matches} ${result.total_matches === 1 ? 'product matches' : 'products match'} “${trimmed}”`
              : `${result.total_matches} products`}
            {products.length > 0 && ` · showing ${first}–${last}`}
            {searching && <span className="searching"> · searching…</span>}
          </p>
          <label className="sort-select">
            Sort by
            <select
              value={sort}
              onChange={(e) => updateParams({ sort: e.target.value === 'relevance' ? '' : e.target.value, page: '' })}
            >
              {Object.entries(SORTS).map(([key, label]) => (
                <option key={key} value={key}>
                  {key === 'relevance' && !trimmed ? 'Featured' : label}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {result?.capped && (
        <p className="cap-note">
          Showing the first {result.returned} of {result.total_matches} results. Search for a type, college or color to
          narrow it down.
        </p>
      )}

      {result && products.length === 0 && (
        <div className="no-results">
          <p>No products match “{trimmed}”.</p>
          <p className="muted">Try fewer words, or search for a type like “hoodie” or a college like “Saybrook”.</p>
        </div>
      )}

      <div className={`product-grid${searching ? ' is-searching' : ''}`}>
        {shown.map((p) => (
          <ProductCard key={p.product_id} product={p} />
        ))}
      </div>

      {pageCount > 1 && (
        <nav className="pager" aria-label="Pages">
          <button type="button" onClick={() => goToPage(page - 1)} disabled={page === 1}>
            ← Prev
          </button>
          {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
            <button
              key={n}
              type="button"
              className={n === page ? 'is-current' : ''}
              aria-current={n === page ? 'page' : undefined}
              onClick={() => goToPage(n)}
            >
              {n}
            </button>
          ))}
          <button type="button" onClick={() => goToPage(page + 1)} disabled={page === pageCount}>
            Next →
          </button>
        </nav>
      )}
    </>
  )
}
