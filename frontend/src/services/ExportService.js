import { getConfig, getDriveToken, saveToDrive } from '../api';

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

function formatTranscriptForDownload(recording) {
  const lines = [];
  lines.push(recording.name || 'Recording');
  lines.push('='.repeat(60));
  lines.push(`Date: ${formatDate(recording.created_at)}`);
  lines.push(`Duration: ${recording.duration || '—'}`);
  lines.push('');
  if (recording.summary) {
    lines.push('Summary');
    lines.push('-'.repeat(40));
    lines.push(recording.summary);
    lines.push('');
  }
  if (recording.topics?.length) {
    lines.push('Topics: ' + recording.topics.join(', '));
    lines.push('');
  }
  lines.push('Transcript');
  lines.push('-'.repeat(40));
  const transcript = (recording.transcript || '').trim();
  if (transcript) {
    const paragraphs = transcript.split(/\n\n+/).filter(Boolean);
    lines.push(paragraphs.map((p) => p.trim()).join('\n\n'));
  } else {
    lines.push('No transcript available.');
  }
  return lines.join('\n');
}

function sanitizeFilename(name) {
  return (name || 'transcript').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-') || 'transcript';
}

/**
 * Download the recording transcript as a formatted text file.
 */
export function downloadTranscript(recording) {
  const content = formatTranscriptForDownload(recording);
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${sanitizeFilename(recording.name)}-transcript.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function deriveDriveFilename(recording) {
  const base = (recording.name || 'call_notes').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '_') || 'call_notes';
  return `${base}.md`;
}

/**
 * Open the Google Picker to choose a folder, then save the recording's summary and transcript there.
 * Returns a Promise that resolves when done, or rejects on error or if the user cancels.
 */
export async function exportToDrive(recording) {
  await getConfig();
  const accessToken = await getDriveToken();

  const folderId = await new Promise((resolve, reject) => {
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
          } else {
            reject(new Error('Cancelled'));
          }
        })
        .build();
      picker.setVisible(true);
    });
  });

  const filename = deriveDriveFilename(recording);
  await saveToDrive(folderId, recording.id, filename);
}
