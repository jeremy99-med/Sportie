import { useEffect, useState } from "react";
import { getMe } from "../../../shared/auth/api.js";
import AnalysisStatus from "./AnalysisStatus.jsx";
import CornerPicker from "./CornerPicker.jsx";
import UploadForm from "./UploadForm.jsx";

// The Video Analyzer page: upload, pick corners, then see the results.
export default function VideoAnalyzerPage({ onBack }) {
  const [user, setUser] = useState(undefined);
  const [upload, setUpload] = useState(null);

  useEffect(() => {
    getMe()
      .then((result) => setUser(result.user))
      .catch(() => setUser(null));
  }, []);

  let step;
  if (user === undefined) {
    step = <p className="text-sp-muted">Loading...</p>;
  } else if (user === null) {
    step = (
      <div className="alert alert-info">
        Please <a href="#community-game-ranker">log in</a> first, then come back here.
      </div>
    );
  } else if (upload === null) {
    step = <UploadForm onUploaded={setUpload} />;
  } else if (upload.status === "uploaded") {
    step = <CornerPicker upload={upload} onStarted={setUpload} />;
  } else {
    step = <AnalysisStatus upload={upload} onChange={setUpload} onStartOver={() => setUpload(null)} />;
  }

  return (
    <main className="container py-5">
      <button type="button" className="btn btn-link px-0 mb-4" onClick={onBack}>
        ← Back to Sportie
      </button>
      <header className="mb-4">
        <p className="eyebrow mb-2">VIDEO ANALYZER</p>
        <h1 className="fw-bold">Upload a game</h1>
        <p className="lead text-secondary">
          Upload a 5v5 futsal clip to track players, see a top-down view, and get passing hints.
        </p>
      </header>
      {step}
    </main>
  );
}
