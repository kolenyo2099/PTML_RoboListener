/**
 * RadioWatch — frontend entry point.
 * Powered by Radio Browser (https://api.radio-browser.info/), free & key-free.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bell, Download, Headphones, Pause, Play, Radio, RefreshCw, Search, Square, Trash2, Volume2, VolumeX, X,
} from "lucide-react";
import { api } from "./lib/api";
import { API_BASE, defaultKeywords, defaultPipeline, FALLBACK_LANGUAGES, presets } from "./lib/defaults";
import type {
  Alert, BackendStatus, KeywordConfig, Language,
  LanguageProfile, PipelineConfig, Station,
} from "./lib/types";
import "./styles.css";

type View = "discovery" | "monitor" | "keywords" | "pipeline" | "alerts";
type Toast = { id: string; message: string; cls?: string };

// ── Session bootstrap ─────────────────────────────────────────────────────────
const savedRaw = localStorage.getItem("radiowatch-session");
const saved = JSON.parse(savedRaw || "{}");
const isFirstBrowserSession = !sessionStorage.getItem("rw-started");
const initialShowResume = !!savedRaw && isFirstBrowserSession &&
  ((saved.selectedIds?.length ?? 0) > 0 || (saved.keywords?.keywords?.length ?? 0) > 0);

// ── App ───────────────────────────────────────────────────────────────────────
function App() {
  const [view, setView] = useState<View>("discovery");
  const [languages, setLanguages] = useState<Language[]>([]);
  const [profiles, setProfiles] = useState<LanguageProfile[]>([]);
  const [activeCodes, setActiveCodes] = useState<string[]>(saved.activeCodes || ["es"]);
  const [stations, setStations] = useState<Station[]>(saved.stations || []);
  const [selectedIds, setSelectedIds] = useState<string[]>(saved.selectedIds || []);
  const [stationsLoadedAt, setStationsLoadedAt] = useState<number | null>(saved.stationsLoadedAt || null);
  const [keywords, setKeywords] = useState<KeywordConfig>(saved.keywords || defaultKeywords);
  const [pipeline, setPipeline] = useState<PipelineConfig>(saved.pipeline || defaultPipeline);
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [notice, setNotice] = useState("");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [showResume, setShowResume] = useState(initialShowResume);
  const [languagePanelOpen, setLanguagePanelOpen] = useState(!saved.stations?.length);
  const [drawerStation, setDrawerStation] = useState<Station | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const prevMatchesRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── WebSocket with 5 s reconnect ────────────────────────────────────────────
  useEffect(() => {
    function connect() {
      const ws = new WebSocket(`ws://${window.location.host}/ws/status`);
      wsRef.current = ws;
      ws.onmessage = (event) => {
        const next = JSON.parse(event.data) as BackendStatus;
        setStatus(next);
        setWsConnected(true);
        if (next.totalMatchesSession > prevMatchesRef.current) {
          prevMatchesRef.current = next.totalMatchesSession;
          next.stationStatuses
            .filter((s) => s.status === "match")
            .forEach((s) => {
              const kw = s.matchedKeywordsInSnippet[0] || "keyword";
              addToast(`${s.languageCode.toUpperCase()} match: "${kw}"`, "match-toast");
            });
        }
      };
      ws.onclose = () => {
        setWsConnected(false);
        retryTimerRef.current = setTimeout(connect, 5000);
      };
      ws.onerror = () => { setWsConnected(false); ws.close(); };
    }
    connect();
    return () => {
      wsRef.current?.close();
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, []);

  // ── Load profiles and languages ─────────────────────────────────────────────
  useEffect(() => {
    api.profiles().then(setProfiles).catch(() => {});
    api.languages()
      .then(setLanguages)
      .catch(() => setLanguages(FALLBACK_LANGUAGES));
    api.status().then(setStatus).catch(() => {});
  }, []);

  // ── Toast auto-dismiss ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!toasts.length) return;
    const t = setTimeout(() => setToasts((p) => p.slice(1)), 4500);
    return () => clearTimeout(t);
  }, [toasts]);

  // ── Persist session ─────────────────────────────────────────────────────────
  useEffect(() => {
    localStorage.setItem(
      "radiowatch-session",
      JSON.stringify({ activeCodes, stations, selectedIds, keywords, pipeline, stationsLoadedAt }),
    );
  }, [activeCodes, stations, selectedIds, keywords, pipeline, stationsLoadedAt]);

  // ── Load alerts ─────────────────────────────────────────────────────────────
  useEffect(() => {
    api.alerts().then(setAlerts).catch(() => {});
  }, [status?.unreviewedAlerts, view]);

  // ── Disk auto-stop ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (status && status.diskFreeMB < 100 && status.activeSlots > 0) {
      api.stopAll().then(setStatus).catch(() => {});
      setNotice("⚠ Disk space critically low (<100 MB) — monitoring stopped automatically.");
    }
  }, [status?.diskFreeMB]);

  function addToast(message: string, cls?: string) {
    setToasts((prev) => [...prev, { id: crypto.randomUUID(), message, cls }]);
  }

  const selectedStations = stations.filter((s) => selectedIds.includes(s.id));
  const activeProfiles = profiles.filter((p) => activeCodes.includes(p.code));
  const diskWarn = status && status.diskFreeMB < 500 && status.diskFreeMB >= 100;
  const diskCritical = status && status.diskFreeMB < 100;

  // ── Language toggling with station pruning ──────────────────────────────────
  function toggleLanguage(code: string) {
    if (activeCodes.includes(code)) {
      const remaining = activeCodes.filter((c) => c !== code);
      const orphanIds = stations
        .filter((s) => s.languageCode === code && !remaining.includes(s.languageCode))
        .map((s) => s.id);
      if (orphanIds.length && selectedIds.some((id) => orphanIds.includes(id))) {
        if (!confirm(`Removing ${code.toUpperCase()} will deselect ${orphanIds.filter((id) => selectedIds.includes(id)).length} selected station(s). Continue?`)) return;
      }
      setActiveCodes(remaining);
      setStations((prev) => prev.filter((s) => s.languageCode !== code || remaining.includes(s.languageCode)));
      setSelectedIds((prev) => prev.filter((id) => !orphanIds.includes(id)));
    } else {
      setActiveCodes([...activeCodes, code]);
    }
  }

  // ── Load stations ───────────────────────────────────────────────────────────
  async function loadStations() {
    if (!activeCodes.length) { setNotice("Select at least one language."); return; }
    try {
      const batches = await Promise.all(activeCodes.map((code) => api.stations(code)));
      const byId = new Map<string, Station>();
      batches.flat().forEach((s) => byId.set(s.id, s));
      setStations(Array.from(byId.values()));
      setStationsLoadedAt(Date.now());
      setLanguagePanelOpen(false);
    } catch (e) {
      setNotice(`Station load failed: ${String(e)}`);
    }
  }

  // ── Keywords ────────────────────────────────────────────────────────────────
  function addKeywords(values: string[]) {
    const existing = new Set(keywords.keywords.map((k) => k.text.toLowerCase()));
    const additions = values.map((v) => v.trim()).filter(Boolean).filter((v) => !existing.has(v.toLowerCase()));
    if (keywords.keywords.length + additions.length > 200) { setNotice("Maximum 200 keywords."); return; }
    const next: KeywordConfig = {
      ...keywords,
      keywords: [
        ...keywords.keywords,
        ...additions.map((text) => ({ id: crypto.randomUUID(), text, addedAt: new Date().toISOString() })),
      ],
    };
    setKeywords(next);
    api.patchKeywords(next).catch(() => {});
  }

  // ── Monitoring ──────────────────────────────────────────────────────────────
  async function startMonitoring(stationsToStart?: Station[]) {
    const targets = stationsToStart ?? selectedStations;
    if (!targets.length) return;
    try {
      const next = await api.start(targets, keywords, pipeline);
      setStatus(next);
      if (!stationsToStart) setView("monitor");
    } catch (e) {
      setNotice(`Failed to start monitoring: ${String(e)}`);
    }
  }

  // ── Resume session ──────────────────────────────────────────────────────────
  function handleResume() {
    sessionStorage.setItem("rw-started", "1");
    setShowResume(false);
    setView("monitor");
  }
  function handleStartFresh() {
    sessionStorage.setItem("rw-started", "1");
    setShowResume(false);
    setActiveCodes(["es"]);
    setStations([]);
    setSelectedIds([]);
    setKeywords(defaultKeywords);
    setPipeline(defaultPipeline);
    setStationsLoadedAt(null);
    localStorage.removeItem("radiowatch-session");
  }

  // ── Stale URL refresh ───────────────────────────────────────────────────────
  const STALE_HOURS = 24;
  const isStale = stationsLoadedAt != null && (Date.now() - stationsLoadedAt) > STALE_HOURS * 3600 * 1000;

  async function refreshStaleStations() {
    try {
      const refreshed = await Promise.all(selectedStations.map((s) =>
        s.id.startsWith("custom-") ? Promise.resolve(s) : api.stationById(s.id).catch(() => s),
      ));
      setStations((prev) => {
        const byId = new Map(prev.map((s) => [s.id, s]));
        refreshed.forEach((s) => byId.set(s.id, s));
        return Array.from(byId.values());
      });
      setStationsLoadedAt(Date.now());
      setNotice("Station stream URLs refreshed.");
    } catch (e) {
      setNotice(`Refresh failed: ${String(e)}`);
    }
  }

  return (
    <div>
      {/* ── Top bar ──────────────────────────────────────────────────────────── */}
      <header className="topbar">
        <div className="brand"><Radio size={22} /> RadioWatch</div>
        <nav>
          {(["discovery", "monitor", "keywords", "pipeline", "alerts"] as View[]).map((v) => (
            <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>{v.charAt(0).toUpperCase() + v.slice(1)}</button>
          ))}
        </nav>
      </header>

      {/* ── Status bar ──────────────────────────────────────────────────────── */}
      <section className="status">
        <span className={`dot ${wsConnected ? "ok" : ""}`} />
        {wsConnected ? "Backend connected" : "Backend offline"}
        {activeCodes.map((c) => <b className="pill" key={c}>{c.toUpperCase()}</b>)}
        <span>{selectedStations.length} selected</span>
        <span>{keywords.keywords.length} keywords</span>
        <span>{alerts.filter((a) => !a.reviewed).length} unreviewed alerts</span>
        {diskWarn && <span className="disk-warn">⚠ Disk {status!.diskFreeMB} MB free</span>}
        {diskCritical && <span className="disk-critical">🛑 Disk critically low</span>}
      </section>

      {/* ── Banners ──────────────────────────────────────────────────────────── */}
      {!wsConnected && status && (
        <div className="banner warn"><p>Lost connection to backend — retrying every 5 s…</p></div>
      )}
      {diskCritical && (
        <div className="banner danger"><p>Disk space critically low (&lt;100 MB). Monitoring stopped automatically.</p></div>
      )}
      {showResume && (
        <div className="banner resume">
          <p>Resume your previous session? ({selectedStations.length} station(s), {keywords.keywords.length} keyword(s))</p>
          <div className="actions">
            <button className="primary" onClick={handleResume}>Resume</button>
            <button onClick={handleStartFresh}>Start fresh</button>
          </div>
        </div>
      )}
      {isStale && !showResume && selectedStations.length > 0 && (
        <div className="banner warn">
          <p>Stream URLs may be stale (loaded &gt;{STALE_HOURS}h ago).</p>
          <div className="actions">
            <button onClick={refreshStaleStations}><RefreshCw size={15} /> Refresh from API</button>
          </div>
        </div>
      )}

      {/* ── Notice ───────────────────────────────────────────────────────────── */}
      {notice && (
        <div className="notice">
          <span>{notice}</span>
          <button onClick={() => setNotice("")}><X size={16} /></button>
        </div>
      )}

      {/* ── Toasts ───────────────────────────────────────────────────────────── */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.cls || ""}`}>
            {t.message}
            <button style={{ marginLeft: 10, background: "none", border: "none", color: "white", cursor: "pointer" }}
              onClick={() => setToasts((p) => p.filter((x) => x.id !== t.id))}><X size={13} /></button>
          </div>
        ))}
      </div>

      {/* ── Views ────────────────────────────────────────────────────────────── */}
      {view === "discovery" && (
        <Discovery
          languages={languages} activeCodes={activeCodes} toggleLanguage={toggleLanguage}
          languagePanelOpen={languagePanelOpen} setLanguagePanelOpen={setLanguagePanelOpen}
          loadStations={loadStations} stations={stations} setStations={setStations}
          selectedIds={selectedIds} setSelectedIds={setSelectedIds}
          profiles={profiles} drawerStation={drawerStation} setDrawerStation={setDrawerStation}
          ytDlpAvailable={status?.ytDlpAvailable ?? false}
        />
      )}
      {view === "monitor" && (
        <Monitor
          selectedStations={selectedStations} status={status} wsConnected={wsConnected}
          startMonitoring={startMonitoring} setSelectedIds={setSelectedIds} activeCodes={activeCodes}
        />
      )}
      {view === "keywords" && (
        <Keywords keywords={keywords} setKeywords={setKeywords} addKeywords={addKeywords}
          activeCodes={activeCodes} profiles={profiles} />
      )}
      {view === "pipeline" && (
        <Pipeline pipeline={pipeline} setPipeline={setPipeline}
          selectedStations={selectedStations} keywords={keywords}
          activeProfiles={activeProfiles} allProfiles={profiles}
          ffmpegAvailable={status?.ffmpegAvailable ?? true}
          ytDlpAvailable={status?.ytDlpAvailable ?? false} />
      )}
      {view === "alerts" && (
        <Alerts alerts={alerts} setAlerts={setAlerts} activeCodes={activeCodes}
          deleteConfirmId={deleteConfirmId} setDeleteConfirmId={setDeleteConfirmId} />
      )}

      {/* ── Delete confirm modal ─────────────────────────────────────────────── */}
      {deleteConfirmId && (
        <DeleteConfirmModal
          onConfirm={async () => {
            await api.deleteAlert(deleteConfirmId).catch(() => {});
            setAlerts((prev) => prev.filter((a) => a.id !== deleteConfirmId));
            setDeleteConfirmId(null);
          }}
          onCancel={() => setDeleteConfirmId(null)}
        />
      )}
    </div>
  );
}

// ── Delete Confirm Modal ──────────────────────────────────────────────────────
function DeleteConfirmModal({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="modal-overlay">
      <div className="modal">
        <h2>Delete alert?</h2>
        <p>This removes the alert record. The audio clip file on disk is not deleted.</p>
        <div className="actions">
          <button onClick={onCancel}>Cancel</button>
          <button className="primary" style={{ background: "#d12b45", borderColor: "#d12b45" }} onClick={onConfirm}>Delete</button>
        </div>
      </div>
    </div>
  );
}

// ── Stream URL classifier ─────────────────────────────────────────────────────
const PLATFORM_HOSTS = ["youtube.com", "youtu.be", "twitch.tv", "facebook.com", "instagram.com", "twitter.com", "x.com", "dailymotion.com", "vimeo.com", "tiktok.com", "kick.com"];

function classifyUrl(url: string): { type: string; hint: string; needsYtDlp: boolean } {
  const u = url.toLowerCase();
  if (PLATFORM_HOSTS.some((h) => u.includes(h)))
    return { type: "Platform", hint: "YouTube, Twitch, and similar platforms — yt-dlp resolves the real stream URL automatically.", needsYtDlp: true };
  if (u.endsWith(".m3u8") || u.includes(".m3u8?"))
    return { type: "HLS", hint: "HTTP Live Streaming — works directly with ffmpeg.", needsYtDlp: false };
  if (u.startsWith("rtmp://") || u.startsWith("rtmps://"))
    return { type: "RTMP", hint: "Real-Time Messaging Protocol — works directly with ffmpeg.", needsYtDlp: false };
  if (u.endsWith(".mpd") || u.includes("manifest"))
    return { type: "DASH", hint: "MPEG-DASH manifest — works directly with ffmpeg.", needsYtDlp: false };
  if (u.startsWith("mms://") || u.startsWith("mmsh://"))
    return { type: "MMS", hint: "Microsoft Media Server stream — works directly with ffmpeg.", needsYtDlp: false };
  if (/\.(mp3|aac|ogg|opus|flac|wav)/.test(u))
    return { type: "Direct audio", hint: "Direct audio file or Icecast/Shoutcast stream — works directly with ffmpeg.", needsYtDlp: false };
  if (u.startsWith("http://") || u.startsWith("https://"))
    return { type: "HTTP stream", hint: "Likely an Icecast/Shoutcast or proprietary stream — ffmpeg will try to auto-detect the format.", needsYtDlp: false };
  return { type: "Unknown", hint: "Paste a full URL including the scheme (https://, rtmp://, etc.).", needsYtDlp: false };
}

// ── Custom Stream Form ────────────────────────────────────────────────────────
function CustomStreamForm({ onAdd, ytDlpAvailable }: { onAdd: (station: Station) => void; ytDlpAvailable: boolean }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [langCode, setLangCode] = useState("");
  const [country, setCountry] = useState("");
  const [isTV, setIsTV] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);

  const urlInfo = url.trim() ? classifyUrl(url.trim()) : null;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !url.trim() || !langCode.trim()) return;
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    const station: Station = {
      id: `custom-${crypto.randomUUID()}`,
      name: name.trim(),
      slug,
      location: { cityName: "", countryName: country.trim() || "Custom", countryCode: "" },
      genre: { text: isTV ? "TV (audio)" : "Custom Radio" },
      popularity: { global: 0 },
      streams: [{ url: url.trim(), bitrate: 0, format: urlInfo?.type.toLowerCase() ?? "custom", isHttps: url.trim().startsWith("https") }],
      languageCode: langCode.trim().toLowerCase(),
    };
    onAdd(station);
    setName(""); setUrl(""); setLangCode(""); setCountry(""); setIsTV(false); setOpen(false);
  }

  return (
    <div style={{ marginTop: 12, borderTop: "1px solid #e2e8f0", paddingTop: 12 }}>
      <button onClick={() => setOpen(!open)} style={{ fontSize: 13 }}>
        {open ? "▾" : "▸"} Add custom stream URL
      </button>
      {open && (
        <div style={{ marginTop: 10, maxWidth: 520 }}>
          {/* Format guide */}
          <div style={{ marginBottom: 12 }}>
            <button onClick={() => setGuideOpen(!guideOpen)} style={{ fontSize: 12, color: "#526074", background: "none", border: "none", padding: 0, cursor: "pointer" }}>
              {guideOpen ? "▾" : "▸"} Supported stream formats
            </button>
            {guideOpen && (
              <table style={{ fontSize: 12, marginTop: 6, borderCollapse: "collapse", width: "100%" }}>
                <tbody>
                  {[
                    ["HLS", "https://…/stream.m3u8", "ffmpeg", "TV, radio, most live streams"],
                    ["Icecast / Shoutcast", "https://…:8000/stream", "ffmpeg", "Traditional internet radio"],
                    ["RTMP / RTMPS", "rtmp://…/live/key", "ffmpeg", "Streaming servers"],
                    ["MPEG-DASH", "https://…/manifest.mpd", "ffmpeg", "Adaptive streaming"],
                    ["MMS", "mms://…", "ffmpeg", "Legacy Windows Media"],
                    ["Direct audio", "https://…/audio.mp3", "ffmpeg", "MP3, AAC, OGG, Opus, FLAC"],
                    ["YouTube / Twitch", "https://youtube.com/…", "yt-dlp + ffmpeg", "Requires yt-dlp"],
                  ].map(([fmt, example, tool, notes]) => (
                    <tr key={fmt} style={{ borderBottom: "1px solid #e2e8f0" }}>
                      <td style={{ padding: "4px 8px 4px 0", fontWeight: 600, whiteSpace: "nowrap" }}>{fmt}</td>
                      <td style={{ padding: "4px 8px", fontFamily: "monospace", fontSize: 11, color: "#526074" }}>{example}</td>
                      <td style={{ padding: "4px 8px", whiteSpace: "nowrap" }}>{tool}</td>
                      <td style={{ padding: "4px 0", color: "#627084" }}>{notes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <label>Stream URL
              <input value={url} onChange={(e) => setUrl(e.target.value)}
                placeholder="https://stream.example.com/live.m3u8" required />
            </label>

            {/* Live URL hint */}
            {urlInfo && (
              <div style={{ fontSize: 12, padding: "6px 10px", borderRadius: 6, background: urlInfo.needsYtDlp && !ytDlpAvailable ? "#fff3cd" : "#f0f4f8", color: "#526074" }}>
                <b>{urlInfo.type}</b> — {urlInfo.hint}
                {urlInfo.needsYtDlp && (
                  ytDlpAvailable
                    ? <span style={{ marginLeft: 6, color: "#2d9b6c" }}>✓ yt-dlp detected</span>
                    : <span style={{ marginLeft: 6, color: "#c0392b" }}>⚠ yt-dlp not found — install with <code>pip install yt-dlp</code> or <code>brew install yt-dlp</code></span>
                )}
              </div>
            )}

            <label>Name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="My Radio / Canal 24h" required /></label>
            <div style={{ display: "flex", gap: 12 }}>
              <label style={{ flex: 1 }}>Language code
                <input value={langCode} onChange={(e) => setLangCode(e.target.value)} placeholder="es, en, pt…" required />
              </label>
              <label style={{ flex: 1 }}>Country (optional)
                <input value={country} onChange={(e) => setCountry(e.target.value)} placeholder="Spain" />
              </label>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input type="checkbox" checked={isTV} onChange={(e) => setIsTV(e.target.checked)} style={{ width: "auto", flexShrink: 0 }} />
              TV stream — video is ignored, only audio is transcribed
            </label>
            <button type="submit" className="primary" disabled={!name.trim() || !url.trim() || !langCode.trim()} style={{ alignSelf: "flex-start" }}>
              Add stream
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

// ── Discovery ─────────────────────────────────────────────────────────────────
function Discovery(props: {
  languages: Language[]; activeCodes: string[]; toggleLanguage: (code: string) => void;
  languagePanelOpen: boolean; setLanguagePanelOpen: (v: boolean) => void;
  loadStations: () => void; stations: Station[]; setStations: (fn: (prev: Station[]) => Station[]) => void;
  selectedIds: string[]; setSelectedIds: (v: string[]) => void;
  profiles: LanguageProfile[]; drawerStation: Station | null; setDrawerStation: (s: Station | null) => void;
  ytDlpAvailable: boolean;
}) {
  const [langSearch, setLangSearch] = useState("");
  const [stationQuery, setStationQuery] = useState("");
  const [langFilter, setLangFilter] = useState("all");
  const [genre, setGenre] = useState("all");
  const [countryFilter, setCountryFilter] = useState("all");
  const [countryOffsets, setCountryOffsets] = useState<Record<string, number>>({});
  const [loadingMore, setLoadingMore] = useState<Record<string, boolean>>({});
  const [countryHasMore, setCountryHasMore] = useState<Record<string, boolean>>({});

  const LOAD_MORE_LIMIT = 40;

  function addCustomStation(station: Station) {
    props.setStations((prev) => {
      if (prev.some((s) => s.id === station.id)) return prev;
      return [...prev, station];
    });
    props.setSelectedIds([...props.selectedIds, station.id]);
  }

  const visibleLangs = props.languages.filter((l) => {
    const q = langSearch.toLowerCase();
    return !q || l.nameEnglish.toLowerCase().includes(q) || l.nameNative.toLowerCase().includes(q) || l.code.includes(q);
  });

  // Pre-country-filter pass — used to populate the country dropdown
  const preCountryFiltered = props.stations.filter(
    (s) =>
      (langFilter === "all" || s.languageCode === langFilter) &&
      (genre === "all" || s.genre.text === genre) &&
      `${s.name} ${s.location.cityName}`.toLowerCase().includes(stationQuery.toLowerCase()),
  );
  const availableCountries = Array.from(new Set(preCountryFiltered.map((s) => s.location.countryName)))
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));

  const filtered = countryFilter === "all"
    ? preCountryFiltered
    : preCountryFiltered.filter((s) => s.location.countryName === countryFilter);

  const countries = groupBy(filtered, (s) => s.location.countryName);
  const FREQUENCY_RE = /^[\d.]+\s*(FM|AM|MHz|kHz|kbps)?$/i;
  const genres = Array.from(new Set(props.stations.map((s) => s.genre.text)))
    .filter(Boolean)
    .filter((g) => !FREQUENCY_RE.test(g))
    .sort();

  async function loadMore(countryName: string) {
    const offset = (countryOffsets[countryName] || 0) + LOAD_MORE_LIMIT;
    setLoadingMore((p) => ({ ...p, [countryName]: true }));
    try {
      const more = await api.countryStations(countryName, offset, LOAD_MORE_LIMIT);
      props.setStations((prev) => {
        const byId = new Map(prev.map((s) => [s.id, s]));
        more.forEach((s) => { if (!byId.has(s.id)) byId.set(s.id, s); });
        return Array.from(byId.values());
      });
      setCountryOffsets((p) => ({ ...p, [countryName]: offset }));
      setCountryHasMore((p) => ({ ...p, [countryName]: more.length >= LOAD_MORE_LIMIT }));
    } catch {
      setCountryHasMore((p) => ({ ...p, [countryName]: false }));
    } finally {
      setLoadingMore((p) => ({ ...p, [countryName]: false }));
    }
  }

  return (
    <main>
      <section className="band">
        <h1>Discovery</h1>

        {/* Language panel */}
        {props.languagePanelOpen ? (
          <>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
              <input
                placeholder="Search languages…"
                value={langSearch}
                onChange={(e) => setLangSearch(e.target.value)}
                style={{ flex: 1, margin: 0 }}
              />
              <button className="primary" disabled={!props.activeCodes.length} onClick={props.loadStations} style={{ flexShrink: 0 }}>
                Load stations
              </button>
            </div>
            <div className="language-grid-wrapper">
              <div className="language-grid">
                {visibleLangs.map((lang) => {
                  const profile = props.profiles.find((p) => p.code === lang.code);
                  const selected = props.activeCodes.includes(lang.code);
                  return (
                    <button
                      key={lang.code}
                      className={`language ${selected ? "selected" : ""}`}
                      onClick={() => props.toggleLanguage(lang.code)}
                    >
                      <strong>{lang.nameEnglish}</strong>
                      <span>{lang.nameNative} · {lang.code.toUpperCase()}</span>
                      <small>
                        {lang.stationCount.toLocaleString()} stations ·{" "}
                        {profile ? "✓ Whisper" : "⟳ Auto-detect"} ·{" "}
                        {profile?.lemmaSupported ? "Full lemma" : "Exact/fuzzy only"}
                      </small>
                    </button>
                  );
                })}
                {visibleLangs.length === 0 && <p style={{ color: "#9aa7b5" }}>No languages match "{langSearch}"</p>}
              </div>
            </div>
            {props.activeCodes.length > 5 && (
              <p className="warning">Fetching more than 5 languages at once may be slow.</p>
            )}
          </>
        ) : (
          <div className="lang-collapse">
            <span>Active languages: {props.activeCodes.map((c) => <b className="pill" key={c}>{c.toUpperCase()}</b>)}</span>
            <button onClick={() => props.setLanguagePanelOpen(true)}>Edit languages</button>
          </div>
        )}
        <CustomStreamForm onAdd={addCustomStation} ytDlpAvailable={props.ytDlpAvailable} />
      </section>

      {/* Search + filters */}
      {props.stations.length > 0 && (
        <>
          <section className="tools" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <Search size={18} />
              <input placeholder="Search station or city" value={stationQuery} onChange={(e) => setStationQuery(e.target.value)} style={{ flex: 1, minWidth: 160 }} />
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span className="filter-label">Language</span>
                <ChipRow values={["all", ...props.activeCodes]} current={langFilter} onChange={(v) => { setLangFilter(v); setCountryFilter("all"); }} />
              </div>
            </div>
            {(genres.length > 0 || availableCountries.length > 0) && (
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                {genres.length > 0 && (
                  <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                    <span className="filter-label">Genre</span>
                    <ChipRow values={["all", ...genres.slice(0, 15)]} current={genre} onChange={(v) => { setGenre(v); setCountryFilter("all"); }} />
                  </div>
                )}
                {availableCountries.length > 0 && (
                  <div className="country-select-wrap">
                    <select value={countryFilter} onChange={(e) => setCountryFilter(e.target.value)} style={{ width: "auto", minWidth: 160 }}>
                      <option value="all">All countries ({availableCountries.length})</option>
                      {availableCountries.map((c) => {
                        const count = preCountryFiltered.filter((s) => s.location.countryName === c).length;
                        return <option key={c} value={c}>{c} ({count})</option>;
                      })}
                    </select>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Country panels */}
          {Object.entries(countries)
            .sort((a, b) => b[1].length - a[1].length)
            .map(([country, rows]) => {
              const selCount = rows.filter((s) => props.selectedIds.includes(s.id)).length;
              const byLang = groupBy(rows, (s) => s.languageCode || "?");
              const langBreakdown = Object.entries(byLang).map(([c, ss]) => `${ss.length} ${c.toUpperCase()}`).join(" · ");
              const hasMore = countryHasMore[country] !== false;

              return (
                <details className="country" key={country} open>
                  <summary>
                    <strong>{country}</strong>
                    <span>{rows.length} stations · {langBreakdown} · {selCount} selected</span>
                    <button onClick={(e) => {
                      e.preventDefault();
                      props.setSelectedIds([...new Set([...props.selectedIds, ...rows.filter((s) => s.streams.length).map((s) => s.id)])]);
                    }}>Select all</button>
                    <button onClick={(e) => {
                      e.preventDefault();
                      const ids = new Set(rows.map((s) => s.id));
                      props.setSelectedIds(props.selectedIds.filter((id) => !ids.has(id)));
                    }}>Deselect all</button>
                  </summary>
                  <div className="station-grid">
                    {rows.map((s) => (
                      <StationCard key={s.id} station={s} selected={props.selectedIds.includes(s.id)}
                        toggle={() => props.setSelectedIds(
                          props.selectedIds.includes(s.id)
                            ? props.selectedIds.filter((id) => id !== s.id)
                            : [...props.selectedIds, s.id],
                        )}
                        onDetail={() => props.setDrawerStation(s)}
                      />
                    ))}
                  </div>
                  {hasMore && (
                    <div style={{ padding: "8px 0" }}>
                      <button disabled={loadingMore[country]} onClick={() => loadMore(country)} style={{ fontSize: 13 }}>
                        {loadingMore[country] ? "Loading…" : "Load more"}
                      </button>
                    </div>
                  )}
                </details>
              );
            })}
        </>
      )}

      {/* Station detail drawer */}
      {props.drawerStation && (
        <>
          <div className="drawer-overlay" onClick={() => props.setDrawerStation(null)} />
          <StationDrawer
            station={props.drawerStation}
            selected={props.selectedIds.includes(props.drawerStation.id)}
            toggle={() => {
              const s = props.drawerStation!;
              if (!s.streams.length) return;
              props.setSelectedIds(
                props.selectedIds.includes(s.id)
                  ? props.selectedIds.filter((id) => id !== s.id)
                  : [...props.selectedIds, s.id],
              );
            }}
            onClose={() => props.setDrawerStation(null)}
          />
        </>
      )}
    </main>
  );
}

// ── Station Card ──────────────────────────────────────────────────────────────
function StationCard({ station: s, selected, toggle, onDetail }: {
  station: Station; selected: boolean; toggle: () => void; onDetail: () => void;
}) {
  const disabled = s.streams.length === 0;
  const isCustom = s.id.startsWith("custom-");
  return (
    <article className={`card station ${selected ? "selected" : ""} ${disabled ? "disabled" : ""}`}
      onClick={() => !disabled && toggle()}>
      <div>
        <b>{s.name}</b>
        <span className="pill">{s.languageCode ? s.languageCode.toUpperCase() : "?"}</span>
        {isCustom && <span className="badge info" style={{ marginLeft: 4 }}>Custom</span>}
      </div>
      <p>{s.location.cityName || s.location.countryName || "Custom"} · {s.genre.text}</p>
      <small>
        {disabled ? "No stream available"
          : isCustom ? s.streams[0].url.slice(0, 50) + (s.streams[0].url.length > 50 ? "…" : "")
          : `${s.streams[0].format.toUpperCase()} · ${s.streams[0].bitrate || "?"} kbps`}
        {!s.languageCode && <span className="badge warn" style={{ marginLeft: 6 }}>Language unverified</span>}
      </small>
      <button style={{ marginTop: 6, fontSize: 12 }} onClick={(e) => { e.stopPropagation(); onDetail(); }}>
        Details
      </button>
    </article>
  );
}

// ── Station Drawer ────────────────────────────────────────────────────────────
function StationDrawer({ station: s, selected, toggle, onClose }: {
  station: Station; selected: boolean; toggle: () => void; onClose: () => void;
}) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  return (
    <div className="drawer">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>{s.name}</h2>
        <button onClick={onClose}><X size={18} /></button>
      </div>
      <table>
        <tbody>
          <tr><td>Country</td><td>{s.location.countryName} ({s.location.countryCode})</td></tr>
          <tr><td>City / State</td><td>{s.location.cityName || "—"}</td></tr>
          <tr><td>Genre</td><td>{s.genre.text}</td></tr>
          <tr><td>Language</td><td>{s.languageCode ? s.languageCode.toUpperCase() : "Unverified"}</td></tr>
          <tr><td>Votes</td><td>{s.popularity.global > 0 ? s.popularity.global.toLocaleString() : "—"}</td></tr>
        </tbody>
      </table>
      <details>
        <summary style={{ cursor: "pointer", fontSize: 12, color: "#aeaeb2", userSelect: "none", marginTop: 4 }}>Technical details</summary>
        <p style={{ fontSize: 11, color: "#aeaeb2", wordBreak: "break-all", margin: "6px 0 0", fontFamily: "monospace" }}>UUID: {s.id}</p>
      </details>
      <h2 style={{ fontSize: 15 }}>Streams ({s.streams.length})</h2>
      {s.streams.length === 0 && <p style={{ color: "#9aa7b5" }}>No stream URLs available.</p>}
      {s.streams.map((st, i) => (
        <div key={i} className="stream-row">
          <span className="badge info">{st.format.toUpperCase()}</span>
          <span className="badge info">{st.bitrate || "?"} kbps</span>
          {st.isHttps && <span className="badge ok">HTTPS</span>}
          <a href={st.url} target="_blank" rel="noopener noreferrer" style={{ flex: 1, fontSize: 11 }}>
            {st.url.length > 50 ? st.url.slice(0, 50) + "…" : st.url}
          </a>
          <button style={{ fontSize: 12 }} onClick={() => setPreviewUrl(previewUrl === st.url ? null : st.url)}>
            {previewUrl === st.url ? "Stop" : "Preview"}
          </button>
        </div>
      ))}
      {previewUrl && <audio controls autoPlay src={previewUrl} style={{ width: "100%", marginTop: 8 }} />}
      <button className={selected ? "" : "primary"} disabled={s.streams.length === 0} onClick={toggle}
        style={{ marginTop: "auto" }}>
        {selected ? "Remove from monitor" : "Add to monitor"}
      </button>
    </div>
  );
}

// ── Monitor ───────────────────────────────────────────────────────────────────
function Monitor({ selectedStations, status, wsConnected, startMonitoring, setSelectedIds, activeCodes }: {
  selectedStations: Station[]; status: BackendStatus | null; wsConnected: boolean;
  startMonitoring: (stations?: Station[]) => void; setSelectedIds: (ids: string[]) => void;
  activeCodes: string[];
}) {
  const [langFilter, setLangFilter] = useState("all");
  const [listeningId, setListeningId] = useState<string | null>(null);
  const statusById = new Map((status?.stationStatuses || []).map((s) => [s.stationId, s]));
  const runningIds = new Set((status?.stationStatuses || []).map((s) => s.stationId));
  const allRunning = selectedStations.length > 0 && selectedStations.every((s) => runningIds.has(s.id));
  const visible = selectedStations.filter((s) => langFilter === "all" || s.languageCode === langFilter);

  return (
    <main>
      <section className="band">
        <h1>Monitor</h1>
        {!wsConnected && (
          <div style={{ background: "#f5f7f9", borderRadius: 8, padding: 16, marginBottom: 14 }}>
            <p style={{ margin: "0 0 8px", fontWeight: 600 }}>Backend not connected</p>
            <p style={{ margin: "0 0 10px", color: "#526074", fontSize: 14 }}>Start the backend with:</p>
            <pre style={{ margin: 0 }}>uvicorn app.main:app --reload --port 8000</pre>
            <p style={{ margin: "8px 0 0", color: "#526074", fontSize: 13 }}>Retrying automatically every 5 s…</p>
          </div>
        )}
        <div className="summary">
          <span>{status?.activeSlots || 0} active streams</span>
          <span>{status?.totalChunksProcessed || 0} chunks</span>
          <span>{status?.totalMatchesSession || 0} matches</span>
          <span>{status?.totalClipsSaved || 0} clips</span>
          {status && <span>{status.diskFreeMB.toLocaleString()} MB free</span>}
        </div>
        <div className="actions">
          <button className="primary" disabled={!selectedStations.length || allRunning} onClick={() => startMonitoring()}>
            <Play size={17} /> {allRunning ? "Monitoring active" : "Start monitoring"}
          </button>
          <button onClick={() => api.stopAll().catch(() => {})}><Square size={17} /> Stop all</button>
        </div>
        {activeCodes.length > 1 && (
          <ChipRow values={["all", ...activeCodes]} current={langFilter} onChange={setLangFilter} />
        )}
      </section>

      <section className="monitor-grid">
        {visible.map((station) => {
          const live = statusById.get(station.id);
          const isRunning = runningIds.has(station.id);
          const isListening = listeningId === station.id;
          const streamUrl = station.streams[0]?.url ?? null;
          return (
            <article className={`card monitor ${isListening ? "listening" : ""}`} key={station.id}>
              <div>
                <b>{station.name}</b>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  {isListening && <span className="live-badge"><span className="live-dot" />LIVE</span>}
                  <span className="pill">{station.languageCode.toUpperCase()}</span>
                </div>
              </div>
              <p>
                <span className={`dot ${live?.status || ""}`} />{" "}
                {live?.status || "idle"}{live?.errorMessage ? ` · ${live.errorMessage}` : ""}
              </p>
              {live && (
                <div className="monitor-meta">
                  <span>⏱ {formatUptime(live.uptimeSeconds)}</span>
                  {live.alertCount > 0 && (
                    <span className="badge alert">🔔 {live.alertCount} alert{live.alertCount !== 1 ? "s" : ""}</span>
                  )}
                </div>
              )}
              <p className="transcript" dir="auto">
                {highlight(live?.lastTranscriptSnippet || "Waiting for transcript…", live?.matchedKeywordsInSnippet || [])}
              </p>
              {live?.lastTranscriptAt && (
                <p className="transcript-age">
                  Transcript from {formatTranscriptAge(live.lastTranscriptAt)} ago
                  {isListening && " · live audio is real-time"}
                </p>
              )}
              <div className="timeline">
                {(live?.chunkHistory || Array(10).fill("pending")).map((state, i) => <span key={i} className={state} />)}
              </div>
              {isListening && streamUrl && (
                <audio
                  key={streamUrl}
                  autoPlay
                  controls
                  src={streamUrl}
                  className="station-audio"
                  onError={() => setListeningId(null)}
                />
              )}
              <div className="actions" style={{ marginTop: 8 }}>
                {!isRunning ? (
                  <button className="primary" style={{ fontSize: 13 }} onClick={() => startMonitoring([station])}>
                    <Play size={14} /> Start
                  </button>
                ) : live?.status === "paused" ? (
                  <button style={{ fontSize: 13 }} onClick={() => api.resume(station.id).catch(() => {})}>
                    <Play size={14} /> Resume
                  </button>
                ) : (
                  <button style={{ fontSize: 13 }} onClick={() => api.pause(station.id).catch(() => {})}>
                    <Pause size={14} /> Pause
                  </button>
                )}
                {streamUrl && (
                  <button
                    className={isListening ? "listen-btn active" : "listen-btn"}
                    style={{ fontSize: 13 }}
                    onClick={() => setListeningId(isListening ? null : station.id)}
                    title={isListening ? "Stop listening" : "Listen live"}
                  >
                    {isListening ? <VolumeX size={14} /> : <Volume2 size={14} />}
                    {isListening ? "Mute" : "Listen"}
                  </button>
                )}
                <button className="remove-btn" style={{ fontSize: 13 }} onClick={() => {
                  api.stopStation(station.id).catch(() => {});
                  if (isListening) setListeningId(null);
                  setSelectedIds(selectedStations.filter((s) => s.id !== station.id).map((s) => s.id));
                }}><X size={14} /> Remove</button>
              </div>
            </article>
          );
        })}
      </section>
    </main>
  );
}

// ── Keywords ──────────────────────────────────────────────────────────────────
function Keywords({ keywords, setKeywords, addKeywords, activeCodes, profiles }: {
  keywords: KeywordConfig; setKeywords: (v: KeywordConfig) => void;
  addKeywords: (values: string[]) => void; activeCodes: string[]; profiles: LanguageProfile[];
}) {
  const [entry, setEntry] = useState("");
  const [presetName, setPresetName] = useState("");
  const [savedPresets, setSavedPresets] = useState<Record<string, string[]>>(() => {
    try { return JSON.parse(localStorage.getItem("radiowatch-presets") || "{}"); }
    catch { return {}; }
  });

  function commit() { addKeywords(entry.split("\n")); setEntry(""); }
  const update = (next: KeywordConfig) => { setKeywords(next); api.patchKeywords(next).catch(() => {}); };

  function savePreset() {
    if (!presetName.trim() || !keywords.keywords.length) return;
    const next = { ...savedPresets, [presetName.trim()]: keywords.keywords.map((k) => k.text) };
    setSavedPresets(next);
    localStorage.setItem("radiowatch-presets", JSON.stringify(next));
    setPresetName("");
  }

  function deletePreset(name: string) {
    const { [name]: _, ...next } = savedPresets;
    setSavedPresets(next);
    localStorage.setItem("radiowatch-presets", JSON.stringify(next));
  }

  return (
    <main>
      <section className="band">
        <h1>Keywords</h1>
        <div className="key-row">
          <textarea placeholder="Add one keyword or paste a newline-separated list" value={entry}
            onChange={(e) => setEntry(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commit(); } }} />
          <button onClick={commit}>Add</button>
        </div>
        <div className="tags">
          {keywords.keywords.map((kw) => (
            <button key={kw.id} onClick={() => update({ ...keywords, keywords: keywords.keywords.filter((k) => k.id !== kw.id) })}>
              {kw.text} <X size={14} />
            </button>
          ))}
        </div>
        <div className="segmented">
          {(["exact", "lemma", "fuzzy"] as const).map((mode) => (
            <button key={mode} className={keywords.matchMode === mode ? "active" : ""} onClick={() => update({ ...keywords, matchMode: mode })}>{mode}</button>
          ))}
        </div>
        {keywords.matchMode === "fuzzy" && (
          <label>Threshold <input type="range" min="50" max="100" value={keywords.fuzzyThreshold}
            onChange={(e) => update({ ...keywords, fuzzyThreshold: Number(e.target.value) })} /> {keywords.fuzzyThreshold}</label>
        )}
        {keywords.matchMode === "lemma" && <Coverage profiles={profiles.filter((p) => activeCodes.includes(p.code))} showInstall />}

        <div className="save-preset-row">
          <input
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            placeholder="Preset name…"
            onKeyDown={(e) => { if (e.key === "Enter") savePreset(); }}
            style={{ maxWidth: 240 }}
          />
          <button disabled={!presetName.trim() || !keywords.keywords.length} onClick={savePreset}>
            Save as preset
          </button>
        </div>
      </section>

      {Object.keys(savedPresets).length > 0 ? (
        <section className="preset-grid">
          {Object.entries(savedPresets).map(([name, values]) => (
            <article className="card" key={name}>
              <b>{name}</b>
              <p style={{ color: "#627084", fontSize: 13 }}>{values.join(", ")}</p>
              <div className="actions">
                <button onClick={() => addKeywords(values)}>Load</button>
                <button className="remove-btn" onClick={() => deletePreset(name)}>Delete</button>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <p style={{ textAlign: "center", color: "#9aa7b5", padding: "28px 0", fontSize: 14 }}>
          No saved presets yet — add keywords above and click "Save as preset".
        </p>
      )}
    </main>
  );
}

// ── Pipeline ──────────────────────────────────────────────────────────────────
function Pipeline({ pipeline, setPipeline, selectedStations, keywords, activeProfiles, allProfiles, ffmpegAvailable, ytDlpAvailable }: {
  pipeline: PipelineConfig; setPipeline: (v: PipelineConfig) => void;
  selectedStations: Station[]; keywords: KeywordConfig;
  activeProfiles: LanguageProfile[]; allProfiles: LanguageProfile[];
  ffmpegAvailable: boolean; ytDlpAvailable: boolean;
}) {
  const script = useMemo(() => generateScript(pipeline, selectedStations, keywords, activeProfiles),
    [pipeline, selectedStations, keywords, activeProfiles]);
  const runInstructions = useMemo(() => buildRunInstructions(activeProfiles), [activeProfiles]);
  const update = (patch: Partial<PipelineConfig>) => {
    const next = { ...pipeline, ...patch }; setPipeline(next); api.patchPipeline(next).catch(() => {});
  };

  return (
    <main>
      <section className="settings-grid">
        <Panel title="Transcription">
          <Select label="Whisper model" value={pipeline.whisperModel} values={["large-v3", "turbo", "medium", "small", "tiny"]} onChange={(v) => update({ whisperModel: v as PipelineConfig["whisperModel"] })} />
          <Select label="Device" value={pipeline.device} values={["auto", "cpu", "cuda", "mps"]} onChange={(v) => update({ device: v as PipelineConfig["device"] })} />
          <Select label="Compute type" value={pipeline.computeType} values={["auto", "float16", "int8"]} onChange={(v) => update({ computeType: v as PipelineConfig["computeType"] })} />
          <Select label="Language hint" value={pipeline.languageHintMode} values={["per-station", "auto-detect", "manual"]} onChange={(v) => update({ languageHintMode: v as PipelineConfig["languageHintMode"] })} />
          {pipeline.languageHintMode === "manual" && (
            <TextInput label="Language code (e.g. es)" value={pipeline.manualLanguageCode} onChange={(v) => update({ manualLanguageCode: v })} />
          )}
        </Panel>
        <Panel title="Capture">
          <NumberInput label="Chunk seconds" value={pipeline.chunkSeconds} min={10} max={120} onChange={(v) => update({ chunkSeconds: v })} />
          <NumberInput label="Pre-buffer seconds" value={pipeline.preBufferSeconds} min={5} max={120} onChange={(v) => update({ preBufferSeconds: v })} />
          <NumberInput label="Post-buffer seconds" value={pipeline.postBufferSeconds} min={10} max={120} onChange={(v) => update({ postBufferSeconds: v })} />
        </Panel>
        <Panel title="Output">
          <Select label="Format" value={pipeline.outputFormat} values={["wav", "mp3", "ogg"]} onChange={(v) => update({ outputFormat: v as PipelineConfig["outputFormat"] })} />
          <TextInput label="Output directory" value={pipeline.outputDirectory} onChange={(v) => update({ outputDirectory: v })} />
          <TextInput label="Transcript directory" value={pipeline.transcriptLogDirectory} onChange={(v) => update({ transcriptLogDirectory: v })} />
        </Panel>
        <Panel title="Language models">
          <Coverage profiles={allProfiles} activeCodes={new Set(activeProfiles.map((p) => p.code))} showInstall />
        </Panel>
        <Panel title="Dependencies">
          <table style={{ fontSize: 13, borderCollapse: "collapse", width: "100%" }}>
            <tbody>
              <tr>
                <td style={{ padding: "4px 0", fontWeight: 600 }}>ffmpeg</td>
                <td style={{ padding: "4px 8px" }}>
                  {ffmpegAvailable
                    ? <span className="badge ok">Installed</span>
                    : <span className="badge warn">Not found</span>}
                </td>
                <td style={{ padding: "4px 0", fontSize: 12, color: "#627084" }}>
                  {ffmpegAvailable ? "All stream capture works." : "Required for all stream capture. Install via brew install ffmpeg or your package manager."}
                </td>
              </tr>
              <tr>
                <td style={{ padding: "4px 0", fontWeight: 600 }}>yt-dlp</td>
                <td style={{ padding: "4px 8px" }}>
                  {ytDlpAvailable
                    ? <span className="badge ok">Installed</span>
                    : <span className="badge warn">Not found</span>}
                </td>
                <td style={{ padding: "4px 0", fontSize: 12, color: "#627084" }}>
                  {ytDlpAvailable
                    ? "YouTube, Twitch, and similar platform streams are supported."
                    : "Optional. Enables YouTube, Twitch, and other platform streams. Install with: pip install yt-dlp"}
                </td>
              </tr>
              <tr>
                <td style={{ padding: "4px 0", fontWeight: 600 }}>spaCy</td>
                <td style={{ padding: "4px 8px" }}><span className="badge ok">Installed</span></td>
                <td style={{ padding: "4px 0", fontSize: 12, color: "#627084" }}>Lemma matching. Install language models in the Language models panel above.</td>
              </tr>
            </tbody>
          </table>
        </Panel>
      </section>
      <details className="run-instructions band">
        <summary>Run instructions &amp; dependency install</summary>
        <pre>{runInstructions}</pre>
      </details>
      <section className="band">
        <h1>Generated Python script</h1>
        <div className="actions">
          <button onClick={() => navigator.clipboard.writeText(script)}>Copy</button>
          <button onClick={() => download("radiowatch_monitor.py", script)}><Download size={16} /> Download</button>
        </div>
        <pre>{script}</pre>
      </section>
    </main>
  );
}

// ── Alerts ────────────────────────────────────────────────────────────────────
function Alerts({ alerts, setAlerts, activeCodes, deleteConfirmId, setDeleteConfirmId }: {
  alerts: Alert[]; setAlerts: (rows: Alert[]) => void; activeCodes: string[];
  deleteConfirmId: string | null; setDeleteConfirmId: (id: string | null) => void;
}) {
  const [langFilter, setLangFilter] = useState("all");
  const [stationFilter, setStationFilter] = useState("all");
  const [keywordFilter, setKeywordFilter] = useState("");
  const [reviewedFilter, setReviewedFilter] = useState<"all" | "reviewed" | "unreviewed">("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [selectedAlertIds, setSelectedAlertIds] = useState<string[]>([]);
  const PAGE_SIZE = 50;

  const stationNames = Array.from(new Set(alerts.map((a) => a.stationName)));
  const rows = alerts.filter((a) => {
    if (langFilter !== "all" && a.languageCode !== langFilter) return false;
    if (stationFilter !== "all" && a.stationName !== stationFilter) return false;
    if (keywordFilter && !a.matchedKeyword.toLowerCase().includes(keywordFilter.toLowerCase())) return false;
    if (reviewedFilter === "reviewed" && !a.reviewed) return false;
    if (reviewedFilter === "unreviewed" && a.reviewed) return false;
    if (dateFrom && new Date(a.detectedAt) < new Date(dateFrom)) return false;
    if (dateTo && new Date(a.detectedAt) > new Date(dateTo + "T23:59:59")) return false;
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  async function refresh() { setAlerts(await api.alerts().catch(() => alerts)); }

  return (
    <main>
      <section className="band">
        <h1>Alerts</h1>
        <div className="filter-bar">
          <ChipRow values={["all", ...activeCodes]} current={langFilter} onChange={(v) => { setLangFilter(v); setPage(1); }} />
          <label>Station
            <select value={stationFilter} onChange={(e) => { setStationFilter(e.target.value); setPage(1); }}>
              <option value="all">All stations</option>
              {stationNames.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label>Keyword
            <input placeholder="filter…" value={keywordFilter}
              onChange={(e) => { setKeywordFilter(e.target.value); setPage(1); }} style={{ width: 130 }} />
          </label>
          <label>Status
            <select value={reviewedFilter} onChange={(e) => { setReviewedFilter(e.target.value as typeof reviewedFilter); setPage(1); }}>
              <option value="all">All</option>
              <option value="unreviewed">Unreviewed</option>
              <option value="reviewed">Reviewed</option>
            </select>
          </label>
          <label>From <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} style={{ width: 140 }} /></label>
          <label>To   <input type="date" value={dateTo}   onChange={(e) => { setDateTo(e.target.value); setPage(1); }} style={{ width: 140 }} /></label>
        </div>
        <div className="actions">
          <span style={{ color: "#627084", fontSize: 14 }}>{rows.length} alert{rows.length !== 1 ? "s" : ""}</span>
          <button onClick={() => window.open(api.exportAlerts(selectedAlertIds.length ? selectedAlertIds : rows.map((a) => a.id)), "_blank")}>
            <Download size={15} /> {selectedAlertIds.length ? `Export ${selectedAlertIds.length} selected` : "Export all filtered"}
          </button>
          {selectedAlertIds.length > 0 && <button onClick={() => setSelectedAlertIds([])}>Clear selection</button>}
        </div>
      </section>

      <section className="alert-list">
        {pageRows.map((alert) => (
          <article className="card alert" key={alert.id}>
            <div>
              <div className="check-row">
                <input type="checkbox" checked={selectedAlertIds.includes(alert.id)}
                  onChange={() => setSelectedAlertIds((p) => p.includes(alert.id) ? p.filter((x) => x !== alert.id) : [...p, alert.id])} />
                <b>{new Date(alert.detectedAt).toLocaleString()}</b>
              </div>
              <span className="pill">{alert.languageCode.toUpperCase()}</span>
              <span>{alert.stationName}</span>
              {alert.reviewed && <span className="badge ok">Reviewed</span>}
            </div>
            <p dir="auto">{highlight(alert.transcriptSnippet, [alert.matchedKeyword])}</p>
            <small>
              Keyword: <b>{alert.matchedKeyword}</b> · {alert.matchMode}
              {alert.spaCyModelUsed && ` · ${alert.spaCyModelUsed}`} ·{" "}
              {alert.clipExists
                ? <span className="badge ok">Clip ready · {alert.clipDurationSeconds}s</span>
                : <span className="badge warn">File missing</span>}
            </small>
            {alert.clipExists && <audio controls src={api.clipUrl(alert.id)} style={{ width: "100%", marginTop: 6 }} />}
            <div className="actions" style={{ marginTop: 8 }}>
              {alert.clipExists && (
                <a href={api.clipUrl(alert.id)} download={`${alert.stationName}_${alert.matchedKeyword}.wav`}>
                  <button style={{ fontSize: 13 }}><Download size={14} /> Clip</button>
                </a>
              )}
              <button style={{ fontSize: 13 }} onClick={() => window.open(api.exportAlerts([alert.id]), "_blank")}>
                <Download size={14} /> ZIP
              </button>
              <button style={{ fontSize: 13 }} onClick={async () => { await api.markAlert(alert.id, !alert.reviewed).catch(() => {}); refresh(); }}>
                {alert.reviewed ? "Mark unreviewed" : "Mark reviewed"}
              </button>
              <button style={{ fontSize: 13 }} onClick={() => setDeleteConfirmId(alert.id)}>
                <Trash2 size={14} /> Delete
              </button>
            </div>
          </article>
        ))}
        {pageRows.length === 0 && (
          <p style={{ textAlign: "center", color: "#9aa7b5", padding: 32 }}>No alerts match the current filters.</p>
        )}
      </section>

      {totalPages > 1 && (
        <div className="pagination">
          <button disabled={page === 1} onClick={() => setPage(page - 1)}>← Prev</button>
          <span>Page {page} of {totalPages}</span>
          <button disabled={page === totalPages} onClick={() => setPage(page + 1)}>Next →</button>
        </div>
      )}
    </main>
  );
}

// ── Coverage table ────────────────────────────────────────────────────────────
type InstallState = "idle" | "loading" | "done" | "error";

function InstallButton({ model }: { model: string }) {
  const [state, setState] = useState<InstallState>("idle");
  const [errMsg, setErrMsg] = useState("");

  async function handleInstall() {
    setState("loading");
    try {
      await api.installSpacy(model);
      setState("done");
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "Install failed");
      setState("error");
    }
  }

  if (state === "done") return <span className="badge ok">Installed</span>;
  if (state === "error") return <span className="badge warn" title={errMsg}>Failed</span>;

  return (
    <button
      className="install-btn"
      disabled={state === "loading"}
      onClick={handleInstall}
    >
      {state === "loading" ? "Installing…" : "Install"}
    </button>
  );
}

function Coverage({ profiles, activeCodes, showInstall }: {
  profiles: LanguageProfile[]; activeCodes?: Set<string>; showInstall?: boolean;
}) {
  if (!profiles.length) return <p style={{ color: "#9aa7b5", margin: 0 }}>No languages available.</p>;
  return (
    <table className="coverage-table"><tbody>
      {profiles.map((p) => {
        const isActive = activeCodes ? activeCodes.has(p.code) : true;
        return (
          <tr key={p.code} className={isActive ? "" : "coverage-inactive"}>
            <td className="coverage-lang">{p.code.toUpperCase()}</td>
            <td className="coverage-model">{p.spaCyModel || <em style={{ color: "#9aa7b5" }}>No model</em>}</td>
            <td>{p.lemmaSupported ? <span className="badge ok">Lemma</span> : <span className="badge warn">Exact</span>}</td>
            {showInstall && <td>{p.spaCyModel ? <InstallButton model={p.spaCyModel} /> : null}</td>}
          </tr>
        );
      })}
    </tbody></table>
  );
}

// ── Shared small components ───────────────────────────────────────────────────
function ChipRow({ values, current, onChange }: { values: string[]; current: string; onChange: (v: string) => void }) {
  return (
    <div className="chips">
      {values.map((v) => (
        <button key={v} className={current === v ? "selected" : ""} onClick={() => onChange(v)}>
          {v === "all" ? "All" : v.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="card panel"><h2>{title}</h2>{children}</section>;
}
function Select({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (v: string) => void }) {
  return <label>{label}<select value={value} onChange={(e) => onChange(e.target.value)}>{values.map((v) => <option key={v}>{v}</option>)}</select></label>;
}
function NumberInput({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (v: number) => void }) {
  return <label>{label}<input type="number" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} /></label>;
}
function TextInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return <label>{label}<input value={value} onChange={(e) => onChange(e.target.value)} /></label>;
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function groupBy<T>(rows: T[], key: (row: T) => string): Record<string, T[]> {
  return rows.reduce<Record<string, T[]>>((acc, row) => {
    const g = key(row); acc[g] = [...(acc[g] || []), row]; return acc;
  }, {});
}

function highlight(text: string, words: string[]): React.ReactNode[] {
  let parts: Array<string | React.ReactElement> = [text];
  words.filter(Boolean).forEach((word) => {
    parts = parts.flatMap((part) => {
      if (typeof part !== "string") return [part];
      const pieces = part.split(new RegExp(`(${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
      return pieces.map((piece, i) => i % 2 === 1 ? <mark key={`${word}-${i}`}>{piece}</mark> : piece);
    });
  });
  return parts;
}

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
}

function formatTranscriptAge(iso: string): string {
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function buildRunInstructions(profiles: LanguageProfile[]): string {
  const spaCyLines = profiles.filter((p) => p.spaCyInstallCommand).map((p) => p.spaCyInstallCommand!).join("\n");
  return `# Install Python dependencies
pip install faster-whisper rapidfuzz spacy

# Download spaCy models for your active languages
${spaCyLines || "# (no lemma-capable languages selected)"}

# Run the exported script
python radiowatch_monitor.py`;
}

// ── Standalone script generator ───────────────────────────────────────────────
function generateScript(pipeline: PipelineConfig, stations: Station[], keywords: KeywordConfig, profiles: LanguageProfile[]): string {
  const profileMap = Object.fromEntries(profiles.map((p) => [p.code, { whisper: p.whisperCode, spacy: p.spaCyModel }]));
  const monitorJob = {
    stations: stations.map((s) => ({
      id: s.id, name: s.name, slug: s.slug,
      countryName: s.location.countryName, countryCode: s.location.countryCode,
      languageCode: s.languageCode, streamUrls: s.streams.map((st) => st.url),
    })),
    keywordConfig: keywords,
    pipelineConfig: pipeline,
  };

  return `#!/usr/bin/env python3
"""Standalone RadioWatch monitor — exported from the browser UI.

Captures streams with ffmpeg, transcribes with faster-whisper,
matches keywords (exact / lemma / fuzzy), and writes alerts to a JSONL file.
Stations sourced from Radio Browser (https://api.radio-browser.info/).

${buildRunInstructions(profiles)}
"""

import json
import shutil
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from faster_whisper import WhisperModel
from rapidfuzz import fuzz

LANGUAGE_PROFILES = ${JSON.stringify(profileMap, null, 2)}

MONITOR_JOB = ${JSON.stringify(monitorJob, null, 2)}

STATIONS = MONITOR_JOB["stations"]
KEYWORDS = MONITOR_JOB["keywordConfig"]
PIPELINE = MONITOR_JOB["pipelineConfig"]


def _load_spacy_models():
    nlp = {}
    for lang_code, profile in LANGUAGE_PROFILES.items():
        model_name = profile.get("spacy")
        if not model_name:
            continue
        try:
            import spacy  # noqa: PLC0415
            nlp[lang_code] = spacy.load(model_name)
        except (ImportError, OSError):
            nlp[lang_code] = None
    return nlp


NLP_MODELS = _load_spacy_models()


def transcribe(model, path, language_code):
    language = None
    if PIPELINE["languageHintMode"] == "per-station":
        profile = LANGUAGE_PROFILES.get(language_code, {})
        language = profile.get("whisper") or language_code or None
    elif PIPELINE["languageHintMode"] == "manual":
        language = PIPELINE.get("manualLanguageCode") or None
    segments, _info = model.transcribe(str(path), language=language)
    return " ".join(s.text.strip() for s in segments).strip()


def find_matches(text, language_code):
    text_lower = text.lower()
    found = []
    mode = KEYWORDS["matchMode"]
    if mode == "fuzzy":
        threshold = KEYWORDS.get("fuzzyThreshold", 80)
        for kw in KEYWORDS["keywords"]:
            if fuzz.partial_ratio(kw["text"].lower(), text_lower) >= threshold:
                found.append(kw["text"])
        return found, "fuzzy"
    if mode == "lemma":
        nlp = NLP_MODELS.get(language_code)
        if nlp:
            doc = nlp(text)
            lemmas = {t.lemma_.lower() for t in doc}
            for kw in KEYWORDS["keywords"]:
                kw_lemmas = {t.lemma_.lower() for t in nlp(kw["text"].lower())}
                if kw_lemmas & lemmas:
                    found.append(kw["text"])
            return found, "lemma"
        mode = "exact-fallback"
    for kw in KEYWORDS["keywords"]:
        if kw["text"].lower() in text_lower:
            found.append(kw["text"])
    return found, mode


def capture_station(station, model):
    stream_urls = station.get("streamUrls", [])
    if not stream_urls:
        print(f"[SKIP] {station['name']}: no stream URLs")
        return
    out_dir = Path(PIPELINE["outputDirectory"])
    chunk_dir = out_dir / "_standalone_chunks" / f'{station["id"]}_{station["languageCode"]}'
    chunk_dir.mkdir(parents=True, exist_ok=True)
    pattern = chunk_dir / "chunk_%06d.wav"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", stream_urls[0], "-vn", "-ac", "1", "-ar", "16000",
        "-f", "segment", "-segment_time", str(PIPELINE["chunkSeconds"]),
        "-reset_timestamps", "1", str(pattern),
    ]
    process = subprocess.Popen(cmd)
    processed = set()
    ring = deque(maxlen=max(1, PIPELINE["preBufferSeconds"] // PIPELINE["chunkSeconds"] + 2))
    try:
        while process.poll() is None:
            for chunk in sorted(chunk_dir.glob("*.wav"))[:-1]:
                if chunk in processed:
                    continue
                processed.add(chunk)
                ring.append(chunk)
                text = transcribe(model, chunk, station["languageCode"])
                matches, mode = find_matches(text, station["languageCode"])
                for keyword in matches:
                    alert = {
                        "detectedAt": datetime.now(timezone.utc).isoformat(),
                        "stationId": station["id"],
                        "stationName": station["name"],
                        "languageCode": station["languageCode"],
                        "matchedKeyword": keyword,
                        "matchMode": mode,
                        "transcriptSnippet": text,
                    }
                    with (out_dir / "standalone_alerts.jsonl").open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(alert, ensure_ascii=False) + "\\n")
                    print(json.dumps(alert, ensure_ascii=False))
            time.sleep(1)
    finally:
        process.terminate()


def main():
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required on PATH")
    device = "cpu" if PIPELINE["device"] == "auto" else PIPELINE["device"]
    compute = PIPELINE["computeType"]
    if compute == "auto":
        compute = "int8" if device == "cpu" else "float16"
    model = WhisperModel(PIPELINE["whisperModel"], device=device, compute_type=compute)
    if not STATIONS:
        print("No stations configured. Select stations in the UI and re-export.")
        return
    for station in STATIONS:
        if station.get("streamUrls"):
            capture_station(station, model)


if __name__ == "__main__":
    main()
`;
}

createRoot(document.getElementById("root")!).render(<App />);
