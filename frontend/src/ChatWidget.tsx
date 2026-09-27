import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { formatPrice, getChatHistory, sendChat, type ChatMessage } from './api'
import { useAuth } from './auth'

const GREETING: ChatMessage = {
  role: 'assistant',
  content: "Boola Boola! I'm the Campus Customs assistant. Ask me about products, sizes or stock.",
}

// Shows **text** in bold. Builds React elements (never raw HTML), so a reply can't inject code.
function withBold(text: string) {
  return text
    .split(/(\*\*[^*\n]+\*\*)/g)
    .map((part, i) =>
      part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
        <strong key={i}>{part.slice(2, -2)}</strong>
      ) : (
        part.replace(/^- /gm, '• ')
      ),
    )
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const { user } = useAuth()

  // Logged-in shoppers see their saved chat; logging out clears it from the screen.
  useEffect(() => {
    if (!user) {
      setMessages([GREETING])
      return
    }
    let cancelled = false
    getChatHistory()
      .then((saved) => {
        if (!cancelled) setMessages([GREETING, ...saved])
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [user?.id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, thinking, open])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || thinking) return

    // The greeting is UI only, so it is not sent to the model.
    const history = [...messages, { role: 'user', content: text } as ChatMessage]
    setMessages(history)
    setInput('')
    setThinking(true)
    try {
      const { reply, products, agents_used } = await sendChat(history.slice(1))
      setMessages((m) => [...m, { role: 'assistant', content: reply, products, agents_used }])
    } catch (err) {
      const reason = (err as Error).message
      const content = /^\d{3} |fetch/i.test(reason)
        ? 'Sorry, I could not reach the store. Please try again.'
        : reason
      setMessages((m) => [...m, { role: 'assistant', content }])
    } finally {
      setThinking(false)
    }
  }

  return (
    <div className="chat">
      {open && (
        <section className="chat-panel" aria-label="Chat with Campus Customs">
          <header>
            <span>Campus Customs Chat</span>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close chat">
              ×
            </button>
          </header>
          <p className="chat-note">
            {user ? 'Your chat is saved to your account.' : 'Log in to save your chat.'}
          </p>
          <div className="chat-messages">
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg ${m.role}`}>
                <p>{m.role === 'assistant' ? withBold(m.content) : m.content}</p>
                {m.products?.map((p) => (
                  <Link key={p.product_id} to={`/products/${p.product_id}`} className="chat-product">
                    <img src={p.image_url} alt="" />
                    <span>
                      {p.name}
                      <small>{formatPrice(p.price)}</small>
                    </span>
                  </Link>
                ))}
                {m.agents_used && m.agents_used.length > 1 && (
                  <small className="chat-agents">With help from {m.agents_used.slice(1).join(' and ')}</small>
                )}
              </div>
            ))}
            {thinking && <div className="chat-msg assistant thinking">Thinking…</div>}
            <div ref={bottomRef} />
          </div>
          <form onSubmit={handleSubmit}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about gear…"
              maxLength={2000}
              autoFocus
            />
            <button type="submit" disabled={!input.trim() || thinking}>
              Send
            </button>
          </form>
        </section>
      )}
      <button
        type="button"
        className="chat-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close chat' : 'Open chat'}
      >
        {open ? '×' : 'Chat'}
      </button>
    </div>
  )
}
