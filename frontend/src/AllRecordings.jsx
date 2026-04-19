import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { listRecordings, getRecording, searchRecordings } from './api';
import { RecordingModal } from './RecordingModal';
import { downloadTranscript, exportToDrive } from './services/ExportService';
import './AllRecordings.css';

function formatDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', {
      month: 'numeric',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debouncedValue;
}

export function AllRecordings() {
  const { id: selected } = useParams();
  const navigate = useNavigate();
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  const [list, setList] = useState([]);
  const [detail, setDetail] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showRecordingModal, setShowRecordingModal] = useState(false);
  const [exportingToDrive, setExportingToDrive] = useState(false);

  const debouncedQuery = useDebounce(searchQuery, 300);

  const loadList = useCallback(async (query) => {
    try {
      setError(null);
      const data = query
        ? await searchRecordings(query)
        : await listRecordings();
      setList(data);
      if (data.length > 0) {
        const ids = new Set(data.map((r) => r.id));
        if (!selectedRef.current || !ids.has(selectedRef.current)) {
          navigate('/recordings/' + data[0].id, { replace: true });
        }
      }
    } catch (e) {
      setError(e.message || 'Failed to load recordings');
      setList([]);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    setLoading(true);
    loadList(debouncedQuery);
  }, [debouncedQuery]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    getRecording(selected)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => { cancelled = true; };
  }, [selected]);

  const handleExportToDrive = useCallback(async () => {
    if (!detail) return;
    setExportingToDrive(true);
    try {
      await exportToDrive(detail);
    } catch (err) {
      if (err.message !== 'Cancelled') {
        setError(err.message || 'Export to Drive failed');
      }
    } finally {
      setExportingToDrive(false);
    }
  }, [detail]);

  const handleRecordingSaved = useCallback(async () => {
    setShowRecordingModal(false);
    const data = debouncedQuery
      ? await searchRecordings(debouncedQuery)
      : await listRecordings();
    setList(data);
    setLoading(false);
    if (data.length > 0) {
      navigate('/recordings/' + data[0].id, { replace: true });
    }
  }, [debouncedQuery, navigate]);

  return (
    <div className="all-recordings-page">
      <div className="all-recordings">
        <div className="all-recordings-header">
          <h1 className="all-recordings-title">All Recordings</h1>
          <button
            type="button"
            className="btn btn-primary all-recordings-new-btn"
            onClick={() => setShowRecordingModal(true)}
          >
            <i className="fa-sharp fa-solid fa-plus" aria-hidden />
            <span>New Recording</span>
          </button>
        </div>
        <div className="all-recordings-search-bar">
          <i className="fa-solid fa-magnifying-glass all-recordings-search-icon" aria-hidden />
          <input
            type="search"
            className="all-recordings-search"
            placeholder="Search by title, summary, or topics"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

      {error && <div className="all-recordings-error">{error}</div>}
      {loading && <div className="all-recordings-loading">Loading...</div>}

      <div className="all-recordings-layout">
        <aside className="all-recordings-sidebar">
          {list.map((rec) => (
            <button
              key={rec.id}
              type="button"
              className={`all-recordings-item ${selected === rec.id ? 'selected' : ''}`}
              onClick={() => navigate('/recordings/' + rec.id)}
            >
              <span className="item-name">{rec.name}</span>
              <span className="item-meta">
                {rec.duration} · {formatDate(rec.created_at)}
              </span>
            </button>
          ))}
        </aside>
        <main className="all-recordings-detail">
          {detail ? (
            <>
              <div className="detail-content">
                <section>
                  <h2 className="detail-heading">Summary</h2>
                  <p className="detail-summary">{detail.summary}</p>
                </section>
                {detail.topics?.length > 0 && (
                  <section className="detail-topics-section">
                    <span className="detail-topics-label">Topics:</span>
                    <div className="detail-topics">
                      {detail.topics.map((t, i) => (
                        <span key={i} className="topic-chip">{t}</span>
                      ))}
                    </div>
                  </section>
                )}
              </div>
              <div className="detail-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => downloadTranscript(detail)}
                  title="Download transcript as text file"
                >
                  <i className="fa-sharp fa-solid fa-download" aria-hidden />
                  <span>Download transcript</span>
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleExportToDrive}
                  disabled={exportingToDrive}
                  title="Save summary and transcript to Google Drive"
                >
                  <i className="fa-sharp fa-solid fa-arrow-up-right-from-square" aria-hidden />
                  <span>{exportingToDrive ? 'Opening...' : 'Export to Google Drive'}</span>
                </button>
              </div>
            </>
          ) : (
            <div className="detail-empty">
              {list.length === 0
                ? 'No recordings yet.'
                : 'Select a recording to view details.'}
            </div>
          )}
        </main>
      </div>
    </div>

    {showRecordingModal && (
      <RecordingModal
        onClose={() => setShowRecordingModal(false)}
        onSaved={handleRecordingSaved}
      />
    )}

    </div>
  );
}
