import type { KeywordConfig, Language, PipelineConfig } from "./types";

export const API_BASE = "";

export const FALLBACK_LANGUAGES: Language[] = [
  { code: "es", nameEnglish: "Spanish",    nameNative: "Español",           stationCount: 0, isRtl: false },
  { code: "en", nameEnglish: "English",    nameNative: "English",            stationCount: 0, isRtl: false },
  { code: "fr", nameEnglish: "French",     nameNative: "Français",           stationCount: 0, isRtl: false },
  { code: "de", nameEnglish: "German",     nameNative: "Deutsch",            stationCount: 0, isRtl: false },
  { code: "pt", nameEnglish: "Portuguese", nameNative: "Português",          stationCount: 0, isRtl: false },
  { code: "ar", nameEnglish: "Arabic",     nameNative: "العربية",            stationCount: 0, isRtl: true  },
  { code: "ru", nameEnglish: "Russian",    nameNative: "Русский",            stationCount: 0, isRtl: false },
  { code: "zh", nameEnglish: "Chinese",    nameNative: "中文",               stationCount: 0, isRtl: false },
  { code: "it", nameEnglish: "Italian",    nameNative: "Italiano",           stationCount: 0, isRtl: false },
  { code: "nl", nameEnglish: "Dutch",      nameNative: "Nederlands",         stationCount: 0, isRtl: false },
  { code: "tr", nameEnglish: "Turkish",    nameNative: "Türkçe",             stationCount: 0, isRtl: false },
  { code: "fa", nameEnglish: "Persian",    nameNative: "فارسی",              stationCount: 0, isRtl: true  },
  { code: "he", nameEnglish: "Hebrew",     nameNative: "עברית",              stationCount: 0, isRtl: true  },
  { code: "ur", nameEnglish: "Urdu",       nameNative: "اردو",               stationCount: 0, isRtl: true  },
  { code: "hi", nameEnglish: "Hindi",      nameNative: "हिन्दी",            stationCount: 0, isRtl: false },
  { code: "bn", nameEnglish: "Bengali",    nameNative: "বাংলা",              stationCount: 0, isRtl: false },
  { code: "vi", nameEnglish: "Vietnamese", nameNative: "Tiếng Việt",        stationCount: 0, isRtl: false },
  { code: "pl", nameEnglish: "Polish",     nameNative: "Polski",             stationCount: 0, isRtl: false },
  { code: "uk", nameEnglish: "Ukrainian",  nameNative: "Українська",        stationCount: 0, isRtl: false },
  { code: "ro", nameEnglish: "Romanian",   nameNative: "Română",             stationCount: 0, isRtl: false },
  { code: "cs", nameEnglish: "Czech",      nameNative: "Čeština",            stationCount: 0, isRtl: false },
  { code: "hu", nameEnglish: "Hungarian",  nameNative: "Magyar",             stationCount: 0, isRtl: false },
  { code: "sv", nameEnglish: "Swedish",    nameNative: "Svenska",            stationCount: 0, isRtl: false },
  { code: "da", nameEnglish: "Danish",     nameNative: "Dansk",              stationCount: 0, isRtl: false },
  { code: "fi", nameEnglish: "Finnish",    nameNative: "Suomi",              stationCount: 0, isRtl: false },
  { code: "el", nameEnglish: "Greek",      nameNative: "Ελληνικά",          stationCount: 0, isRtl: false },
  { code: "th", nameEnglish: "Thai",       nameNative: "ภาษาไทย",          stationCount: 0, isRtl: false },
  { code: "ko", nameEnglish: "Korean",     nameNative: "한국어",             stationCount: 0, isRtl: false },
  { code: "ja", nameEnglish: "Japanese",   nameNative: "日本語",             stationCount: 0, isRtl: false },
  { code: "id", nameEnglish: "Indonesian", nameNative: "Bahasa Indonesia",   stationCount: 0, isRtl: false },
];

export const defaultKeywords: KeywordConfig = {
  keywords: [],
  matchMode: "lemma",
  fuzzyThreshold: 80,
};

export const defaultPipeline: PipelineConfig = {
  whisperModel: "turbo",
  device: "auto",
  computeType: "auto",
  languageHintMode: "per-station",
  manualLanguageCode: "",
  chunkSeconds: 30,
  preBufferSeconds: 15,
  postBufferSeconds: 30,
  outputFormat: "wav",
  outputDirectory: "./recordings",
  transcriptLogDirectory: "./transcripts",
};

export const presets: Record<string, Record<string, string[]>> = {
  es: {
    "Derechos humanos": ["detención", "desaparición", "tortura", "ejecución", "desplazamiento"],
    Seguridad: ["operativo", "enfrentamiento", "homicidio", "secuestro", "narcotráfico"],
    "Protesta social": ["manifestación", "protesta", "marcha", "huelga", "represión"],
    Migración: ["migrantes", "deportación", "frontera", "caravana", "expulsión"],
    Corrupción: ["corrupción", "soborno", "desvío", "impunidad", "fiscal"],
  },
  fr: {
    "Droits humains": ["détention", "disparition", "torture", "exécution", "déplacement"],
    Sécurité: ["opération", "affrontement", "homicide", "enlèvement", "trafic"],
    Protestation: ["manifestation", "grève", "répression", "blocus"],
    Migration: ["migrants", "expulsion", "frontière", "asile", "réfugiés"],
    Corruption: ["corruption", "détournement", "impunité", "procureur"],
  },
  ar: {
    "Human rights": ["اعتقال", "اختفاء", "تعذيب", "إعدام", "تهجير"],
    Security: ["مداهمة", "مواجهة", "جريمة", "اختطاف", "مخدرات"],
    Protest: ["احتجاج", "مظاهرة", "إضراب", "قمع"],
    Migration: ["مهاجرون", "ترحيل", "لجوء", "حدود"],
    Corruption: ["فساد", "رشوة", "اختلاس", "إفلات من العقاب"],
  },
  pt: {
    "Direitos humanos": ["detenção", "desaparecimento", "tortura", "execução", "deslocamento"],
    Segurança: ["operação", "confronto", "homicídio", "sequestro", "narcotráfico"],
    Protesto: ["manifestação", "greve", "repressão", "bloqueio"],
    Migração: ["migrantes", "deportação", "fronteira", "asilo", "refugiados"],
    Corrupção: ["corrupção", "suborno", "desvio", "impunidade", "promotor"],
  },
  en: {
    "Human rights": ["detention", "disappearance", "torture", "execution", "displacement"],
    Security: ["operation", "clash", "homicide", "kidnapping", "trafficking"],
    Protest: ["protest", "march", "strike", "repression"],
    Migration: ["migrants", "deportation", "border", "asylum", "refugees"],
    Corruption: ["corruption", "bribery", "impunity", "prosecutor"],
  },
};

