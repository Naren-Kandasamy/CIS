import { useState } from 'react';
import Modal from '../common/Modal';

export interface NewCaseValues {
  title: string;
  crime_no: string | null;
  district: string | null;
}

interface NewCaseDialogProps {
  open: boolean;
  onCancel: () => void;
  onSubmit: (values: NewCaseValues) => Promise<void>;
}

export default function NewCaseDialog({ open, onCancel, onSubmit }: NewCaseDialogProps) {
  const [title, setTitle] = useState('');
  const [crimeNo, setCrimeNo] = useState('');
  const [district, setDistrict] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setTitle('');
    setCrimeNo('');
    setDistrict('');
    setError(null);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError('A case title is required.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        title: title.trim(),
        crime_no: crimeNo.trim() || null,
        district: district.trim() || null,
      });
      reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the case file.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onCancel();
      }}
      title="Open a new case file"
      description="Start a fresh investigation folder. Sessions and the evidence board live inside it."
    >
      <form onSubmit={submit} className="dialog-form">
        <label className="dialog-field">
          <span>Case title</span>
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Belagavi jewellery burglary series"
            maxLength={120}
          />
        </label>
        <div className="dialog-field-row">
          <label className="dialog-field">
            <span>Crime no. (optional)</span>
            <input
              value={crimeNo}
              onChange={(e) => setCrimeNo(e.target.value)}
              placeholder="234/2026"
              maxLength={40}
            />
          </label>
          <label className="dialog-field">
            <span>District (optional)</span>
            <input
              value={district}
              onChange={(e) => setDistrict(e.target.value)}
              placeholder="Belagavi"
              maxLength={60}
            />
          </label>
        </div>
        {error && <p className="dialog-error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              reset();
              onCancel();
            }}
            disabled={busy}
          >
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={busy || !title.trim()}>
            {busy ? 'Opening…' : 'Open case'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
