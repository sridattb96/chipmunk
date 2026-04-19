import { useState, useCallback } from 'react';
import { getConfig, getDriveToken, saveToDrive } from './api';

export function DrivePicker({ recordingId, defaultFilename = 'call_notes.md', onSaved, onClose }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filename, setFilename] = useState(defaultFilename);

  const openPicker = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await getConfig(); // Ensure config loaded
      const accessToken = await getDriveToken();

      return new Promise((resolve, reject) => {
        if (typeof gapi === 'undefined') {
          reject(new Error('Google API not loaded'));
          return;
        }
        gapi.load('picker', () => {
          const view = new google.picker.DocsView()
            .setIncludeFolders(true)
            .setMimeTypes('application/vnd.google-apps.folder')
            .setSelectFolderEnabled(true);
          const picker = new google.picker.PickerBuilder()
            .addView(view)
            .setOAuthToken(accessToken)
            .setCallback((data) => {
              if (data.action === google.picker.Action.PICKED && data.docs?.length > 0) {
                resolve(data.docs[0].id);
              } else if (data.action === google.picker.Action.CANCEL) {
                reject(new Error('Cancelled'));
              }
            })
            .build();
          picker.setVisible(true);
        });
      });
    } catch (err) {
      setError(err.message || 'Failed to open picker');
      setLoading(false);
    }
  }, []);

  const handleSave = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const folderId = await openPicker();
      if (!folderId) return;
      await saveToDrive(folderId, recordingId, filename);
      onSaved?.();
      onClose?.();
    } catch (err) {
      if (err.message !== 'Cancelled') {
        setError(err.message || 'Failed to save');
      }
    } finally {
      setLoading(false);
    }
  }, [openPicker, recordingId, filename, onSaved, onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Save to Google Drive</h3>
        <p>Choose where to save the call summary and transcript.</p>
        <label>
          Filename:
          <input
            type="text"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
          />
        </label>
        {error && <div className="error">{error}</div>}
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={loading}
          >
            {loading ? 'Opening picker...' : 'Choose folder & save'}
          </button>
        </div>
      </div>
    </div>
  );
}
