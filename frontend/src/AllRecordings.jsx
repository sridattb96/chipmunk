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
    const now = new Date();
    const diffMs = now - d;
    const diffMins = diffMs / 60000;

    if (diffMins < 1) return 'less than a min ago';
    if (diffMins < 60) return `${Math.floor(diffMins)} minute${Math.floor(diffMins) === 1 ? '' : 's'} ago`;

    const isCurrentYear = d.getFullYear() === now.getFullYear();
    const monthDay = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    if (isCurrentYear) return monthDay;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return iso;
  }
}

const PILL_COLORS = [
  { bg: '#fef3c7', text: '#92400e', border: '#fde68a' },  // amber
  { bg: '#dbeafe', text: '#1e40af', border: '#bfdbfe' },  // blue
  { bg: '#dcfce7', text: '#166534', border: '#bbf7d0' },  // green
  { bg: '#fce7f3', text: '#9d174d', border: '#fbcfe8' },  // pink
  { bg: '#ede9fe', text: '#5b21b6', border: '#ddd6fe' },  // purple
  { bg: '#ffedd5', text: '#9a3412', border: '#fed7aa' },  // orange
  { bg: '#e0f2fe', text: '#075985', border: '#bae6fd' },  // sky
  { bg: '#fdf2f8', text: '#831843', border: '#f9a8d4' },  // rose
  { bg: '#ecfdf5', text: '#065f46', border: '#6ee7b7' },  // emerald
  { bg: '#fff7ed', text: '#7c2d12', border: '#fdba74' },  // burnt orange
  { bg: '#f0f9ff', text: '#0c4a6e', border: '#7dd3fc' },  // light blue
  { bg: '#fafafa', text: '#292524', border: '#d6d3d1' },  // stone
  { bg: '#f5f3ff', text: '#4c1d95', border: '#c4b5fd' },  // violet
  { bg: '#ecfeff', text: '#164e63', border: '#67e8f9' },  // cyan
  { bg: '#fef9c3', text: '#713f12', border: '#fef08a' },  // yellow
];

function indexToColor(colorIndex) {
  return PILL_COLORS[colorIndex % PILL_COLORS.length];
}

function formatDetailDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    if (d.toDateString() === now.toDateString()) return `Today at ${time}`;
    if (d.toDateString() === yesterday.toDateString()) return `Yesterday at ${time}`;
    const monthDay = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    if (d.getFullYear() === now.getFullYear()) return `${monthDay} at ${time}`;
    return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} at ${time}`;
  } catch {
    return iso;
  }
}

const WAVEFORM_BARS = [4, 8, 12, 7, 14, 9, 5, 11, 6, 10];

function WaveformIcon() {
  return (
    <svg width="29" height="14" viewBox="0 0 29 14" className="item-waveform" aria-hidden>
      {WAVEFORM_BARS.map((h, i) => (
        <rect key={i} x={i * 3} y={(14 - h) / 2} width="2" height={h} rx="1" />
      ))}
    </svg>
  );
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
              <WaveformIcon />
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
              <div className="detail-header">
                <h1 className="detail-title">{detail.name}</h1>
                <p className="detail-header-meta">{formatDetailDate(detail.created_at)} · {detail.duration}</p>
              </div>
              <div className="detail-audio-placeholder" aria-hidden>
                <div className="audio-waveform-bars">
                  {Array.from({ length: 40 }, (_, i) => {
                    const h = 8 + Math.abs(Math.sin(i * 1.7 + 1) * 22 + Math.sin(i * 0.9) * 10);
                    return <span key={i} className={`audio-bar ${i < 14 ? 'audio-bar-played' : ''}`} style={{ height: `${h}px` }} />;
                  })}
                </div>
                <div className="audio-controls-row">
                  <div className="audio-play-btn" />
                  <div className="audio-progress-track">
                    <div className="audio-progress-fill" />
                  </div>
                  <span className="audio-time">0:00 / {detail.duration}</span>
                </div>
              </div>
              <div className="detail-content">
                <section>
                  <h2 className="detail-heading">Summary</h2>
                  <p className="detail-summary">{detail.summary}</p>
                </section>
                {detail.topics?.length > 0 && (
                  <section className="detail-topics-section">
                    <span className="detail-topics-label">Topics:</span>
                    <div className="detail-topics">
                      {detail.topics.map((t, i) => {
                        const colorIdx = detail.topic_colors?.[t] ?? i;
                        const c = indexToColor(colorIdx);
                        return (
                          <span key={i} className="topic-chip" style={{ background: c.bg, color: c.text, borderColor: c.border }}>
                            {t}
                          </span>
                        );
                      })}
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
