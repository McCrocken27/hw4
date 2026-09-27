// The shop you see through the front window: back wall, lights, shelves and a clothing
// rack, drawn with HTML and CSS. A glass layer on top adds reflections and the window
// frame. Purely decorative, so it's hidden from screen readers.

const RACK = ['navy', 'white', 'gray', 'sky', 'navy', 'cream', 'white', 'navy']
const SHELF_STACKS = [
  ['navy', 'navy', 'white'],
  ['gray', 'gray', 'gray'],
  ['white', 'sky', 'white'],
  ['navy', 'cream', 'navy'],
]

function Shelves({ side }: { side: 'left' | 'right' }) {
  return (
    <div className={`store-shelves store-shelves--${side}`}>
      {[0, 1, 2].map((row) => (
        <div key={row} className="store-shelf">
          {SHELF_STACKS.map((stack, i) => (
            <div key={i} className="store-stack">
              {stack.map((color, j) => (
                <span key={j} className={`fold fold--${color}`} />
              ))}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export function StoreBackdrop() {
  return (
    <>
      <div className="store-scene" aria-hidden="true">
        <div className="store-wall" />
        <div className="store-sign">
          <span>Campus Customs</span>
          <small>Est. 1975</small>
        </div>
        <div className="store-lights">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className="store-lamp" />
          ))}
        </div>
        <Shelves side="left" />
        <div className="store-rack">
          <div className="store-rail" />
          {RACK.map((color, i) => (
            <div key={i} className={`hanging hanging--${color}`}>
              <span className="hanger" />
              <span className="garment" />
            </div>
          ))}
        </div>
        <Shelves side="right" />
        <div className="store-floor" />
      </div>
      <div className="store-glass" aria-hidden="true" />
    </>
  )
}

// Striped shop awning: alternating blue and white flaps with rounded bottoms.
export function Awning() {
  return (
    <div className="awning" aria-hidden="true">
      {Array.from({ length: 60 }, (_, i) => (
        <span key={i} className={i % 2 ? 'flap flap--white' : 'flap'} />
      ))}
    </div>
  )
}
