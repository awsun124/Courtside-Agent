import { Icon } from './Icons'
import { formatDate, plural } from './format'
import type { Briefing } from './types'

export default function CollectionActivity({ briefing }: { briefing: Briefing }) {
  return <details className="sidebar-details">
    <summary>Collection activity<Icon name="chevron" /></summary>
    <div className="details-body">
      <p>Saved collection: {formatDate(briefing.as_of, true)}. This activity belongs to this briefing.</p>
      {briefing.data_mode === 'sample' ? <p>Sample mode makes no external news requests.</p>
        : !briefing.collection_activity?.length ? <p>No search activity was recorded for this older briefing. Refresh to record it.</p>
          : <>
            <ol className="history-list collection-activity">{briefing.collection_activity.map((entry, index) => {
              const label = entry.purpose === 'feed' ? 'Feed snapshot' : entry.purpose === 'discovery' ? 'Discovery search'
                : entry.topic === 'injury' ? 'Injury search' : entry.topic === 'game' ? 'Game search' : 'Targeted search'
              return <li key={`${entry.source_id}-${index}`}>
                <strong>{entry.source_name} · {label}</strong>
                <p className={entry.status === 'failed' ? 'collection-failure' : undefined}>{entry.status === 'ok' ? 'Succeeded' : entry.status === 'partial' ? 'Succeeded with partial coverage' : entry.status === 'failed' ? 'Failed' : entry.status === 'unconfigured' ? 'Not configured' : 'Skipped'} · {plural(entry.requests, 'request')}</p>
                {entry.query && <p className="collection-query">Search: <span>{entry.query}</span></p>}
                {entry.selection_reason && <p>{entry.selection_reason}</p>}
                {entry.window_start && entry.window_end && <p>Search window: {formatDate(entry.window_start, true)} to {formatDate(entry.window_end, true)}</p>}
                {entry.requests > 0 && <>
                  <p>{plural(entry.returned_results, 'result')} returned · {plural(entry.added_articles, 'new article URL')} added</p>
                  <p>{plural(entry.publisher_labels, 'publisher label')} in these results · {entry.added_publisher_labels} new to this collection</p>
                  {entry.reporting_groups_added !== undefined && <p>{plural(entry.reporting_groups_added, 'estimated reporting group')} added to the selected story</p>}
                </>}
                {entry.note && <p>{entry.note}</p>}
              </li>
            })}</ol>
            <p>“New” means not already found earlier in this refresh. Counts describe URLs and publisher labels, not independent reporting or changes since a previous briefing.</p>
          </>}
    </div>
  </details>
}
