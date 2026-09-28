export type SizeStock = { size: string; quantity: number }

export type Product = {
  product_id: string
  name: string
  garment_type: string
  description: string
  short_description: string
  colors: string[]
  image_url: string
  price: number
  inventory: SizeStock[]
}

export type ProductDetail = Product & {
  total_stock: number
}

export type ChatProduct = Pick<Product, 'product_id' | 'name' | 'price' | 'image_url'>

export type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  products?: ChatProduct[]
  agents_used?: string[]
}

export type User = {
  id: number
  first_name: string
  last_name: string
  email: string
}

// Turns FastAPI error bodies into one readable sentence.
function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) {
    const { msg, loc } = detail[0] as { msg: string; loc?: string[] }
    if (loc?.at(-1) === 'email') return 'Please enter a valid email address'
    return msg.replace(/^Value error, /, '')
  }
  return fallback
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(errorMessage(body, `${res.status} ${res.statusText}`))
  }
  return res.json()
}

const postJson = <T>(url: string, body: unknown) =>
  request<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export type SignupForm = {
  first_name: string
  last_name: string
  email: string
  password: string
  confirm_password: string
}

export const signup = (form: SignupForm) => postJson<User>('/api/auth/signup', form)

export const login = (email: string, password: string) =>
  postJson<User>('/api/auth/login', { email, password })

export const logout = () => postJson<{ ok: boolean }>('/api/auth/logout', {})

export const getMe = () => request<{ user: User | null }>('/api/auth/me')

// Spec limits, matching backend/limits.py.
export const MAX_QTY_PER_ITEM = 10
export const PAGE_SIZE = 20

export type ProductPage = {
  products: Product[]
  total_matches: number
  returned: number
  max_results: number
  page_size: number
  capped: boolean
  partial: boolean
}

export const getProductsByIds = (ids: string[]) =>
  request<ProductPage>(`/api/products?ids=${ids.map(encodeURIComponent).join(',')}`)

export const searchProducts = (query: string, sort: string, signal?: AbortSignal) =>
  request<ProductPage>(`/api/products?q=${encodeURIComponent(query)}&sort=${encodeURIComponent(sort)}`, {
    signal,
  })

export const getProduct = (id: string) =>
  request<ProductDetail>(`/api/products/${encodeURIComponent(id)}`)

// Only the most recent turns are sent as context, so long saved histories stay fast.
const CHAT_CONTEXT_TURNS = 20

// The server stops a reply after 3 minutes; the page gives up a few seconds later.
const CHAT_TIMEOUT_MS = 185_000

// Where the shopper is when they send a message. The server looks the product up itself.
export type PageInfo = { current_page: string; current_product_id: string | null }

export async function sendChat(messages: ChatMessage[], page: PageInfo) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS)
  try {
    return await request<{ reply: string; products: ChatProduct[]; agents_used: string[] }>('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: messages.slice(-CHAT_CONTEXT_TURNS).map(({ role, content }) => ({ role, content })),
        ...page,
      }),
      signal: controller.signal,
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw new Error('Sorry, that took too long. Please try again.')
    throw err
  } finally {
    clearTimeout(timer)
  }
}

// ---------- cart and orders (all prices and totals come from the server) ----------

export type CartLine = {
  product_id: string
  name: string
  size: string
  quantity: number
  in_stock: number
  unit_price: number
  line_total: number
  image_url: string
  problem: string | null
}

export type CartData = {
  items: CartLine[]
  item_count: number
  subtotal: number
  has_problems: boolean
}

export type OrderReceipt = {
  order_id: number
  items: { name: string; size: string; quantity: number; line_total: number }[]
  item_count: number
  subtotal: number
}

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  return request<T>(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

const itemUrl = (productId: string, size: string) =>
  `/api/cart/items/${encodeURIComponent(productId)}/${encodeURIComponent(size)}`

export const getCart = () => request<CartData>('/api/cart')
export const addCartItem = (product_id: string, size: string, quantity = 1) =>
  send<CartData>('/api/cart/items', 'POST', { product_id, size, quantity })
export const updateCartItem = (productId: string, size: string, quantity: number) =>
  send<CartData>(itemUrl(productId, size), 'PATCH', { quantity })
export const removeCartItem = (productId: string, size: string) =>
  send<CartData>(itemUrl(productId, size), 'DELETE')
export const emptyCart = () => send<CartData>('/api/cart', 'DELETE')
export const placeOrder = () => send<OrderReceipt>('/api/orders', 'POST')

// ---------- Yale Athletics scores ----------

export type Scoreboard = {
  results: {
    date: string
    sport: string
    opponent: string
    home: boolean
    outcome: 'W' | 'L' | 'T'
    yale_score: number
    opponent_score: number
  }[]
  upcoming: { date: string; time: string | null; sport: string; opponent: string; home: boolean }[]
  updated_at: string | null
  source: string
  available: boolean
}

export const getScores = () => request<Scoreboard>('/api/scores')

export const getChatHistory = () =>
  request<(ChatMessage & { created_at: string })[]>('/api/chat/history')

export const formatPrice = (price: number) => `$${price.toFixed(2)}`
