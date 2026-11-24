import { useState } from "react";
import { uploadVideo } from "../api.js";

const MAX_SIZE_MB = 500;

// Lets the user pick a video, agree to the consent notice, and upload it.
export default function UploadForm({ onUploaded }) {
  const [file, setFile] = useState(null);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);

  function handleFileChange(event) {
    const chosen = event.target.files[0];
    setFile(null);
    setError(null);
    if (!chosen) return;
    if (!chosen.type.startsWith("video/")) {
      setError("Please choose a video file (for example .mp4 or .mov).");
    } else if (chosen.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`That video is too large. The limit is ${MAX_SIZE_MB} MB.`);
    } else {
      setFile(chosen);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setUploading(true);
    setError(null);
    try {
      onUploaded(await uploadVideo(file));
    } catch (err) {
      setError(err.body?.error || err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <form className="card border-0 shadow-sm" onSubmit={handleSubmit}>
      <div className="card-body p-4">
        <label htmlFor="video-file" className="form-label fw-semibold">Game video</label>
        <input
          id="video-file"
          type="file"
          accept="video/*"
          className="form-control mb-2"
          onChange={handleFileChange}
        />
        <p className="small text-sp-muted mb-4">MP4 or MOV, up to {MAX_SIZE_MB} MB.</p>

        {error && <div className="alert alert-danger" role="alert">{error}</div>}

        <div className="form-check mb-4">
          <input
            id="consent"
            type="checkbox"
            className="form-check-input"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          <label htmlFor="consent" className="form-check-label">
            Everyone in this video knows it is being recorded and analyzed.
          </label>
        </div>

        <button type="submit" className="btn btn-primary" disabled={!file || !consent || uploading}>
          {uploading ? "Uploading..." : "Upload video"}
        </button>
      </div>
    </form>
  );
}
