export function briefingLink() {
  return new URLSearchParams(window.location.search).get('mode') === 'sample' ? '/?mode=sample' : '/'
}

export default function SiteHeader({ page, now = Date.now() }: { page: 'briefing' | 'ranking'; now?: number }) {
  const home = briefingLink()
  const ranking = home.includes('?') ? '/ranking?mode=sample' : '/ranking'
  return <header className="site-header"><div className="header-inner">
    <a className="brand" href={home} aria-label="Court Side home">
      <svg width="35" height="35" viewBox="0 0 40 40" aria-hidden="true"><rect x="1" y="1" width="38" height="38" rx="6" fill="currentColor" /><g fill="none" stroke="#fffaf0" strokeWidth="1.4"><circle cx="20" cy="20" r="12" /><path d="M8 20h24M20 8v24M11 12c10 2 10 14 18 16M11 28c10-2 10-14 18-16" /></g></svg>
      <span>COURT SIDE<span className="brand-period">.</span></span>
    </a>
    <nav aria-label="Main navigation">
      <a href={page === 'briefing' ? '#briefing' : `${home}#briefing`} className={page === 'briefing' ? 'active' : undefined} aria-current={page === 'briefing' ? 'page' : undefined}>NBA briefing</a>
      <a href={ranking} className={page === 'ranking' ? 'active' : undefined} aria-current={page === 'ranking' ? 'page' : undefined}>How we rank</a>
    </nav>
    <span className="header-date">{new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(now)}</span>
  </div></header>
}
