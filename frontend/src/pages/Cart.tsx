import { useState } from 'react'
import { Link } from 'react-router-dom'
import { formatPrice, MAX_QTY_PER_ITEM, type OrderReceipt } from '../api'
import { useAuth } from '../auth'
import { useCart } from '../cart'

export default function Cart() {
  const { items, count, subtotal, hasProblems, setQuantity, remove, clear, order } = useCart()
  const { user } = useAuth()
  const [placing, setPlacing] = useState(false)
  const [orderError, setOrderError] = useState('')
  const [receipt, setReceipt] = useState<OrderReceipt | null>(null)

  async function handleOrder() {
    setPlacing(true)
    setOrderError('')
    try {
      setReceipt(await order())
    } catch (err) {
      setOrderError((err as Error).message)
    } finally {
      setPlacing(false)
    }
  }

  if (receipt) {
    return (
      <section className="cart-empty">
        <h1>Order placed!</h1>
        <p>
          Order #{receipt.order_id}: {receipt.item_count} {receipt.item_count === 1 ? 'item' : 'items'},{' '}
          <strong>{formatPrice(receipt.subtotal)}</strong>
        </p>
        <ul className="receipt">
          {receipt.items.map((i) => (
            <li key={`${i.name}-${i.size}`}>
              {i.quantity} × {i.name} (size {i.size}) · {formatPrice(i.line_total)}
            </li>
          ))}
        </ul>
        <Link to="/products" className="btn btn-solid">
          Keep Shopping
        </Link>
      </section>
    )
  }

  if (items.length === 0) {
    return (
      <section className="cart-empty">
        <h1>Your Cart</h1>
        <p>Your cart is empty.</p>
        <Link to="/products" className="btn btn-solid">
          Shop Products
        </Link>
      </section>
    )
  }

  return (
    <section className="cart">
      <h1>Your Cart</h1>
      <div className="cart-layout">
        <ul className="cart-items">
          {items.map((item) => (
            <li key={`${item.product_id}-${item.size}`} className="cart-item">
              <Link to={`/products/${item.product_id}`}>
                <img src={item.image_url} alt="" />
              </Link>
              <div className="cart-item-info">
                <Link to={`/products/${item.product_id}`} className="cart-item-name">
                  {item.name}
                </Link>
                <p className="muted">
                  Size {item.size} · {formatPrice(item.unit_price)} each
                </p>
                {item.problem && <p className="cart-problem">{item.problem}. Lower the quantity to order.</p>}
                <div className="qty">
                  <button
                    type="button"
                    onClick={() => setQuantity(item.product_id, item.size, item.quantity - 1)}
                    aria-label="One fewer"
                  >
                    −
                  </button>
                  <span aria-live="polite">{item.quantity}</span>
                  <button
                    type="button"
                    onClick={() => setQuantity(item.product_id, item.size, item.quantity + 1)}
                    disabled={item.quantity >= Math.min(item.in_stock, MAX_QTY_PER_ITEM)}
                    aria-label="One more"
                  >
                    +
                  </button>
                  {item.quantity >= MAX_QTY_PER_ITEM ? (
                    <small className="muted">Limit {MAX_QTY_PER_ITEM} per item</small>
                  ) : (
                    item.quantity >= item.in_stock &&
                    item.in_stock > 0 && <small className="muted">Only {item.in_stock} in stock</small>
                  )}
                </div>
              </div>
              <div className="cart-item-side">
                <strong>{formatPrice(item.line_total)}</strong>
                <button type="button" className="link-button" onClick={() => remove(item.product_id, item.size)}>
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>

        <aside className="cart-summary">
          <h2>Summary</h2>
          <p>
            <span>
              {count} {count === 1 ? 'item' : 'items'}
            </span>
            <strong>{formatPrice(subtotal)}</strong>
          </p>
          {user ? (
            <button
              type="button"
              className="btn btn-solid"
              onClick={handleOrder}
              disabled={placing || hasProblems}
            >
              {placing ? 'Placing order…' : 'Place Order'}
            </button>
          ) : (
            <Link to="/login" className="btn btn-solid">
              Log in to order
            </Link>
          )}
          {hasProblems && <p className="cart-problem">Some items don't have enough stock. Fix them to order.</p>}
          {orderError && (
            <p className="form-error" role="alert">
              {orderError}
            </p>
          )}
          <p className="muted small">No payment is taken yet. Placing an order reserves the items.</p>
          <button type="button" className="link-button" onClick={clear}>
            Empty cart
          </button>
        </aside>
      </div>
    </section>
  )
}
