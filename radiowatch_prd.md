# RadioWatch — Product Requirements Document

**Version:** 1.1
**Status:** Draft
**Intended audience:** AI development agent
**Change from v1.0:** Application is now language-agnostic. Users select one or more broadcast languages before station discovery. All transcription, lemma matching, and keyword presets are parameterized by the selected language(s). Spanish is the default but any language supported by the 50K Radio Stations API and faster-whisper may be used.

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Glossary](#2-glossary)
3. [System Architecture Summary](#3-system-architecture-summary)
4. [User Roles](#4-user-roles)
5. [Application Structure](#5-application-structure)
6. [User Journeys](#6-user-journeys)
   - 6.1 First Launch and API Key Setup
   - 6.2 Language Selection
   - 6.3 Country Browser and Station Discovery
   - 6.4 Station Selection and Monitor Configuration
   - 6.5 Keyword Management
   - 6.6 Pipeline Configuration
   - 6.7 Active Monitoring and Live Dashboard
   - 6.8 Alert Review and Clip Export
   - 6.9 Session Persistence and Resume
7. [Feature Requirements](#7-feature-requirements)
8. [Data Models](#8-data-models)
9. [External Integrations](#9-external-integrations)
10. [Backend Pipeline Specification](#10-backend-pipeline-specification)
11. [Non-Functional Requirements](#11-non-functional-requirements)
12. [Out of Scope](#12-out-of-scope)

---

## 1. Product Overview

RadioWatch is a desktop-class web application that enables investigators, journalists, and human rights monitors to watch multiple live broadcast streams in any language simultaneously for specific keywords or phrases. When a keyword is detected in a stream's transcription, the application saves a timestamped audio clip (with configurable pre- and post-match buffers), logs the transcript segment, and surfaces the alert in a real-time dashboard.

### Core value proposition

- Select one or more broadcast languages to monitor (e.g. Spanish, Arabic, French, Portuguese).
- Discover stations broadcasting in those languages, organized by country, using the 50K Radio Stations API (RapidAPI).
- Select any combination of stations across one or more countries and languages to monitor simultaneously.
- Define keywords with support for exact, lemma-based (morphological), or fuzzy matching — each station's transcript is matched using the language-appropriate model.
- Run a local Python backend pipeline (ffmpeg + faster-whisper) that captures, transcribes (with a per-station language hint), and keyword-scans streams.
- Review alerts, replay clips, and export findings without data leaving the user's machine.

---

## 2. Glossary

| Term | Definition |
|---|---|
| **Station** | A radio or TV broadcast source with one or more stream URLs, metadata (name, country, genre, bitrate, language), and a unique ID from the 50K Radio Stations API. |
| **Stream URL** | A direct audio stream endpoint (HLS, Icecast, RTMP, MP3 stream) associated with a station. A station may have multiple stream URLs as fallbacks. |
| **Language** | An ISO 639-1 two-letter code (e.g. `es`, `ar`, `fr`, `pt`) identifying the broadcast language of a station and the language used to configure transcription and lemma matching for that station. |
| **Active language set** | The set of one or more languages the user has selected for the current session. Determines which stations are fetched from the API and which spaCy models are pre-loaded. |
| **Language profile** | The combination of a Whisper language hint and a spaCy model code associated with a given ISO 639-1 language code. Used by the backend to configure per-station transcription and lemma matching. |
| **Country panel** | A collapsible UI section grouping all fetched stations for a single country, within the context of the active language set. |
| **Monitor slot** | An active capture-and-transcribe process assigned to a single station stream. |
| **Keyword** | A word or short phrase the user wants to detect in transcribed audio. Keywords are language-agnostic entries in a shared list; matching is applied per-station using that station's language profile. |
| **Lemma match** | Matching that normalizes a word to its root form using the spaCy model for the station's language (e.g. for Spanish: "detenidos" → "detener"; for French: "détenus" → "détenir"), so morphological variants are caught without listing every form. Falls back to exact match if no spaCy model is available for the station's language. |
| **Fuzzy match** | String similarity matching with a configurable threshold (default: 80% ratio via rapidfuzz) to catch transcription errors or close variants. Language-independent. |
| **Chunk** | A fixed-length audio segment (default: 30 seconds) produced by ffmpeg from a stream, fed to the Whisper transcription worker. |
| **Ring buffer** | A rolling queue of the N most recent audio chunks per station, used to reconstruct audio from before a keyword match fires. |
| **Pre-buffer** | Audio saved from before the keyword match (pulled from the ring buffer). |
| **Post-buffer** | Audio recorded after the keyword match fires, up to a configured duration. |
| **Clip** | The saved audio file combining pre-buffer + triggering chunk + post-buffer. |
| **Alert** | A logged event recording the station name, language, timestamp, matched keyword, transcript snippet, and path to the saved clip. |
| **Pipeline config** | User-adjustable parameters controlling Whisper model, chunk length, buffer sizes, match mode, output format, and per-language settings. |
| **Export script** | A generated Python script that encodes the current station list, keywords, language profiles, and pipeline config, ready to run locally. |

---

## 3. System Architecture Summary

The application has two layers:

**Frontend (browser):** A SvelteKit or React single-page application responsible for language selection, station discovery (via 50K Radio Stations API), selection UI, keyword management, pipeline configuration, alert dashboard, and clip review. The frontend communicates with the backend via a local WebSocket or REST API.

**Backend (local Python process):** A FastAPI server that manages capture processes (one per monitored station using ffmpeg via subprocess), a shared faster-whisper transcription worker pool (with per-station language hints), language-appropriate keyword matching, ring buffer management, clip saving, and alert emission.

```
[Browser UI]
    │ REST / WebSocket (localhost)
    ▼
[FastAPI backend]
    ├── ffmpeg capture process × N stations
    ├── faster-whisper worker pool (language hint per station)
    ├── Language profile resolver (spaCy model per language)
    ├── Keyword matcher (exact / lemma / fuzzy, per station language)
    ├── Ring buffer per station
    └── Alert log + clip archive
```

For the prototype phase, the frontend can operate independently (language selection, station discovery, keyword config, script export) without the backend running. Full monitoring requires the backend.

---

## 4. User Roles

| Role | Description |
|---|---|
| **Investigator** | Primary user. Selects languages, configures monitoring, reviews alerts, exports clips and transcripts. |
| **Administrator** | (Optional, future) Manages multi-user deployments, shared keyword lists, access control. |

All current requirements target the Investigator role in a single-user local deployment.

---

## 5. Application Structure

The application consists of five primary views, always accessible via a persistent top navigation bar:

| View | Route | Purpose |
|---|---|---|
| **Discovery** | `/discovery` | Select broadcast languages, browse and select stations by country |
| **Monitor** | `/monitor` | Real-time status of active monitor slots |
| **Keywords** | `/keywords` | Manage keyword list and match configuration |
| **Pipeline** | `/pipeline` | Configure backend parameters and export script |
| **Alerts** | `/alerts` | Review, replay, and export matched clips |

A persistent **status bar** at the top of all views shows: backend connection status, active language badges (one pill per active language, e.g. "ES" "AR"), number of active monitor slots, number of keywords, and count of unreviewed alerts.

---

## 6. User Journeys

### 6.1 First Launch and API Key Setup

**Goal:** The user authenticates against the 50K Radio Stations API so they can fetch station data.

**Preconditions:** The user has a RapidAPI account and a valid API key for the 50K Radio Stations API.

**Steps:**

1. User opens the application for the first time.
2. Application displays a full-screen onboarding modal with:
   - A brief description of RadioWatch's purpose.
   - A text field labeled "RapidAPI Key."
   - A link to https://rapidapi.com to obtain a key.
   - A "Continue with demo data" option that loads hardcoded example stations in Spanish and French without an API key.
3. User pastes their API key into the field and clicks "Verify & Continue."
4. Application sends a test request to `GET /radios?limit=1` with the provided key.
5. On success: API key is stored in localStorage, modal closes, user proceeds to the Language Selection step (Journey 6.2).
6. On failure (4xx/5xx): modal displays an inline error message with the HTTP status and a suggestion to check the key. Field remains editable.
7. User can update their API key at any time via Settings (accessible from the status bar).

**Edge cases:**
- If localStorage is unavailable (private browsing), display a warning that the key will not persist across sessions.
- If the API returns a 429 (rate limit), display a specific message explaining the free tier limit (500 req/month) and suggest upgrading.

---

### 6.2 Language Selection

**Goal:** The user selects one or more broadcast languages to monitor, which determines which stations are fetched and which transcription/matching models are pre-loaded.

**Preconditions:** API key is configured (or demo mode is active).

**Steps:**

1. After API key setup (or on returning visits if no language is persisted), the Discovery view shows a language selection panel as the primary UI element — above the country panels.
2. The language selection panel displays a searchable grid of available languages, fetched from `GET /languages`. Each language entry shows:
   - Language name in English (e.g. "Spanish").
   - Language name in its native form (e.g. "Español").
   - ISO 639-1 code (e.g. "es").
   - Station count available in that language.
   - A Whisper support badge: "Supported" (green) if faster-whisper has a dedicated model for this language, "Auto-detect only" (amber) if Whisper will guess the language, "Limited" (gray) if coverage is known to be weak.
   - A Lemma matching badge: "Full lemma support" if a spaCy model is available, "Exact/fuzzy only" if not (see Language Profile table in Section 8).
3. User clicks one or more language entries to select them. Selected languages are highlighted. At least one language must be selected to proceed.
4. A summary row below the grid shows the active language set: e.g. "Monitoring: Spanish (ES) · Arabic (AR) · French (FR)" — each as a removable chip.
5. User clicks "Load stations" (or "Apply" if languages are changed mid-session).
6. Application calls `GET /languages/{code}/radios?limit=100` for each selected language in parallel and merges results, deduplicating by station ID.
7. A loading state (skeleton panels) is shown while fetches are in progress. Each language fetch resolves independently — country panels for a language appear as soon as that language's fetch completes, without waiting for all languages.
8. The language panel collapses (but remains accessible via an "Edit languages" button) once at least one language is loaded, giving full vertical space to the country panels.

**Changing the active language set mid-session:**
- User clicks "Edit languages" to re-expand the language panel.
- Adding a new language: fetches stations for that language and merges into the existing country panels. Already-selected stations are unaffected.
- Removing a language: stations belonging exclusively to that language (not also returned under another active language) are removed from the Discovery list. If any removed stations were selected for monitoring, a confirmation dialog warns the user: "Removing [Language] will deselect [N] stations currently being monitored. Continue?"
- If monitoring is active, removing a language that has active monitor slots triggers a stop for those slots before they are removed.

**Edge cases:**
- If a language has zero stations in the API, show a "No stations found for this language" tooltip on hover and prevent selection.
- If the user selects more than 5 languages simultaneously, show a warning: "Fetching many languages at once may approach your API rate limit. Proceeding will use approximately [N] requests."
- If `GET /languages` fails, fall back to a hardcoded list of the 30 most common broadcast languages with their ISO codes, without station counts.

---

### 6.3 Country Browser and Station Discovery

**Goal:** The user explores available stations for their selected language(s), organized by country, and understands what is available before committing to monitoring.

**Preconditions:** At least one language is selected and its stations have been fetched.

**Steps:**

1. Below the language selection panel, the Discovery view shows country panels for all fetched stations.
2. Country panels are sorted by total station count across all active languages (descending). Each panel header shows:
   - Country name and flag emoji.
   - Total station count for that country (across all active languages).
   - Language breakdown if multiple languages are active (e.g. "12 ES · 4 FR").
   - Count of currently selected stations for that country (e.g. "3 selected").
   - A "Select all" / "Deselect all" toggle for that country.
3. Each panel is collapsed by default. User clicks a country header to expand it.
4. Inside an expanded panel, stations are listed as cards. Each card shows:
   - Station name.
   - City (if available).
   - Genre tags.
   - Language badge (e.g. "ES", "AR") — important when multiple languages are active.
   - Bitrate and stream format of the primary stream.
   - Number of fallback streams (if > 1).
   - A selection checkbox or toggle.
5. User can filter the country panel list by language using a language filter row above the panels — chips for each active language (e.g. "All · ES · AR · FR"). Selecting a chip shows only countries that have stations in that language.
6. User can search across all stations using a search input at the top of the Discovery view. Search filters station names and city names in real time, expanding any country panel that has matching results.
7. User can filter by genre using a multi-select genre chip row.
8. User can load more stations for a specific country and language by clicking "Load more" at the bottom of a country panel, which calls `GET /countries/{countryName}/radios?limit=40&page=N` and appends results.
9. User can click any station card to open a Station Detail drawer showing:
   - Full metadata (name, country, city, genre, language name and code, global popularity score).
   - All available stream URLs with bitrate and format.
   - A "Preview" button that plays the stream in an HTML5 audio element within the drawer.
   - An "Add to monitor" / "Remove from monitor" button.

**Edge cases:**
- If a station has no `streams` array or an empty one, display it as "No stream available" and disable selection.
- If a station's language code from the API does not match any active language (possible if a station is multilingual or mis-tagged), display it with a "Language unverified" badge and still allow selection.
- If a country has only one station, skip the "Select all" toggle.

---

### 6.4 Station Selection and Monitor Configuration

**Goal:** The user selects specific stations across one or more countries and languages and assigns them to active monitor slots.

**Preconditions:** Stations have been loaded in the Discovery view.

**Steps:**

1. User selects stations by checking their toggle in the Discovery view. Selection state is reflected immediately:
   - The station card shows a highlighted border and a checkmark.
   - The country panel header updates its selected count.
   - The status bar updates the "N monitored" counter.
2. User can select stations from multiple countries and multiple languages in the same session. A warning is shown if more than 10 stations are selected simultaneously (performance note). There is no hard cap in the UI.
3. User navigates to the Monitor view. It shows:
   - A card per selected station.
   - Each card displays: station name, country flag, language badge, stream URL (truncated), current status (Idle / Capturing / Transcribing / Error), and a Remove button.
   - A global "Start monitoring" button (if backend is connected) or a "Generate script" button (if backend is not connected).
4. User clicks "Start monitoring."
   - Application sends a `POST /monitor/start` to the backend with the list of stations, each including stream URLs, station name, and `languageCode`.
   - Each station card transitions to "Capturing" status.
5. User can add or remove stations while monitoring is active:
   - Adding: select a new station in Discovery, navigate to Monitor, the new card appears with a "Start" button.
   - Removing: click "Remove" on a station card. Application sends `DELETE /monitor/{stationId}` to the backend, stopping that capture process. The card is removed.
6. Stream fallback: if the primary stream URL fails, the backend retries with the next fallback URL. The Monitor card shows "Reconnecting..." with the fallback stream number.

**Edge cases:**
- If the backend is not running when the user clicks "Start monitoring," show a modal with the startup command in a code block.
- If a stream URL is unreachable after all fallbacks are exhausted, the station card shows "Error" with a Retry button and a timestamp of last attempt.
- If the user selects more than 10 stations: display a warning banner but do not block the action.

---

### 6.5 Keyword Management

**Goal:** The user defines and manages the keyword list. Keywords are shared across all active languages; the backend applies them per-station using the appropriate language model.

**Preconditions:** User is on the Keywords view.

**Steps:**

1. The Keywords view displays:
   - A list of active keywords as removable tags.
   - An input field for adding new keywords or phrases.
   - A match mode selector (Exact / Lemma / Fuzzy) with a short explanation of each mode and a note on language behavior (see below).
   - A fuzzy threshold slider (visible only when Fuzzy mode is selected, range 50–100, default 80).
   - A language-aware preset section (see step 6).
2. User types a keyword or phrase into the input field and presses Enter or clicks "Add."
   - The keyword appears as a tag in the active list.
   - Duplicate detection: if the keyword already exists (case-insensitive), show an inline "Already added" message.
3. User removes a keyword by clicking the × on its tag.
4. User can bulk-import keywords by pasting a newline-separated list into the input field. The application splits by newline, deduplicates, and adds all valid entries.
5. User selects a match mode:
   - **Exact:** Case-insensitive substring match. Language-independent. Fast, no dependencies.
   - **Lemma (recommended):** Each station's transcript is lemmatized using the spaCy model for that station's language before matching. The keyword is also lemmatized using the same model. This means a keyword added in one language will only lemma-match transcripts in that language; for cross-language coverage, add the keyword in each target language separately. If no spaCy model is available for a station's language, that station falls back to exact matching for this keyword. A language coverage table is shown in the UI (see Language Profile table in Section 8).
   - **Fuzzy:** Uses `rapidfuzz.fuzz.partial_ratio`. Language-independent. Threshold slider controls minimum similarity score.
6. The preset section shows keyword group cards. Each card is labeled with the language it targets and is visible only if that language is in the active language set. If multiple languages are active, cards from all active languages are shown, grouped by language. Each card has an "Add all" button.

   Preset groups by language (non-exhaustive; AI agent should expand to the full set during implementation):

   **Spanish (ES):**
   - Derechos humanos: detención, desaparición, tortura, ejecución, desplazamiento
   - Seguridad: operativo, enfrentamiento, homicidio, secuestro, narcotráfico
   - Protesta social: manifestación, protesta, marcha, huelga, represión
   - Migración: migrantes, deportación, frontera, caravana, expulsión
   - Corrupción: corrupción, soborno, desvío, impunidad, fiscal

   **French (FR):**
   - Droits humains: détention, disparition, torture, exécution, déplacement
   - Sécurité: opération, affrontement, homicide, enlèvement, trafic
   - Protestation: manifestation, grève, répression, blocus
   - Migration: migrants, expulsion, frontière, asile, réfugiés
   - Corruption: corruption, détournement, impunité, procureur

   **Arabic (AR):**
   - Human rights: اعتقال, اختفاء, تعذيب, إعدام, تهجير
   - Security: مداهمة, مواجهة, جريمة, اختطاف, مخدرات
   - Protest: احتجاج, مظاهرة, إضراب, قمع
   - Migration: مهاجرون, ترحيل, لجوء, حدود
   - Corruption: فساد, رشوة, اختلاس, إفلات من العقاب

   **Portuguese (PT):**
   - Direitos humanos: detenção, desaparecimento, tortura, execução, deslocamento
   - Segurança: operação, confronto, homicídio, sequestro, narcotráfico
   - Protesto: manifestação, greve, repressão, bloqueio
   - Migração: migrantes, deportação, fronteira, asilo, refugiados
   - Corrupção: corrupção, suborno, desvio, impunidade, promotor

   Additional language presets (English, German, Italian, Russian, Chinese, etc.) should be provided using the same category structure. If the active language has no preset group defined, the preset section is hidden for that language.

7. Any change to the keyword list or match mode is sent immediately to the backend via `PATCH /keywords` if monitoring is active.

**Edge cases:**
- Maximum keyword list size: 200 entries. If exceeded, show an error and prevent addition.
- If Lemma mode is selected and a station's language has no available spaCy model, show a per-language warning in the keyword view: "Lemma matching unavailable for [Language] — stations in this language will use exact matching."
- A language coverage indicator (small table or legend) is always visible in the Keywords view when Lemma mode is active, showing each active language, its spaCy model status (installed / not installed / unavailable), and the effective match mode that will be applied.

---

### 6.6 Pipeline Configuration

**Goal:** The user configures backend transcription and recording parameters before or during monitoring.

**Preconditions:** User is on the Pipeline view.

**Steps:**

1. The Pipeline view displays a settings panel with the following fields:

   **Transcription:**
   - Whisper model selector: `large-v3`, `turbo` (default), `medium`, `small`, `tiny`. Each option shows an estimated quality note and approximate processing speed.
   - Device: Auto-detect (default), CPU, CUDA, MPS. A "Detect hardware" button queries the backend and shows what is available.
   - Compute type: auto (default), float16, int8.
   - Language hint mode: "Per-station (recommended)" uses the `languageCode` from each station's metadata as the Whisper `language` parameter, improving speed and accuracy. "Auto-detect" passes no language hint and lets Whisper infer the language from audio. "Manual override" exposes a single language code input that overrides all stations — useful when the user knows all monitored stations share one language.

   **Per-language model status panel:**
   - A read-only table showing each language in the active language set, its spaCy model identifier, installation status (installed / not installed), and an "Install" button that displays the `pip` and `spacy download` commands for that model. This panel is hidden when match mode is set to Exact or Fuzzy.

   **Capture:**
   - Chunk length (seconds): numeric input, range 10–120, default 30.
   - Audio sample rate: 16000 Hz (fixed, informational only).

   **Buffers:**
   - Pre-buffer duration (seconds): numeric input, range 5–120, default 15.
   - Post-buffer duration (seconds): numeric input, range 10–120, default 30.

   **Output:**
   - Output format: WAV (default), MP3, OGG.
   - Output directory: file path input, defaults to `./recordings`.
   - Transcript log directory: file path input, defaults to `./transcripts`.

2. User adjusts any setting. Changes are validated inline.
3. User clicks "Apply." Changes affecting capture are staged for the next stream reconnect; changes affecting transcription trigger a model reload on the backend.
4. The Pipeline view also shows a "Generated Python script" section:
   - A read-only, syntax-highlighted Python script encoding all current settings, selected stations (with their `languageCode`), and keywords.
   - The script constructs a `LANGUAGE_PROFILES` dict mapping each language code to its Whisper hint and spaCy model name.
   - "Copy to clipboard" and "Download as .py" buttons.
   - The script updates in real time as settings change.
5. A "Start backend server" section (collapsible) shows the startup command and the full dependency install command including all spaCy models needed for the active language set.

**Edge cases:**
- If "Manual override" language is set to a code not recognized by Whisper, show an inline error.
- If `large-v3` is selected with CPU device, show a performance warning.
- If a language in the active set has no spaCy model and Lemma mode is active, the generated script includes an inline comment noting that exact matching will be used as fallback for that language.

---

### 6.7 Active Monitoring and Live Dashboard

**Goal:** The user observes the live status of all active monitor slots in real time.

**Preconditions:** Backend is running and at least one station is being captured.

**Steps:**

1. The Monitor view displays a card for each active station. Each card updates in real time via WebSocket:
   - **Station name, country flag, and language badge** (e.g. "AR" in an amber pill).
   - **Status indicator:** colored dot with label — Idle (gray), Capturing (blue, pulsing), Transcribing (amber, pulsing), Match detected (red, pulsing), Error (red, static).
   - **Live transcript strip:** the last 2–3 sentences of the most recent transcribed chunk, with matched keywords highlighted in amber. Text is displayed in the station's native script (RTL languages such as Arabic are rendered right-to-left).
   - **Chunk timeline:** mini horizontal bar showing match history for the last 10 chunks.
   - **Uptime counter** and **alert count badge.**
   - **Remove button.**

2. A global summary bar shows: total active streams, total chunks transcribed (session), total keywords matched (session), total clips saved (session).

3. The Monitor view can be filtered by language using the same language chip row as the Discovery view, showing only cards for stations in the selected language(s).

4. When a keyword match fires on any station:
   - The station card flashes briefly and its status changes to "Match detected."
   - A toast notification appears: "[Station name] ([Language]) — matched '[keyword]'" with a link to the Alerts view.
   - The alert count badge on the status bar increments.

5. User can pause monitoring for a single station (SIGSTOP equivalent on the capture process) or stop all monitoring with a global "Stop all" button.

**Edge cases:**
- If the WebSocket connection is lost, show a reconnect banner. Cards freeze at last known state. Auto-retry every 5 seconds.
- If transcription lag exceeds 2× chunk duration for a station, show a "Transcription lag" warning on that station's card.
- If disk space falls below 500 MB, show a persistent warning. If below 100 MB, auto-stop all monitoring and show a blocking modal.
- RTL scripts (Arabic, Hebrew, Farsi) must render correctly in the transcript strip. The frontend must apply `dir="auto"` to transcript display elements.

---

### 6.8 Alert Review and Clip Export

**Goal:** The user reviews triggered alerts, replays audio clips, reads transcript context, and exports findings.

**Preconditions:** At least one keyword match has been recorded.

**Steps:**

1. User navigates to the Alerts view.
2. The view shows a table or card list of alerts, sorted by most recent first. Each alert entry shows:
   - Timestamp (date + time, local timezone).
   - Station name, country flag, and language badge.
   - Matched keyword (highlighted).
   - Transcript snippet (±2 sentences around the match, keyword highlighted).
   - Clip duration.
   - "Play," "Export," and "Mark reviewed" controls.
3. User clicks "Play" on an alert. An inline audio player appears and begins playback. The transcript is displayed alongside.
4. User can filter alerts by station, country, language, keyword, date range, and reviewed status.
5. User clicks "Export" on a single alert. Options: audio clip, transcript TXT, or both as ZIP with metadata JSON.
6. Bulk export: select multiple alerts via checkboxes and download as ZIP.
7. User can delete an alert (with optional clip file deletion) after a confirmation dialog.
8. Alerts persist across sessions in a local SQLite database.

**Edge cases:**
- If the clip file is missing from disk, show a "File missing" badge; disable Play and Export.
- Pagination activates at 500+ alerts (50 per page).
- The metadata JSON in exports includes the station's `languageCode` and the spaCy model used for matching (or "exact-fallback" if no model was available).

---

### 6.9 Session Persistence and Resume

**Goal:** The user can close and reopen the application and resume a previous monitoring configuration.

**Preconditions:** User has previously configured languages, stations, keywords, and pipeline settings.

**Steps:**

1. On application close, the frontend saves to localStorage:
   - API key.
   - Active language set (array of ISO 639-1 codes).
   - Selected station IDs and their metadata including `languageCode`.
   - Keyword list and match mode configuration.
   - Pipeline config values.
2. On next application open, the frontend detects saved state and shows a "Resume last session?" banner:
   - "Resume" — restores language set, selected stations, keywords, and pipeline config. Navigates to Monitor view.
   - "Start fresh" — clears saved state, shows Discovery view at the language selection step.
3. If the backend is already running, monitoring resumes automatically. If not, the Monitor view shows cards in Idle state with the startup command.
4. Alert history is always loaded from the backend's persistent store.

**Edge cases:**
- If a saved station's language code is no longer in the active language set after resuming, the station is still shown in the Monitor view but its language badge shows "Language removed from active set" with an option to re-add that language.
- If a saved language code is not recognized by the API (rare), it is removed from the restored active language set with a notification.

---

## 7. Feature Requirements

### 7.1 Language Selection

| ID | Requirement | Priority |
|---|---|---|
| LS-01 | Language selection panel is the first UI element on the Discovery view | Must have |
| LS-02 | Language list is fetched from `GET /languages` with station counts | Must have |
| LS-03 | Each language entry shows Whisper support badge and Lemma support badge | Must have |
| LS-04 | User can select one or more languages; at least one is required to proceed | Must have |
| LS-05 | Active language set is shown as removable chips | Must have |
| LS-06 | Station fetches for all selected languages run in parallel | Must have |
| LS-07 | Adding a language mid-session fetches and merges new stations | Must have |
| LS-08 | Removing a language mid-session warns if active monitor slots will be affected | Must have |
| LS-09 | Warning shown if more than 5 languages selected (API rate limit risk) | Should have |
| LS-10 | Fallback hardcoded language list if `GET /languages` fails | Should have |

### 7.2 Station Discovery

| ID | Requirement | Priority |
|---|---|---|
| SD-01 | Application calls `GET /languages/{code}/radios` for each selected language on Discovery view load | Must have |
| SD-02 | Stations grouped into collapsible country panels sorted by station count descending | Must have |
| SD-03 | Country panel header shows total count, per-language count breakdown (if multiple languages active), and selected count | Must have |
| SD-04 | Each country panel has "Select all" and "Deselect all" controls | Must have |
| SD-05 | Language filter chips above country panels allow showing only stations in a specific language | Must have |
| SD-06 | Search input filters stations by name and city in real time | Must have |
| SD-07 | Genre filter chips allow filtering across all country panels | Should have |
| SD-08 | "Load more" pagination per country panel | Should have |
| SD-09 | Station detail drawer with live audio preview | Should have |
| SD-10 | Stations with no stream URLs are shown but disabled | Must have |
| SD-11 | Language badge on each station card (critical when multiple languages are active) | Must have |
| SD-12 | Selected state persists when navigating away from Discovery and returning | Must have |

### 7.3 Keyword Management

| ID | Requirement | Priority |
|---|---|---|
| KW-01 | User can add keywords via text input | Must have |
| KW-02 | User can remove keywords via × on tag | Must have |
| KW-03 | Duplicate keywords rejected with inline feedback | Must have |
| KW-04 | Exact, Lemma, and Fuzzy match modes selectable | Must have |
| KW-05 | Fuzzy mode exposes threshold slider | Must have |
| KW-06 | Lemma mode explanation notes per-station language application | Must have |
| KW-07 | Language coverage table shown in Keywords view when Lemma mode is active | Must have |
| KW-08 | Quick-add preset groups shown for each active language | Should have |
| KW-09 | Preset groups exist for ES, FR, AR, PT at minimum | Must have |
| KW-10 | Bulk import via newline-separated paste | Should have |
| KW-11 | Keyword changes propagate to active backend session without restart | Should have |
| KW-12 | Maximum 200 keywords enforced | Must have |

### 7.4 Monitoring

| ID | Requirement | Priority |
|---|---|---|
| MN-01 | Monitor view shows one card per selected station with language badge | Must have |
| MN-02 | Cards update in real time via WebSocket | Must have |
| MN-03 | Live transcript strip with keyword highlighting; RTL scripts rendered correctly | Must have |
| MN-04 | Language filter chips on Monitor view | Should have |
| MN-05 | Toast notification on keyword match includes language information | Must have |
| MN-06 | Individual station pause/resume | Should have |
| MN-07 | Global "Stop all" control | Must have |
| MN-08 | Automatic stream fallback on URL failure | Must have |
| MN-09 | Disk space warning and auto-stop | Should have |
| MN-10 | Transcription lag warning | Should have |

### 7.5 Alert Management

| ID | Requirement | Priority |
|---|---|---|
| AL-01 | Alerts list includes station language badge | Must have |
| AL-02 | Filter alerts by language (in addition to station, country, keyword, date, reviewed) | Must have |
| AL-03 | Inline audio player per alert | Must have |
| AL-04 | Single alert export with metadata JSON including languageCode and match model | Must have |
| AL-05 | Bulk export as ZIP | Should have |
| AL-06 | Mark reviewed toggle | Must have |
| AL-07 | Delete alert with confirmation | Must have |
| AL-08 | Alerts persist across sessions | Must have |
| AL-09 | "File missing" state | Must have |
| AL-10 | Pagination at 500+ alerts | Should have |

### 7.6 Pipeline and Export

| ID | Requirement | Priority |
|---|---|---|
| PL-01 | Whisper model selector | Must have |
| PL-02 | Language hint mode selector (per-station / auto-detect / manual override) | Must have |
| PL-03 | Per-language spaCy model status panel with install commands | Must have |
| PL-04 | Device selector with hardware detection | Should have |
| PL-05 | Chunk length, pre-buffer, post-buffer inputs | Must have |
| PL-06 | Output format selector | Must have |
| PL-07 | Output and transcript directory inputs | Must have |
| PL-08 | Generated script includes LANGUAGE_PROFILES dict keyed by ISO code | Must have |
| PL-09 | Generated script is fully standalone | Must have |
| PL-10 | Copy and download buttons for generated script | Must have |
| PL-11 | Backend startup command includes spaCy download commands for all active languages | Must have |

---

## 8. Data Models

### Language

```typescript
interface Language {
  code: string;                      // ISO 639-1, e.g. "es", "ar", "fr"
  nameEnglish: string;               // e.g. "Spanish"
  nameNative: string;                // e.g. "Español"
  stationCount: number;              // from API
  isRtl: boolean;                    // true for Arabic, Hebrew, Farsi, Urdu, etc.
}
```

### Language Profile

Defined as a static lookup table in both frontend and backend. The AI agent must implement this table completely at build time and keep it up to date with spaCy's available models.

```typescript
interface LanguageProfile {
  code: string;                      // ISO 639-1
  whisperCode: string;               // language code as passed to faster-whisper (usually same as ISO 639-1)
  spaCyModel: string | null;         // e.g. "es_core_news_sm", null if unavailable
  spaCyInstallCommand: string | null; // e.g. "python -m spacy download es_core_news_sm"
  lemmaSupported: boolean;           // true if spaCyModel is not null
  isRtl: boolean;
}

// Minimum required entries (agent must add more):
const LANGUAGE_PROFILES: LanguageProfile[] = [
  { code: 'es', whisperCode: 'es', spaCyModel: 'es_core_news_sm',  spaCyInstallCommand: 'python -m spacy download es_core_news_sm',  lemmaSupported: true,  isRtl: false },
  { code: 'fr', whisperCode: 'fr', spaCyModel: 'fr_core_news_sm',  spaCyInstallCommand: 'python -m spacy download fr_core_news_sm',  lemmaSupported: true,  isRtl: false },
  { code: 'de', whisperCode: 'de', spaCyModel: 'de_core_news_sm',  spaCyInstallCommand: 'python -m spacy download de_core_news_sm',  lemmaSupported: true,  isRtl: false },
  { code: 'pt', whisperCode: 'pt', spaCyModel: 'pt_core_news_sm',  spaCyInstallCommand: 'python -m spacy download pt_core_news_sm',  lemmaSupported: true,  isRtl: false },
  { code: 'it', whisperCode: 'it', spaCyModel: 'it_core_news_sm',  spaCyInstallCommand: 'python -m spacy download it_core_news_sm',  lemmaSupported: true,  isRtl: false },
  { code: 'nl', whisperCode: 'nl', spaCyModel: 'nl_core_news_sm',  spaCyInstallCommand: 'python -m spacy download nl_core_news_sm',  lemmaSupported: true,  isRtl: false },
  { code: 'ru', whisperCode: 'ru', spaCyModel: 'ru_core_news_sm',  spaCyInstallCommand: 'python -m spacy download ru_core_news_sm',  lemmaSupported: true,  isRtl: false },
  { code: 'zh', whisperCode: 'zh', spaCyModel: 'zh_core_web_sm',   spaCyInstallCommand: 'python -m spacy download zh_core_web_sm',   lemmaSupported: true,  isRtl: false },
  { code: 'ar', whisperCode: 'ar', spaCyModel: null,                spaCyInstallCommand: null,                                        lemmaSupported: false, isRtl: true  },
  { code: 'fa', whisperCode: 'fa', spaCyModel: null,                spaCyInstallCommand: null,                                        lemmaSupported: false, isRtl: true  },
  { code: 'tr', whisperCode: 'tr', spaCyModel: 'tr_core_news_trf', spaCyInstallCommand: 'python -m spacy download tr_core_news_trf', lemmaSupported: true,  isRtl: false },
  { code: 'en', whisperCode: 'en', spaCyModel: 'en_core_web_sm',   spaCyInstallCommand: 'python -m spacy download en_core_web_sm',   lemmaSupported: true,  isRtl: false },
];
```

### Station (from API, extended with local state)

```typescript
interface Station {
  id: number;                        // from API
  name: string;
  slug: string;
  location: {
    cityName: string;
    countryName: string;
    countryCode: string;             // ISO 3166-1 alpha-2
  };
  genre: { text: string };
  popularity: { global: number };
  streams: Array<{
    url: string;
    bitrate: number;
    format: string;
    isHttps: boolean;
  }>;
  languageCode: string;              // ISO 639-1, from the language filter used to fetch this station
  // local state (not from API)
  isSelected: boolean;
  monitorStatus: 'idle' | 'capturing' | 'transcribing' | 'match' | 'error' | 'paused';
  errorMessage?: string;
  alertCount: number;
  sessionStartedAt?: string;
}
```

### Keyword

```typescript
interface Keyword {
  id: string;                        // client-generated UUID
  text: string;
  addedAt: string;
}

interface KeywordConfig {
  keywords: Keyword[];
  matchMode: 'exact' | 'lemma' | 'fuzzy';
  fuzzyThreshold: number;            // 50–100, default 80
  languageHintMode: 'per-station' | 'auto-detect' | 'manual';
  manualLanguageCode?: string;       // only used when languageHintMode is 'manual'
}
```

### Alert

```typescript
interface Alert {
  id: string;
  stationId: number;
  stationName: string;
  countryName: string;
  countryCode: string;
  languageCode: string;              // ISO 639-1 of the station's broadcast language
  matchedKeyword: string;
  transcriptSnippet: string;
  fullTranscriptPath: string;
  clipPath: string;
  clipDurationSeconds: number;
  detectedAt: string;
  reviewed: boolean;
  chunkIndex: number;
  matchMode: 'exact' | 'lemma' | 'fuzzy' | 'exact-fallback';  // exact-fallback = lemma was requested but no model available
  spaCyModelUsed: string | null;     // e.g. "es_core_news_sm" or null
}
```

### PipelineConfig

```typescript
interface PipelineConfig {
  whisperModel: 'large-v3' | 'turbo' | 'medium' | 'small' | 'tiny';
  device: 'auto' | 'cpu' | 'cuda' | 'mps';
  computeType: 'auto' | 'float16' | 'int8';
  languageHintMode: 'per-station' | 'auto-detect' | 'manual';
  manualLanguageCode?: string;
  chunkSeconds: number;
  preBufferSeconds: number;
  postBufferSeconds: number;
  outputFormat: 'wav' | 'mp3' | 'ogg';
  outputDirectory: string;
  transcriptLogDirectory: string;
}
```

### BackendStatus (via WebSocket)

```typescript
interface BackendStatus {
  connected: boolean;
  activeSlots: number;
  totalChunksProcessed: number;
  totalMatchesSession: number;
  totalClipsSaved: number;
  diskFreeMB: number;
  loadedSpaCyModels: string[];       // list of currently loaded spaCy model names
  stationStatuses: Array<{
    stationId: number;
    languageCode: string;
    status: string;
    lastTranscriptSnippet: string;
    matchedKeywordsInSnippet: string[];
    chunkHistory: Array<'none' | 'match' | 'clip' | 'pending'>;
    uptimeSeconds: number;
  }>;
}
```

---

## 9. External Integrations

### 9.1 50K Radio Stations API (RapidAPI)

**Base URL:** `https://50k-radio-stations.p.rapidapi.com`

**Required headers:**
```
X-RapidAPI-Key: {userApiKey}
X-RapidAPI-Host: 50k-radio-stations.p.rapidapi.com
```

**Endpoints used:**

| Endpoint | Usage | Called from |
|---|---|---|
| `GET /radios?limit=1` | API key verification | Onboarding |
| `GET /languages` | Fetch all available languages with station counts | Language selection panel mount |
| `GET /languages/{code}/radios?limit=100` | Load stations for a selected language | Language selection "Load stations" (one call per language, in parallel) |
| `GET /countries/{countryName}/radios?limit=40&page={n}` | Paginated load per country | "Load more" button |
| `GET /radios/{id}` | Refresh stale station data | Station detail drawer, Resume warning |
| `GET /radios/search?q={query}&limit=40` | Search fallback | Search input (debounced, 400ms) |

**Caching:** API responses are cached in memory for 15 minutes. Station stream URLs are flagged as potentially stale after 24 hours.

**Rate limit awareness:** Each language loaded consumes one API request. The frontend tracks the number of API requests made in the current session and shows a counter in the Settings panel. If the count approaches the plan limit (500/month on the free tier), a persistent warning banner is shown.

**Error handling:**
- 401 / 403: invalidate API key, redirect to Settings.
- 429: show rate limit warning, disable API calls for 60 seconds with countdown.
- 5xx: show error banner, offer Retry after 10 seconds.

---

### 9.2 Backend API (local FastAPI, localhost:8000)

The frontend communicates with the backend over localhost. All endpoints are unauthenticated (single-user local deployment).

**WebSocket:** `ws://localhost:8000/ws/status` — streams `BackendStatus` updates every 2 seconds and event-driven alert notifications.

**REST endpoints (consumed by frontend):**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/status` | Health check; returns loaded spaCy models and active language set |
| `GET` | `/hardware` | Detect available GPU/CPU/MPS |
| `GET` | `/languages/profiles` | Return the LANGUAGE_PROFILES table (for frontend display) |
| `POST` | `/monitor/start` | Start monitoring; payload includes stations with languageCode |
| `DELETE` | `/monitor/{stationId}` | Stop a monitor slot |
| `POST` | `/monitor/{stationId}/pause` | Pause capture |
| `POST` | `/monitor/{stationId}/resume` | Resume capture |
| `POST` | `/monitor/stop-all` | Stop all slots |
| `PATCH` | `/keywords` | Update keyword list and match config |
| `PATCH` | `/pipeline` | Update pipeline config |
| `GET` | `/alerts` | List alerts (supports `?language=` filter) |
| `GET` | `/alerts/{alertId}` | Single alert detail |
| `PATCH` | `/alerts/{alertId}` | Update reviewed status |
| `DELETE` | `/alerts/{alertId}` | Delete alert |
| `GET` | `/alerts/{alertId}/clip` | Stream audio clip |
| `GET` | `/alerts/export` | Bulk ZIP export |

---

## 10. Backend Pipeline Specification

### 10.1 Capture process (per station)

- Uses `streamlink` (preferred) or `ffmpeg` directly.
- `ffmpeg` segments output into fixed-length WAV chunks (16 kHz mono).
- Filesystem watcher pushes new chunks to the shared transcription queue, tagged with the station's `languageCode`.
- Automatic retry with exponential backoff; fallback to next stream URL on repeated failure.
- Ring buffer: `deque(maxlen = ceil(preBufferSeconds / chunkSeconds) + 1)` per station.

### 10.2 Language profile resolution

On startup, the backend loads spaCy models for all languages in the active station set that have a defined `spaCyModel` in the LANGUAGE_PROFILES table. Models are loaded once and reused across all stations sharing a language. If a model fails to load (not installed), the backend logs a warning and records that language as falling back to exact matching.

```python
# Pseudocode
for lang_code in {s.languageCode for s in stations}:
    profile = LANGUAGE_PROFILES.get(lang_code)
    if profile and profile.spacy_model:
        try:
            nlp_models[lang_code] = spacy.load(profile.spacy_model)
        except OSError:
            nlp_models[lang_code] = None  # fallback to exact
```

### 10.3 Transcription worker pool

- One shared `faster_whisper.WhisperModel` instance.
- Workers pull chunks from the queue. Each chunk is tagged with the station's `languageCode`.
- `model.transcribe(path, language=lang_code)` is called with the station's language code if `languageHintMode` is `per-station`; with no language argument if `auto-detect`; with `manualLanguageCode` if `manual`.
- Transcripts appended to a per-station rolling log file.

### 10.4 Keyword matcher

- Operates on the full text of each transcribed chunk.
- Match mode applied as per `KeywordConfig`, using the station's language profile:
  - **Lemma:** use `nlp_models[station.languageCode]` if available; otherwise fall back to exact and record `matchMode = 'exact-fallback'` in the alert.
  - **Fuzzy:** language-independent `rapidfuzz.fuzz.partial_ratio`.
  - **Exact:** language-independent substring.
- On match: collect ring buffer, begin post-buffer recording, concatenate clip with ffmpeg, write alert to SQLite, emit WebSocket event.

### 10.5 Alert storage

- SQLite database at `{outputDirectory}/radiowatch.db`.
- Schema mirrors the `Alert` TypeScript interface.
- Clip files: `{outputDirectory}/{YYYYMMDD}/{stationSlug}_{lang}_{timestamp}_{keyword}.{format}`.
- Transcript logs: `{transcriptLogDirectory}/{stationSlug}_{lang}_{YYYYMMDD}.txt`.

---

## 11. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Performance** | UI must remain responsive with up to 20 concurrent station WebSocket updates across multiple languages. |
| **Latency** | Keyword match alert must appear in the frontend within 5 seconds of the triggering chunk being transcribed. |
| **Reliability** | A crashed capture process for one station must not affect other active monitor slots. |
| **Privacy** | No audio, transcripts, API keys, or alerts are transmitted to any remote server. All processing is local. |
| **Portability** | The generated Python script must run on macOS (Apple Silicon and Intel), Linux (x86_64), without modification. Windows is best-effort. |
| **RTL support** | All transcript display elements must correctly render right-to-left scripts (Arabic, Hebrew, Farsi, Urdu). Frontend must apply `dir="auto"` to dynamic transcript content. |
| **Accessibility** | All interactive elements keyboard-navigable. Status indicators must not rely solely on color. |
| **Disk management** | No writes outside configured output directories without explicit user permission. |
| **Startup time** | Frontend interactive within 3 seconds. Station discovery shows loading state immediately. |
| **API efficiency** | Language fetches run in parallel. Results are cached 15 minutes. Request count is tracked and surfaced to the user. |

---

## 12. Out of Scope

The following features are explicitly out of scope for the initial version:

- TV video stream monitoring (audio-only is in scope; video capture and analysis are not).
- OCR or on-screen text detection for TV streams.
- Multi-user / networked deployment with authentication.
- Cloud-based transcription (all transcription must run locally).
- Automatic translation between languages.
- Custom or fine-tuned Whisper models.
- Integration with external alert systems (email, Slack, webhooks).
- Automated reporting or PDF export.
- Browser extension variant.
- Mobile or tablet layout optimization (desktop browser only).
- Automatic language detection for stations not tagged with a language code in the API (stations with missing language metadata are treated as requiring manual language assignment by the user).

---

*End of document — version 1.1*
