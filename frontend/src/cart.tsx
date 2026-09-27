import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import * as api from './api'
import { useAuth } from './auth'

type Notice = { kind: 'added'; name: string; size: string; image_url: string } | { kind: 'error'; message: string }

type CartState = {
  items: api.CartLine[]
  count: number
  subtotal: number
  hasProblems: boolean
  add: (product: api.Product, size: string) => Promise<boolean>
  setQuantity: (productId: string, size: string, quantity: number) => Promise<void>
  remove: (productId: string, size: string) => Promise<void>
  clear: () => Promise<void>
  order: () => Promise<api.OrderReceipt>
  notice: Notice | null
}

const EMPTY: api.CartData = { items: [], item_count: 0, subtotal: 0, has_problems: false }
const CartContext = createContext<CartState | null>(null)

// The cart lives on the server: guests by a cart cookie, logged-in shoppers on their
// account. The server checks stock on every change and works out every price and total.
export function CartProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [cart, setCart] = useState<api.CartData>(EMPTY)
  const [notice, setNotice] = useState<Notice | null>(null)

  const refresh = useCallback(() => {
    api.getCart().then(setCart).catch(() => setCart(EMPTY))
  }, [])

  // Reload when someone logs in or out; logging in moves a guest cart onto the account.
  useEffect(refresh, [user?.id, refresh])

  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), notice.kind === 'error' ? 4000 : 2500)
    return () => clearTimeout(timer)
  }, [notice])

  // Runs a cart change; if the server rejects it (e.g. not enough stock), shows why.
  async function change(action: () => Promise<api.CartData>): Promise<boolean> {
    try {
      setCart(await action())
      return true
    } catch (err) {
      setNotice({ kind: 'error', message: (err as Error).message })
      refresh()
      return false
    }
  }

  const value: CartState = {
    items: cart.items,
    count: cart.item_count,
    subtotal: cart.subtotal,
    hasProblems: cart.has_problems,
    add: async (product, size) => {
      const ok = await change(() => api.addCartItem(product.product_id, size))
      if (ok) setNotice({ kind: 'added', name: product.name, size, image_url: product.image_url })
      return ok
    },
    setQuantity: async (productId, size, quantity) => {
      await change(() => api.updateCartItem(productId, size, quantity))
    },
    remove: async (productId, size) => {
      await change(() => api.removeCartItem(productId, size))
    },
    clear: async () => {
      await change(api.emptyCart)
    },
    order: async () => {
      try {
        const receipt = await api.placeOrder()
        setCart(EMPTY)
        return receipt
      } finally {
        refresh()
      }
    },
    notice,
  }

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used inside CartProvider')
  return ctx
}
