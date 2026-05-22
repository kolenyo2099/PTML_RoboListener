export type Language = {
  code: string;
  nameEnglish: string;
  nameNative: string;
  stationCount: number;
  isRtl: boolean;
};

export type LanguageProfile = {
  code: string;
  nameEnglish: string;
  nameNative: string;
  whisperCode: string;
  spaCyModel: string | null;
  spaCyInstallCommand: string | null;
  lemmaSupported: boolean;
  isRtl: boolean;
};

export type Station = {
  id: string;  // Radio Browser UUID
  name: string;
  slug: string;
  location: { cityName: string; countryName: string; countryCode: string };
  genre: { text: string };
  popularity: { global: number };
  streams: { url: string; bitrate: number; format: string; isHttps: boolean }[];
  languageCode: string;
};

export type Keyword = { id: string; text: string; addedAt: string };
export type MatchMode = "exact" | "lemma" | "fuzzy";

export type KeywordConfig = {
  keywords: Keyword[];
  matchMode: MatchMode;
  fuzzyThreshold: number;
};

export type PipelineConfig = {
  whisperModel: "large-v3" | "turbo" | "medium" | "small" | "tiny";
  device: "auto" | "cpu" | "cuda" | "mps";
  computeType: "auto" | "float16" | "int8";
  languageHintMode: "per-station" | "auto-detect" | "manual";
  manualLanguageCode: string;
  chunkSeconds: number;
  preBufferSeconds: number;
  postBufferSeconds: number;
  outputFormat: "wav" | "mp3" | "ogg";
  outputDirectory: string;
  transcriptLogDirectory: string;
};

export type Alert = {
  id: string;
  stationId: string;  // Radio Browser UUID
  stationName: string;
  countryName: string;
  countryCode: string;
  languageCode: string;
  matchedKeyword: string;
  transcriptSnippet: string;
  clipPath: string;
  clipDurationSeconds: number;
  detectedAt: string;
  reviewed: boolean;
  chunkIndex: number;
  matchMode: string;
  spaCyModelUsed: string | null;
  clipExists?: boolean;
};

export type BackendStatus = {
  connected: boolean;
  activeSlots: number;
  totalChunksProcessed: number;
  totalMatchesSession: number;
  totalClipsSaved: number;
  diskFreeMB: number;
  loadedSpaCyModels: string[];
  unreviewedAlerts: number;
  stationStatuses: {
    stationId: string;  // Radio Browser UUID
    languageCode: string;
    status: string;
    errorMessage?: string;
    lastTranscriptSnippet: string;
    lastTranscriptAt: string | null;
    matchedKeywordsInSnippet: string[];
    chunkHistory: string[];
    uptimeSeconds: number;
    alertCount: number;
  }[];
};
