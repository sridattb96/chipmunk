import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getDbSnapshot } from './api';
import './DbSnapshot.css';

export function DbSnapshot() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchSnapshot = async () => {
    setLoading(true);
    setError(null);
    try {
      const snapshot = await getDbSnapshot();
      setData(snapshot);
    } catch (err) {
      setError(err.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSnapshot();
    const interval = setInterval(fetchSnapshot, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !data) {
    return (
      <div className="db-snapshot">
        <div className="db-snapshot-header">
          <h1>Database Snapshot</h1>
          <Link to="/" className="db-snapshot-back">← Back</Link>
        </div>
        <div className="db-snapshot-loading">Loading...</div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="db-snapshot">
        <div className="db-snapshot-header">
          <h1>Database Snapshot</h1>
          <Link to="/" className="db-snapshot-back">← Back</Link>
        </div>
        <div className="db-snapshot-error">{error}</div>
      </div>
    );
  }

  const { sql = {}, chroma = {} } = data || {};

  return (
    <div className="db-snapshot">
      <div className="db-snapshot-header">
        <h1>Database Snapshot</h1>
        <div className="db-snapshot-actions">
          <button type="button" onClick={fetchSnapshot} disabled={loading}>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
          <Link to="/" className="db-snapshot-back">← Back</Link>
        </div>
      </div>

      {sql.error && (
        <div className="db-snapshot-error">SQL: {sql.error}</div>
      )}

      <div className="db-snapshot-grid">
        <section className="db-snapshot-card">
          <h2>SQLite</h2>
          <div className="db-snapshot-section">
            <h3>Users</h3>
            <p className="db-snapshot-count">{sql.users?.count ?? '-'}</p>
          </div>
          <div className="db-snapshot-section">
            <h3>Recordings</h3>
            <p className="db-snapshot-count">{sql.recordings?.count ?? '-'}</p>
            {sql.recordings?.sample?.length > 0 && (
              <table className="db-snapshot-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Duration</th>
                    <th>Created</th>
                    <th>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {sql.recordings.sample.map((r) => (
                    <tr key={r.id}>
                      <td><code>{r.id}</code></td>
                      <td>{r.name}</td>
                      <td>{r.duration}</td>
                      <td>{r.created_at}</td>
                      <td className="db-snapshot-preview">{r.summary_preview}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="db-snapshot-section">
            <h3>Topics</h3>
            <p className="db-snapshot-count">{sql.topics?.count ?? '-'}</p>
            {sql.topics?.sample?.length > 0 && (
              <table className="db-snapshot-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Call ID</th>
                    <th>Label</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  {sql.topics.sample.map((r) => (
                    <tr key={r.id}>
                      <td><code>{r.id?.slice(0, 8)}…</code></td>
                      <td><code>{r.call_id}</code></td>
                      <td>{r.label}</td>
                      <td className="db-snapshot-preview">{r.desc_preview}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="db-snapshot-section">
            <h3>Embedding jobs</h3>
            <p className="db-snapshot-count">Total: {sql.embedding_jobs?.total ?? '-'}</p>
            {sql.embedding_jobs?.by_status && Object.keys(sql.embedding_jobs.by_status).length > 0 && (
              <div className="db-snapshot-status">
                {Object.entries(sql.embedding_jobs.by_status).map(([status, cnt]) => (
                  <span key={status} className="db-snapshot-badge">
                    {status}: {cnt}
                  </span>
                ))}
              </div>
            )}
            {sql.embedding_jobs?.recent?.length > 0 && (
              <table className="db-snapshot-table">
                <thead>
                  <tr>
                    <th>Call ID</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {sql.embedding_jobs.recent.map((j) => (
                    <tr key={j.id}>
                      <td><code>{j.call_id}</code></td>
                      <td><span className={`db-snapshot-status-${j.status}`}>{j.status}</span></td>
                      <td>{j.created_at}</td>
                      <td className="db-snapshot-preview db-snapshot-error-cell">{j.error || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="db-snapshot-card">
          <h2>ChromaDB (Vectors)</h2>
          {chroma.error && (
            <div className="db-snapshot-error">Chroma: {chroma.error}</div>
          )}
          <div className="db-snapshot-section">
            <h3>Collection</h3>
            <p className="db-snapshot-count">Vectors: {chroma.count ?? '-'}</p>
            {chroma.sample?.length > 0 && (
              <table className="db-snapshot-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>entity_type</th>
                    <th>call_id</th>
                    <th>created_at</th>
                  </tr>
                </thead>
                <tbody>
                  {chroma.sample.map((s) => (
                    <tr key={s.id}>
                      <td><code>{String(s.id).slice(0, 12)}…</code></td>
                      <td>{s.metadata?.entity_type}</td>
                      <td><code>{s.metadata?.call_id}</code></td>
                      <td>{s.metadata?.created_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {(data?.similar_calls?.length > 0 || data?.similar_calls_skipped) && (
            <div className="db-snapshot-section">
              <h3>Semantically similar calls</h3>
              {data?.similar_calls_skipped ? (
                <p className="db-snapshot-count db-snapshot-muted">Could not load similar calls (database may be busy). Refresh in a moment.</p>
              ) : (
                <>
                  <p className="db-snapshot-count">
                    Summary embeddings compared by vector similarity (lower distance = more similar).
                  </p>
                  <div className="db-similar-calls">
                    {data.similar_calls?.map((group, idx) => (
                      group.error ? (
                        <div key={idx} className="db-snapshot-error">Similar calls: {group.error}</div>
                      ) : (
                        <div key={idx} className="db-similar-group">
                          <div className="db-similar-anchor">
                            <strong>{group.anchor?.name ?? group.anchor?.call_id}</strong>
                            <code className="db-similar-call-id">{group.anchor?.call_id}</code>
                          </div>
                          <table className="db-snapshot-table">
                            <thead>
                              <tr>
                                <th>Similar call</th>
                                <th>Call ID</th>
                                <th>Distance</th>
                              </tr>
                            </thead>
                            <tbody>
                              {group.similar?.map((s, i) => (
                                <tr key={i}>
                                  <td>{s.name}</td>
                                  <td><code>{s.call_id}</code></td>
                                  <td>{s.distance}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
