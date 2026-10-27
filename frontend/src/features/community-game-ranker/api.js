import { apiFetch } from "../../shared/http.js";

const GAMES = "/api/ranker/games/";

// Ranked games for one day (YYYY-MM-DD, US Eastern; default today), optionally one sport.
export function getGames({ date, sport } = {}) {
  const params = {};
  if (date) params.date = date;
  if (sport) params.sport = sport;
  return apiFetch(GAMES, { params });
}

export const getGame = (id) => apiFetch(`${GAMES}${id}/`);

// value: 1 (up) or -1 (down). Sending the same value again removes the vote.
// Resolves to {my_vote, net_votes, importance_score}.
export const castVote = (id, value) =>
  apiFetch(`${GAMES}${id}/vote/`, { method: "POST", body: { value } });
