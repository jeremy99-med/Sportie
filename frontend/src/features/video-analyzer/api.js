import { apiFetch } from "../../shared/http.js";

const UPLOADS = "/api/video/uploads/";

export function uploadVideo(file) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch(UPLOADS, { method: "POST", body: form });
}

export const listUploads = () => apiFetch(UPLOADS);

export const getUpload = (id) => apiFetch(`${UPLOADS}${id}/`);

export const analyzeUpload = (id, corners, attackDirection) =>
  apiFetch(`${UPLOADS}${id}/analyze/`, {
    method: "POST",
    body: { corners, attack_direction: attackDirection },
  });

export const deleteUpload = (id) => apiFetch(`${UPLOADS}${id}/`, { method: "DELETE" });
