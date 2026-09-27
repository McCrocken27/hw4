// Ivy League mascots, built from HTML elements and CSS (no images).
// The Yale Bulldog wears a navy "Y" sweater and always comes out on top.

type Kind = 'bulldog' | 'tiger' | 'lion' | 'bear'

export function Critter({ kind, facing = 'right', dizzy = false }: { kind: Kind; facing?: 'left' | 'right'; dizzy?: boolean }) {
  return (
    <div className={`critter critter--${kind} critter--${facing}${dizzy ? ' critter--dizzy' : ''}`}>
      <div className="c-tail" />
      <div className="c-leg c-leg--back" />
      <div className="c-leg c-leg--front" />
      <div className="c-body">{kind === 'bulldog' && <span className="c-letter">Y</span>}</div>
      <div className="c-arm c-arm--back">
        <span className="c-paw" />
      </div>
      <div className="c-head">
        {kind === 'lion' && <div className="c-mane" />}
        <div className="c-ear c-ear--left" />
        <div className="c-ear c-ear--right" />
        <div className="c-face">
          <span className="c-brow c-brow--left" />
          <span className="c-brow c-brow--right" />
          <span className="c-eye c-eye--left" />
          <span className="c-eye c-eye--right" />
          <div className="c-muzzle">
            <span className="c-nose" />
            <span className="c-mouth" />
            {kind === 'bulldog' && <span className="c-teeth" />}
          </div>
        </div>
      </div>
      <div className="c-arm c-arm--front">
        <span className="c-paw" />
      </div>
      {dizzy && (
        <div className="c-stars">
          <span>★</span>
          <span>★</span>
          <span>★</span>
        </div>
      )}
    </div>
  )
}

const RIVALS: { kind: Exclude<Kind, 'bulldog'>; school: string; mascot: string; sound: string }[] = [
  { kind: 'tiger', school: 'Princeton', mascot: 'Tiger', sound: 'POW!' },
  { kind: 'lion', school: 'Columbia', mascot: 'Lion', sound: 'BOOLA!' },
  { kind: 'bear', school: 'Brown', mascot: 'Bear', sound: 'WHAM!' },
]

function Scuffle({ kind, school, mascot, sound, delay }: (typeof RIVALS)[number] & { delay: number }) {
  return (
    <figure className="scuffle" style={{ animationDelay: `${delay}s` }}>
      <div className="scuffle-stage">
        <Critter kind="bulldog" facing="right" />
        <div className="scuffle-cloud">
          <span className="puff" />
          <span className="puff" />
          <span className="puff" />
          <strong>{sound}</strong>
        </div>
        <Critter kind={kind} facing="left" dizzy />
      </div>
      <figcaption>
        <span className="scuffle-yale">Bulldog</span> vs {school} {mascot}
      </figcaption>
    </figure>
  )
}

export function RivalryRow() {
  return (
    <section className="rivalry" aria-label="Rivalry Row: cartoon Yale Bulldogs scuffling with Ivy League mascots">
      <div className="section-heading">
        <div>
          <p className="kicker">Rivalry Row</p>
          <h2>The Bulldogs Take On the Ivy League</h2>
        </div>
      </div>
      <div className="rivalry-grid">
        {RIVALS.map((r, i) => (
          <Scuffle key={r.kind} {...r} delay={i * 0.35} />
        ))}
      </div>
    </section>
  )
}

// A bulldog peeking in over the bottom of the shop window, on every page.
export function PeekingBulldog() {
  return (
    <div className="peeker" aria-hidden="true">
      <Critter kind="bulldog" facing="right" />
    </div>
  )
}
