/**
 * RadioWatch API client — connects to the local FastAPI backend which in turn
 * proxies Radio Browser (https://api.radio-browser.info/). No API key needed.
 */
import { API_BASE } from "./defaults";
import type { Alert, BackendStatus, KeywordConfig, Language, LanguageProfile, PipelineConfig, Station } from "./types";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function json(body: unknown): RequestInit {
  return { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

function buildMonitorJob(stations: Station[], kw: KeywordConfig, pl: PipelineConfig) {
  return {
    stations: stations.map((s) => ({
      id: s.id,
      name: s.name,
      slug: s.slug,
      countryName: s.location.countryName,
      countryCode: s.location.countryCode,
      languageCode: s.languageCode,
      streamUrls: s.streams.map((st) => st.url),
    })),
    keywordConfig: kw,
    pipelineConfig: pl,
  };
}

export const api = {
  // ── Discovery ──────────────────────────────────────────────────────────────
  languages: () => request<Language[]>("/api/radio/languages"),
  profiles: () => request<LanguageProfile[]>("/api/radio/profiles"),
  stations: (code: string, limit = 100, offset = 0) =>
    request<Station[]>(`/api/radio/languages/${code}/radios?limit=${limit}&offset=${offset}`),
  countryStations: (countryName: string, offset = 0, limit = 40) =>
    request<Station[]>(
      `/api/radio/countries/${encodeURIComponent(countryName)}/radios?limit=${limit}&offset=${offset}`,
    ),
  searchStations: (q: string, limit = 40) =>
    request<Station[]>(`/api/radio/radios/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  stationById: (id: string) => request<Station>(`/api/radio/radios/${id}`),

  // ── Monitor ────────────────────────────────────────────────────────────────
  status: () => request<BackendStatus>("/status"),
  start: (stations: Station[], keywords: KeywordConfig, pipeline: PipelineConfig) =>
    request<BackendStatus>("/monitor/start", { method: "POST", ...json(buildMonitorJob(stations, keywords, pipeline)) }),
  stopStation: (id: string) => request<BackendStatus>(`/monitor/${id}`, { method: "DELETE" }),
  stopAll: () => request<BackendStatus>("/monitor/stop-all", { method: "POST" }),
  pause: (id: string) => request<BackendStatus>(`/monitor/${id}/pause`, { method: "POST" }),
  resume: (id: string) => request<BackendStatus>(`/monitor/${id}/resume`, { method: "POST" }),
  patchKeywords: (payload: KeywordConfig) =>
    request<BackendStatus>("/keywords", { method: "PATCH", ...json(payload) }),
  patchPipeline: (payload: PipelineConfig) =>
    request<BackendStatus>("/pipeline", { method: "PATCH", ...json(payload) }),

  // ── Alerts ─────────────────────────────────────────────────────────────────
  alerts: (language = "") =>
    request<Alert[]>(`/alerts${language ? `?language=${language}` : ""}`),
  alertById: (id: string) => request<Alert>(`/alerts/${id}`),
  markAlert: (id: string, reviewed: boolean) =>
    request<Alert>(`/alerts/${id}`, { method: "PATCH", ...json({ reviewed }) }),
  deleteAlert: (id: string) => request<{ ok: boolean }>(`/alerts/${id}`, { method: "DELETE" }),
  exportAlerts: (ids: string[]) => `${API_BASE}/alerts/export?ids=${ids.join(",")}`,
  clipUrl: (id: string) => `${API_BASE}/alerts/${id}/clip`,

  // ── spaCy ──────────────────────────────────────────────────────────────────
  installSpacy: (model: string) =>
    request<{ ok: boolean; model: string; output: string }>("/api/spacy/install", {
      method: "POST",
      ...json({ model }),
    }),
};
