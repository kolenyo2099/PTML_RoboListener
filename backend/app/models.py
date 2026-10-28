from __future__ import annotations

from pydantic import BaseModel, Field


class Stream(BaseModel):
    """A playable audio source for a station."""

    url: str
    bitrate: int = 0
    format: str = "unknown"
    isHttps: bool = False


class Location(BaseModel):
    """Where a station broadcasts from, if the API provides it."""

    cityName: str = ""
    countryName: str = "Unknown"
    countryCode: str = ""


class Genre(BaseModel):
    text: str = "General"


class Popularity(BaseModel):
    global_: int = Field(0, alias="global")


class Station(BaseModel):
    """Station data as the frontend sends it to the backend."""

    id: str  # Radio Browser UUID (e.g. "9257ed3b-c422-43cf-a8dd-8165861b3187")
    name: str
    slug: str = ""
    location: Location
    genre: Genre = Field(default_factory=Genre)
    popularity: Popularity = Field(default_factory=Popularity)
    streams: list[Stream] = Field(default_factory=list)
    languageCode: str


class Keyword(BaseModel):
    id: str
    text: str
    addedAt: str


class KeywordConfig(BaseModel):
    keywords: list[Keyword] = Field(default_factory=list)
    matchMode: str = "lemma"
    fuzzyThreshold: int = 80


class PipelineConfig(BaseModel):
    whisperModel: str = "small"
    device: str = "auto"
    computeType: str = "auto"
    languageHintMode: str = "per-station"
    manualLanguageCode: str = ""
    chunkSeconds: int = 30
    preBufferSeconds: int = 15
    postBufferSeconds: int = 30
    outputFormat: str = "wav"
    outputDirectory: str = "./recordings"
    transcriptLogDirectory: str = "./transcripts"


class StartMonitorRequest(BaseModel):
    stations: list[Station]
    keywords: KeywordConfig = Field(default_factory=KeywordConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)


class MonitorJobStation(BaseModel):
    """Stripped station shape matching the PRD MonitorJob contract."""

    id: str  # Radio Browser UUID
    name: str
    slug: str = ""
    countryName: str
    countryCode: str = ""
    languageCode: str
    streamUrls: list[str]


class MonitorJob(BaseModel):
    """The integration contract between frontend and backend (PRD Section 5)."""

    stations: list[MonitorJobStation]
    keywordConfig: KeywordConfig = Field(default_factory=KeywordConfig)
    pipelineConfig: PipelineConfig = Field(default_factory=PipelineConfig)

