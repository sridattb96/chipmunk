import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getTopicChains } from './api';
import './TopicChains.css';

function formatDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'numeric',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

export function TopicChains() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedGroupId, setSelectedGroupId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getTopicChains()
      .then((d) => {
        if (!cancelled) {
          setData(d);
          if (d?.groups?.length > 0 && !selectedGroupId) {
            setSelectedGroupId(d.groups[0].id);
          }
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || 'Failed to load');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const selectedGroup = data?.groups?.find((g) => g.id === selectedGroupId);

  if (loading) {
    return (
      <div className="topic-chains">
        <div className="topic-chains-header">
          <h1>Topic Chains</h1>
          <Link to="/" className="topic-chains-back">← Back</Link>
        </div>
        <div className="topic-chains-loading">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="topic-chains">
        <div className="topic-chains-header">
          <h1>Topic Chains</h1>
          <Link to="/" className="topic-chains-back">← Back</Link>
        </div>
        <div className="topic-chains-error">{error}</div>
      </div>
    );
  }

  return (
    <div className="topic-chains">
      <div className="topic-chains-header">
        <h1>Topic Chains</h1>
        <Link to="/" className="topic-chains-back">← Back</Link>
      </div>
      <div className="topic-chains-layout">
        <aside className="topic-chains-sidebar">
          <h2>Topics</h2>
          {!data?.groups?.length ? (
            <p className="topic-chains-empty">No topic groups. Record meetings with similar themes to see chains.</p>
          ) : (
            <ul className="topic-chains-list">
              {data.groups.map((g) => (
                <li key={g.id}>
                  <button
                    type="button"
                    className={`topic-chains-item ${selectedGroupId === g.id ? 'topic-chains-item-active' : ''}`}
                    onClick={() => setSelectedGroupId(g.id)}
                  >
                    <span className="topic-chains-item-title">{g.title}</span>
                    <span className="topic-chains-item-date">{formatDate(g.createdAt)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <main className="topic-chains-main">
          <h2>
            <i className="fa-sharp fa-solid fa-clipboard-list" aria-hidden />
            <span>Topic Chain View</span>
          </h2>
          {!selectedGroup ? (
            <p className="topic-chains-empty">Select a topic group to view the call chain.</p>
          ) : (
            <>
              <div className="topic-chains-col-headers">
                <span>Recording</span>
                <span>Description</span>
                <span>Insights</span>
              </div>
            <div className="topic-chains-chain">
              {selectedGroup.recordingIds.map((recId, idx) => {
                const rec = data.recordingsById?.[recId];
                if (!rec) return null;
                const isLast = idx === selectedGroup.recordingIds.length - 1;
                return (
                  <div key={recId} className="topic-chains-node-wrapper">
                    <div className="topic-chains-node">
                      <div className="topic-chains-node-circle">
                        <span className="topic-chains-node-name">{rec.name}</span>
                      </div>
                      <div className="topic-chains-node-summary">
                        {rec.summary || 'No summary.'}
                      </div>
                      <div className="topic-chains-node-decisions">
                        {rec.decisions?.length ? (
                          <ul>
                            {rec.decisions.map((d, i) => (
                              <li key={i}>{d}</li>
                            ))}
                          </ul>
                        ) : (
                          <span className="topic-chains-node-no-decisions">None made.</span>
                        )}
                      </div>
                    </div>
                    {!isLast && (
                      <div className="topic-chains-arrow" aria-hidden>
                        ↑
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
