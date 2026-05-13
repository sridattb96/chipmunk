import './LandingPage.css';

const AUTH_URL = `${import.meta.env.VITE_API_URL || ''}/auth/google`;

const TAPE_ITEMS = [
  '★ NEW: SEMANTIC THREADING IS LIVE',
  '★ FREE FOR TEAMS UNDER 5',
  '★ VISUALIZE YOUR MEETING CONTEXT',
];

const STATS = [
  { label: 'MEETINGS_INDEXED',  num: '2.4M'  },
  { label: 'HOURS_TRANSCRIBED', num: '8,200' },
  { label: 'THREADS_LINKED',    num: '410K'  },
  { label: 'LANGUAGES',         num: '40+'   },
];

const THREAD_STEPS = [
  { date: 'MAR 04', title: 'Initial pricing brainstorm',      tag: 'EXPLORE',  active: false },
  { date: 'MAR 18', title: 'Competitor benchmark review',     tag: 'RESEARCH', active: false },
  { date: 'APR 02', title: 'Three tiers proposed by finance', tag: 'PROPOSE',  active: false },
  { date: 'APR 21', title: 'Tier 2 cut, usage-based added',   tag: 'PIVOT',    active: false },
  { date: 'MAY 09', title: 'Final pricing locked, GTM brief', tag: 'DECIDED',  active: true  },
];

export function LandingPage() {
  return (
    <div className="lp">
      {/* Scrolling tape */}
      <div className="lp-tape">
        <div className="lp-tape-track">
          {[...TAPE_ITEMS, ...TAPE_ITEMS].map((item, i) => (
            <span key={i}>{item}</span>
          ))}
        </div>
      </div>

      {/* Nav */}
      <nav className="lp-nav">
        <div className="lp-logo">THREADFORM<span>.</span></div>
        <div className="lp-nav-links">
          <a href="#how">HOW IT WORKS</a>
          <a href="#thread">PRODUCT</a>
          <a href={AUTH_URL} className="lp-nav-cta">SIGN IN →</a>
        </div>
      </nav>

      {/* Hero */}
      <section className="lp-hero" id="product">
        <div className="lp-hero-grid">
          <div>
            <div className="lp-hero-eyebrow">FILE: 001 / MEETINGS / THREADS</div>
            <h1>
              CONNECT<br />YOUR <span className="lp-accent-word">CONVERSATIONS</span>.
            </h1>
            <p className="lp-hero-sub">
              Threadform records every meeting, transcribes it word-for-word, and stitches them into living threads — so you can follow the context every step of the way.
            </p>
            <div className="lp-hero-cta-row">
              <a href={AUTH_URL} className="lp-hero-cta lp-primary">RECORD NOW →</a>
            </div>
          </div>
        </div>
      </section>


{/* How it works */}
      <section className="lp-how" id="how">
        <div className="lp-section-label">// HOW IT WORKS</div>
<div className="lp-steps">
          <div className="lp-step">
            <div className="lp-step-num">STEP 01</div>
            <div className="lp-step-icon">●</div>
            <h3>Record</h3>
            <p>Hit record to capture your conversation.</p>
          </div>
          <div className="lp-step">
            <div className="lp-step-num">STEP 02</div>
            <div className="lp-step-icon">≣</div>
            <h3>Transcribe</h3>
            <p>Threadform generates a meeting summary, complete with topic extraction and a downloadable transcript.</p>
          </div>
          <div className="lp-step">
            <div className="lp-step-num">STEP 03</div>
            <div className="lp-step-icon">∿</div>
            <h3>Thread</h3>
            <p>Semantic analysis links the meeting to its predecessors. The full evolution of any decision, in one view.</p>
          </div>
        </div>
      </section>

      {/* Thread example */}
      <section className="lp-thread-section" id="thread">
        <div className="lp-section-label">// EXAMPLE THREAD</div>
        <div className="lp-thread-heading">
          DEAL THREAD / 3 MEETINGS
        </div>
        <div className="lp-thread-nodes">
          <div className="lp-node lp-node-latest">
            <div className="lp-node-step">Call 03</div>
            <div className="lp-node-title">Closing<br />the deal</div>
          </div>
          <div className="lp-connector">
            <div className="lp-connector-arrow">↑</div>
          </div>
          <div className="lp-node">
            <div className="lp-node-step">Call 02</div>
            <div className="lp-node-title">Negotiating<br />the contract</div>
          </div>
          <div className="lp-connector">
            <div className="lp-connector-arrow">↑</div>
          </div>
          <div className="lp-node">
            <div className="lp-node-step">Call 01</div>
            <div className="lp-node-title">Call with<br />prospect</div>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="lp-final-cta" id="pricing">
        <div className="lp-final-cta-h2">
          VISUALIZE THE CONTEXT<br />ACROSS YOUR CALLS.
        </div>
        <a href={AUTH_URL} className="lp-final-btn">RECORD NOW →</a>
      </section>

      {/* Footer */}
      <footer className="lp-footer">
        <span>THREADFORM © 2026 // BUILT IN NEW YORK</span>
        <span>STATUS: OPERATIONAL · v3.4.1</span>
      </footer>
    </div>
  );
}
