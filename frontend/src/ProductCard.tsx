import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatPrice, MAX_QTY_PER_ITEM, type Product } from './api'
import { useCart } from './cart'

const LOW_STOCK = 10

export default function ProductCard({ product: p }: { product: Product }) {
  const { add, items } = useCart()
  const [added, setAdded] = useState<string | null>(null)
  const url = `/products/${p.product_id}`
  const soldOut = p.inventory.every((s) => s.quantity <= 0)
  // Quantities come straight from the inventory table in campus_customs.db.
  const totalStock = p.inventory.reduce((sum, s) => sum + Math.max(s.quantity, 0), 0)
  const stockLabel = soldOut ? 'Sold out' : totalStock <= LOW_STOCK ? `Only ${totalStock} left` : `${totalStock} in stock`
  const stockLevel = soldOut ? 'out' : totalStock <= LOW_STOCK ? 'low' : 'ok'

  useEffect(() => {
    if (!added) return
    const timer = setTimeout(() => setAdded(null), 1500)
    return () => clearTimeout(timer)
  }, [added])

  const inCart = (size: string) =>
    items.find((i) => i.product_id === p.product_id && i.size === size)?.quantity ?? 0

  return (
    <div className="product-card">
      <div className="product-card-media">
        <Link to={url} tabIndex={-1} aria-hidden="true">
          <img src={p.image_url} alt="" loading="lazy" />
        </Link>

        {/* Slides up on hover (or keyboard focus): pick a size to add it to the cart. */}
        <div className="quick-add" role="group" aria-label={`Add ${p.name} to cart`}>
          {added ? (
            <p className="quick-add-done">Added size {added} ✓</p>
          ) : soldOut ? (
            <p className="quick-add-label">Out of stock</p>
          ) : (
            <>
              <p className="quick-add-label">Add to cart · pick a size</p>
              <div className="quick-add-sizes">
                {p.inventory.map((s) => {
                  const full = s.quantity <= 0 || inCart(s.size) >= Math.min(s.quantity, MAX_QTY_PER_ITEM)
                  return (
                    <button
                      key={s.size}
                      type="button"
                      disabled={full}
                      title={s.quantity <= 0 ? `${s.size} is out of stock` : `Add ${s.size} to cart (${s.quantity} in stock)`}
                      onClick={async () => {
                        if (await add(p, s.size)) setAdded(s.size)
                      }}
                    >
                      {s.size}
                      <small>{s.quantity <= 0 ? 'out' : `${s.quantity} left`}</small>
                    </button>
                  )
                })}
              </div>
            </>
          )}
        </div>
      </div>

      <Link to={url} className="product-card-body">
        <h2>{p.name}</h2>
        <p>{p.short_description}</p>
        <div className="card-foot">
          <span className="price">{formatPrice(p.price)}</span>
          <span className={`stock-badge stock-badge--${stockLevel}`}>{stockLabel}</span>
        </div>
      </Link>
    </div>
  )
}
