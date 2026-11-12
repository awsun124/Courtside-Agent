import SiteHeader, { briefingLink } from './SiteHeader'

export default function RankingPage() {
  return <div id="top">
    <title>How we rank | Court Side</title>
    <a className="skip-link" href="#ranking-process">Skip to ranking process</a>
    <SiteHeader page="ranking" />
    <main className="page-shell ranking-page" id="ranking-process">
      <section className="page-intro" aria-labelledby="page-title">
        <div>
          <p className="eyebrow intro-kicker"><span className="small-rule" /> THE METHOD</p>
          <h1 id="page-title">How we rank<span>.</span></h1>
          <p className="intro-copy">A look at the reporting behind the order.<br />Court Side ranks the most-covered stories among the sources we monitor.</p>
        </div>
      </section>

      <section className="ranking-section" aria-labelledby="before-scoring">
        <p className="eyebrow">BEFORE THE SCORE</p>
        <h2 id="before-scoring">Find the event. Check the coverage.</h2>
        <ol className="ranking-steps">
          <li><strong>Collect recent NBA reports.</strong><p>We use the selected one-, three-, or seven-day window. Source limits and delays mean we may only retrieve part of the coverage.</p></li>
          <li><strong>Group articles about the same event.</strong><p>Sharing a player or team name is not enough. We compare the event, people, dates, and details such as teams, scores, or injury location. Ambiguous articles stay in review.</p></li>
          <li><strong>Combine likely copies.</strong><p>Repeated coverage from one publisher and likely syndicated copies count together as one reporting group. Every original link stays available.</p></li>
        </ol>
        <p className="ranking-note">Reporting groups are estimates. We have not fully verified publisher ownership or original authorship.</p>
      </section>

      <section className="ranking-section" aria-labelledby="weighted-score">
        <p className="eyebrow">THE SCORE / 100</p>
        <h2 id="weighted-score">Three measures, one transparent score.</h2>
        <p>These are the default settings. Settings can be changed, and each saved story’s “Why this ranks” panel shows the weights and values used for that briefing.</p>
        <div className="ranking-components">
          <section><span className="ranking-weight">50<span>%</span></span><h3>Coverage</h3>
            <p>How many estimated independent reporting groups cover the event. Eight groups earn all 50 coverage points. Two earn 12.5 points.</p>
            <code>min(groups / 8, 1) × 50</code>
          </section>
          <section><span className="ranking-weight">30<span>%</span></span><h3>Momentum</h3>
            <p>How quickly new reporting groups are joining. We compare groups per hour in the latest 24 hours of available coverage with the earlier part of the window.</p>
            <p>Faster growth earns more points. Sparse coverage reduces them. Equal or falling rates earn zero.</p>
          </section>
          <section><span className="ranking-weight">20<span>%</span></span><h3>Freshness</h3>
            <p>The age of the latest reviewed substantive development, backed by source links. It earns half the available points after 24 hours.</p>
            <p>No reviewed development means zero freshness points. A newly published copy does not make an old event fresh.</p>
            <code>2 ^ (−age in hours / 24) × 20</code>
          </section>
        </div>
        <details className="ranking-formula"><summary>The momentum calculation</summary>
          <div><p>Each reporting group enters the calculation at its earliest publication time.</p>
            <code>recent rate = recent groups / recent hours</code>
            <code>earlier rate = earlier groups / earlier hours</code>
            <code>growth = max(0, (recent rate − earlier rate) / (recent rate + earlier rate))</code>
            <code>momentum points = growth × min(total groups / 3, 1) × 30</code>
            <p>If both rates are zero, growth is zero. If only the earlier rate is zero, growth is one before the sparse-coverage adjustment. Fewer than 24 earlier hours means zero momentum points.</p>
          </div>
        </details>
      </section>

      <section className="ranking-section" aria-labelledby="example-score">
        <p className="eyebrow">AN ILLUSTRATION / NOT LIVE NEWS</p>
        <h2 id="example-score">What a score of 35 can mean.</h2>
        <div className="ranking-example"><table><caption>Example using the default settings and a sufficient earlier comparison period</caption>
          <thead><tr><th scope="col">Measure</th><th scope="col">Evidence</th><th scope="col">Points</th></tr></thead>
          <tbody><tr><th scope="row">Coverage</th><td>Four reporting groups</td><td>25 / 50</td></tr>
            <tr><th scope="row">Momentum</th><td>Equal recent and earlier rates</td><td>0 / 30</td></tr>
            <tr><th scope="row">Freshness</th><td>A reviewed development 24 hours old</td><td>10 / 20</td></tr></tbody>
          <tfoot><tr><th scope="row" colSpan={2}>Total score</th><td>35 / 100</td></tr></tfoot>
        </table></div>
        <p>A score measures the downloaded coverage. It is not a probability that a claim is true or a judgment of how important the event is.</p>
      </section>

      <section className="ranking-section" aria-labelledby="selection-rules">
        <p className="eyebrow">MAKING THE BRIEFING</p>
        <h2 id="selection-rules">Up to ten, when the evidence supports it.</h2>
        <p>A story needs at least two estimated independent reporting groups under the default settings. We sort eligible stories by total score, then coverage, with a stable identifier breaking remaining ties.</p>
        <p>We show fewer than ten when coverage is thin. Candidates below the minimum can appear under “On our radar,” with an explanation of what is missing.</p>
        <p>Software calculates the numerical ranking. The optional AI investigator can inspect evidence and produce cited summaries, but it does not choose the scores. Rumors and uncertainty remain labeled.</p>
      </section>

      <section className="ranking-section" aria-labelledby="ranking-limits">
        <p className="eyebrow">READ THE LIMITS TOO</p>
        <h2 id="ranking-limits">A view of our sources.</h2>
        <p>API searches have request limits, feeds are recent snapshots, and some sources arrive late. GNews free access excludes the latest 12 hours. Momentum uses the available window, which may end before the time you refresh.</p>
        <p>Event grouping and copy detection can make mistakes. A parsed injury availability change does not automatically qualify as a reviewed development or earn freshness points.</p>
        <p>The briefing marks partial collection, failed sources, and stale data. The result is always the most-covered stories among our monitored sources.</p>
        <a className="secondary-button ranking-back" href={briefingLink()}>Back to the NBA briefing</a>
      </section>
      <footer className="site-footer"><div><strong>COURT SIDE.</strong><p>The reporting behind the order.</p></div><a href="https://github.com/awsun124/Courtside-Agent/blob/main/docs/ranking.md" target="_blank" rel="noopener noreferrer">Technical methodology</a></footer>
    </main>
  </div>
}
