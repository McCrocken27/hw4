import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatPrice, getProductsByIds, type Product } from '../api'
import { useAuth } from '../auth'
import { Critter, RivalryRow } from '../Mascots'
import ProductCard from '../ProductCard'
import ScoreTicker from '../ScoreTicker'

// Hand-picked product_ids from the catalogue for each home page section.
const STAFF_PICKS = [
  'basic-hoodie-big-yale',
  'district-vit-hoodie-vintage-sailor-bulldog',
  'brooks-brothers-bomber-jacket-yale',
  'yale-dad-crewneck',
]

const COLLEGE_GEAR = [
  'davenport-college-crewneck',
  'grace-hopper-college-crewneck',
  'jonathan-edwards-college-crewneck',
  'pierson-college-crewneck',
  'saybrook-college-crewneck',
  'timothy-dwight-college-crewneck',
]

const GAME_DAY = '2025-yale-vs-harvard-t-shirt'

export default function Home() {
  const { user } = useAuth()
  const [byId, setById] = useState<Map<string, Product>>(new Map())

  useEffect(() => {
    // Ask for just the products this page features (the API returns at most 50 per request).
    getProductsByIds([...STAFF_PICKS, GAME_DAY, ...COLLEGE_GEAR])
      .then((page) => setById(new Map(page.products.map((p) => [p.product_id, p]))))
      .catch(() => setById(new Map()))
  }, [])

  const pick = (ids: string[]) => ids.flatMap((id) => byId.get(id) ?? [])
  const gameDay = byId.get(GAME_DAY)

  return (
    <>
      <ScoreTicker />

      <section className="hero">
        <div className="hero-mascot hero-mascot--left" aria-hidden="true">
          <Critter kind="bulldog" facing="right" />
        </div>
        <div className="hero-mascot hero-mascot--right" aria-hidden="true">
          <Critter kind="bulldog" facing="left" />
        </div>
        {user && <p className="hero-greeting">Welcome back, {user.first_name}!</p>}
        <h1>Custom Official Yale Gear</h1>
        <p>Gear for all Yale Colleges</p>
        <div className="hero-actions">
          <Link to="/products" className="btn btn-light">
            Shop All Gear
          </Link>
          <Link to="/about" className="btn btn-outline">
            Our Story
          </Link>
        </div>
      </section>

      {byId.size > 0 && (
        <>
          <section className="home-section">
            <div className="section-heading">
              <h2>Staff Picks</h2>
              <Link to="/products">See all →</Link>
            </div>
            <div className="product-grid">
              {pick(STAFF_PICKS).map((p) => (
                <ProductCard key={p.product_id} product={p} />
              ))}
            </div>
          </section>

          {gameDay && (
            <section className="game-day">
              <img src={gameDay.image_url} alt={gameDay.name} />
              <div>
                <p className="game-day-kicker">The Game</p>
                <h2>Get ready to BEAT Harvard</h2>
                <p>{gameDay.description}</p>
                <Link to={`/products/${gameDay.product_id}`} className="btn btn-light">
                  Shop the {gameDay.name} · {formatPrice(gameDay.price)}
                </Link>
              </div>
            </section>
          )}

          <section className="home-section">
            <div className="section-heading">
              <h2>Rep Your College</h2>
              <Link to="/products">See all →</Link>
            </div>
            <div className="product-grid">
              {pick(COLLEGE_GEAR).map((p) => (
                <ProductCard key={p.product_id} product={p} />
              ))}
            </div>
          </section>
        </>
      )}

      <RivalryRow />
    </>
  )
}
