"""Outward-facing DTOs: the vault-specific JSON the tvOS app decodes.

These are deliberately flat and client-friendly. The app never sees raw
Jellyfin/TMDB shapes — vault-api maps everything into these.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExternalScores(BaseModel):
    """Aggregate critic/audience scores from OMDb (M5, optional)."""
    imdb: float | None = None            # 0–10
    rotten_tomatoes: int | None = None   # 0–100 (%)
    metacritic: int | None = None        # 0–100
    source: str = "omdb"


class HomeScene(BaseModel):
    id: str
    label: str
    active: bool = False


class HomeLightRoom(BaseModel):
    id: str
    label: str
    state: str = "unknown"
    scenes: list[HomeScene] = Field(default_factory=list)


class HomeClimate(BaseModel):
    id: str
    label: str
    entity_id: str = ""
    current_temperature: float | None = None
    target_temperature: float | None = None
    hvac_mode: str | None = None
    preset_mode: str | None = None


class HomeCoffee(BaseModel):
    label: str
    entity_id: str
    on: bool = False
    state: str = "unknown"


class HomeWeather(BaseModel):
    entity_id: str = ""
    state: str = "unknown"
    temperature: float | None = None


class HomeWindow(BaseModel):
    entity_id: str
    label: str
    open: bool = False
    state: str = "unknown"


class HomeOverview(BaseModel):
    lights: list[HomeLightRoom] = Field(default_factory=list)
    climates: list[HomeClimate] = Field(default_factory=list)
    coffee: HomeCoffee
    weather: HomeWeather = Field(default_factory=HomeWeather)
    windows: list[HomeWindow] = Field(default_factory=list)
    lights_on: int = 0
    windows_open: int = 0


class HomeClimateUpdate(BaseModel):
    target_temperature: float | None = None
    hvac_mode: str | None = None
    preset_mode: str | None = None


class HomeCoffeeUpdate(BaseModel):
    on: bool


class TodayEvent(BaseModel):
    calendar_id: str
    calendar_label: str
    summary: str
    start: str
    end: str | None = None
    all_day: bool = False
    location: str | None = None


class TodayTodoItem(BaseModel):
    uid: str | None = None
    summary: str
    status: str = "needs_action"
    description: str | None = None
    due: str | None = None


class TodayTodoList(BaseModel):
    entity_id: str
    label: str
    items: list[TodayTodoItem] = Field(default_factory=list)


class TodayWeatherForecast(BaseModel):
    datetime: str
    condition: str | None = None
    temperature: float | None = None
    templow: float | None = None
    precipitation_probability: float | None = None
    precipitation: float | None = None
    wind_speed: float | None = None


class TodayWeather(BaseModel):
    entity_id: str = ""
    condition: str = "unknown"
    temperature: float | None = None
    precipitation_probability: float | None = None
    humidity: float | None = None
    wind_speed: float | None = None
    hourly: list[TodayWeatherForecast] = Field(default_factory=list)
    daily: list[TodayWeatherForecast] = Field(default_factory=list)


class TodayNews(BaseModel):
    headline: str | None = None
    summary: str | None = None


class TodayTodoUpdate(BaseModel):
    item: str
    status: str = "completed"


class TodayOverview(BaseModel):
    events: list[TodayEvent] = Field(default_factory=list)
    todos: list[TodayTodoList] = Field(default_factory=list)
    weather: TodayWeather = Field(default_factory=TodayWeather)
    news: TodayNews = Field(default_factory=TodayNews)


class PodcastPlayer(BaseModel):
    id: str
    label: str
    entity_id: str


class PodcastFeed(BaseModel):
    id: str
    title: str
    description: str | None = None
    image_url: str | None = None
    episode_count: int = 0


class PodcastEpisode(BaseModel):
    id: str
    feed_id: str
    feed_title: str
    title: str
    subtitle: str | None = None
    description: str | None = None
    published: str | None = None
    duration: str | None = None
    audio_url: str
    image_url: str | None = None
    resume_seconds: float | None = None
    completed: bool = False


class PodcastOverview(BaseModel):
    feeds: list[PodcastFeed] = Field(default_factory=list)
    episodes: list[PodcastEpisode] = Field(default_factory=list)
    players: list[PodcastPlayer] = Field(default_factory=list)
    default_player_id: str | None = None


class PodcastPlayRequest(BaseModel):
    episode_id: str
    player_id: str | None = None


class PodcastProgressUpdate(BaseModel):
    episode_id: str
    position_seconds: float = Field(ge=0)
    completed: bool = False


class PodcastProgress(BaseModel):
    episode_id: str
    position_seconds: float = 0
    completed: bool = False
    updated_at: str


class PodcastSearchResult(BaseModel):
    title: str
    feed_url: str
    image_url: str | None = None
    author: str | None = None


class PodcastSearchResponse(BaseModel):
    results: list[PodcastSearchResult] = Field(default_factory=list)


class PodcastSubscribeRequest(BaseModel):
    feed_url: str
    title: str | None = None


class PodcastNowPlaying(BaseModel):
    player_id: str
    player_label: str
    entity_id: str
    state: str = "unknown"
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    image_url: str | None = None
    position: float | None = None
    duration: float | None = None


class PodcastTransportUpdate(BaseModel):
    player_id: str | None = None
    action: str
    seconds: float | None = None
    speed: float | None = None


class PhotoItem(BaseModel):
    id: str
    title: str | None = None
    taken_at: str | None = None
    image_url: str


class PhotoOverview(BaseModel):
    photos: list[PhotoItem] = Field(default_factory=list)


class MusicNowPlaying(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    image_key: str | None = None
    image_url: str | None = None
    seek_position: int | None = None
    length: int | None = None


class MusicOutput(BaseModel):
    id: str
    name: str
    volume: int | None = None
    can_group_with_output_ids: list[str] = Field(default_factory=list)


class MusicZone(BaseModel):
    id: str
    name: str
    state: str = "unknown"
    now_playing: MusicNowPlaying | None = None
    outputs: list[MusicOutput] = Field(default_factory=list)


class MusicStatus(BaseModel):
    connected: bool = False
    core_name: str | None = None
    zone_count: int = 0


class MusicAlbum(BaseModel):
    item_key: str
    album_index: int | None = None
    title: str
    subtitle: str | None = None
    image_key: str | None = None
    image_url: str | None = None
    is_playable: bool = False


class MusicAlbumShelf(BaseModel):
    albums: list[MusicAlbum] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 24
    query: str = ""


class MusicSearchResult(BaseModel):
    item_key: str
    title: str
    subtitle: str | None = None
    image_key: str | None = None
    image_url: str | None = None
    hint: str | None = None
    parent_title: str | None = None
    hierarchy: str | None = None
    browser_session_key: str | None = None
    album_index: int | None = None
    is_playable: bool = False


class MusicSearchShelf(BaseModel):
    source: str = "roon"
    fallback_from: str | None = None
    title: str | None = None
    subtitle: str | None = None
    query: str = ""
    results: list[MusicSearchResult] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 24
    expanded: bool = False


class MusicTransportUpdate(BaseModel):
    zone_id: str
    action: str
    output_id: str | None = None
    volume: int | None = None


class MusicPlayRequest(BaseModel):
    zone_id: str
    item_key: str | None = None
    album_index: int | None = None
    hierarchy: str | None = None
    browser_session_key: str | None = None


class MusicGroupRequest(BaseModel):
    output_ids: list[str]


class KioskMediaItem(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str | None = None
    overview: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    progress: float | None = None
    stream_url: str | None = None
    runtime_seconds: float | None = None
    playable: bool = False


class KioskMediaOverview(BaseModel):
    continue_watching: list[KioskMediaItem] = Field(default_factory=list)
    next_up: list[KioskMediaItem] = Field(default_factory=list)
    latest_movies: list[KioskMediaItem] = Field(default_factory=list)
    latest_series: list[KioskMediaItem] = Field(default_factory=list)
    spotlight: list[KioskMediaItem] = Field(default_factory=list)


class LibraryItem(BaseModel):
    id: str
    type: str  # "Movie" | "Series" | "Episode"
    title: str
    overview: str | None = None
    year: int | None = None
    genres: list[str] = []
    runtime_seconds: float | None = None
    audio_tracks: list[AudioTrackInfo] = Field(default_factory=list)
    community_rating: float | None = None  # ≈ IMDB aggregate (Jellyfin field)
    critic_rating: float | None = None      # ≈ RT (Jellyfin CriticRating, 0–100)
    user_rating: float | None = None        # this user's own 0–10 rating
    official_rating: str | None = None     # e.g. "FSK 16"
    poster_url: str | None = None
    backdrop_url: str | None = None
    logo_url: str | None = None   # ClearLogo: wide transparent PNG for hero display
    # Playback state (from Jellyfin UserData)
    played: bool = False
    played_percentage: float | None = None
    resume_position_seconds: float = 0.0
    # Episode context (None for movies/series)
    series_id: str | None = None
    series_name: str | None = None
    season_id: str | None = None
    index_number: int | None = None
    parent_index_number: int | None = None
    episode_code: str | None = None
    tmdb_id: int | None = None  # from Jellyfin ProviderIds, for library↔TMDB matching
    imdb_id: str | None = None  # from Jellyfin ProviderIds, for OMDb score lookup
    external_scores: ExternalScores | None = None  # filled in item detail when OMDb is on
    trailer_url: str | None = None  # filled in item detail from TMDB videos when available


class DiscoverItem(BaseModel):
    """A TMDB title — may or may not be in the library yet."""
    tmdb_id: int
    type: str  # "Movie" | "Series"
    title: str
    year: int | None = None
    overview: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    vote_average: float | None = None
    genre_ids: list[int] = Field(default_factory=list)


class SearchItem(BaseModel):
    title: str
    type: str  # "Movie" | "Series"
    year: int | None = None
    poster_url: str | None = None
    source: str          # "library" | "discover"
    status: str          # "playable" | "requestable"
    library_id: str | None = None  # set when status == "playable"
    tmdb_id: int | None = None      # set when status == "requestable"


class RecommendationItem(BaseModel):
    id: str  # stable shelf id, e.g. "tmdb:603" or "library:m1"
    title: str
    type: str  # "Movie" | "Series"
    year: int | None = None
    overview: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    score: float = 0.0
    reason: str
    status: str  # "playable" | "requestable"
    library_id: str | None = None
    tmdb_id: int | None = None
    # Display scores (no extra API calls): library items carry Jellyfin's
    # community (≈ IMDB) and critic (≈ RT %) ratings; discover items carry
    # TMDB's vote average in community_rating so the card can show one badge.
    community_rating: float | None = None  # 0–10
    critic_rating: float | None = None     # 0–100 (%)
    match_score: int | None = None          # 0–100 profile match
    janno_score: int | None = None          # 0–100
    tanno_score: int | None = None          # 0–100
    fear_factor: int | None = None          # Tanno-Gruselfaktor: 0–10 normal, Overflow bis 20
    profile: str | None = None              # "both" | "janno" | "tanno"
    category_tags: list[str] = Field(default_factory=list)


class RecommendationShelf(BaseModel):
    id: str
    title: str
    profile: str = "both"
    items: list[RecommendationItem] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    shelves: list[RecommendationShelf]
    llm_used: bool = False


class RequestMovieBody(BaseModel):
    tmdb_id: int
    quality_profile_id: int | None = None  # falls back to the admin default
    root_folder: str | None = None


class RequestSeriesBody(BaseModel):
    tmdb_id: int
    quality_profile_id: int | None = None
    root_folder: str | None = None


class RequestResult(BaseModel):
    ok: bool
    status: str  # "added" | "already_exists"
    title: str
    arr_id: int | None = None
    detail: str | None = None


class QueueItem(BaseModel):
    title: str
    type: str  # "Movie" | "Series"
    progress: float  # 0..1 (1 - size_left/size)
    status: str | None = None
    time_left: str | None = None



class AudioTrackInfo(BaseModel):
    index: int
    language: str | None = None
    codec: str | None = None
    channels: int | None = None
    display_title: str | None = None


class SubtitleTrackInfo(BaseModel):
    index: int
    language: str | None = None
    codec: str | None = None
    display_title: str | None = None
    # Embedded subs are decoded from the container by the player (delivery_url
    # is None). External subs (e.g. an OpenSubtitles sidecar) aren't in the
    # direct stream, so the player downloads them from this URL instead.
    is_external: bool = False
    delivery_url: str | None = None


class RemoteSubtitleInfo(BaseModel):
    """A subtitle result from Jellyfin's OpenSubtitles remote-search endpoint.

    Id is the opaque provider id (may contain '/' etc.) used to trigger a
    download. All other fields are best-effort — skip-on-missing is handled
    on the service side.
    """
    id: str
    provider_name: str | None = None
    name: str | None = None
    format: str | None = None
    language: str | None = None
    download_count: int | None = None
    community_rating: float | None = None
    is_hash_match: bool | None = None
    comment: str | None = None


class SubtitleDownloadBody(BaseModel):
    """Request body for POST /library/item/{item_id}/subtitles/download."""
    subtitle_id: str  # opaque provider id from RemoteSubtitleInfo.id



class MediaSegment(BaseModel):
    type: str  # "intro" | "outro"
    start: float
    end: float


class TrailerStreamInfo(BaseModel):
    url: str
    container: str | None = None


class CastRequest(BaseModel):
    item_id: str


class CastResult(BaseModel):
    ok: bool
    item_id: str
    appletv: str | None = None


class CastPending(BaseModel):
    item_id: str | None = None
    created_at: str | None = None


class CastStatus(BaseModel):
    online: bool
    state: str
    app: str | None = None



class TrickplayInfo(BaseModel):
    """Trickplay (scrubbing thumbnail) metadata for a media item.

    Tile sheets are JPEG images each containing TileWidth × TileHeight thumbnails
    in a grid. The client substitutes the literal {index} placeholder in
    tile_url_template with a 0-based sheet index to fetch each sheet.
    """
    interval: int            # milliseconds between consecutive thumbnails
    tile_width: int          # thumbnails per row within one tile sheet
    tile_height: int         # thumbnails per column within one tile sheet
    thumbnail_width: int     # pixel width of a single thumbnail
    thumbnail_height: int    # pixel height of a single thumbnail
    thumbnail_count: int     # total number of thumbnails across all sheets
    tile_url_template: str   # e.g. ".../Videos/{id}/Trickplay/320/{index}.jpg?api_key=KEY"
                             # — keeps the literal "{index}" placeholder; client substitutes


class StreamInfo(BaseModel):
    """What the player needs. The URL points straight at Jellyfin (LAN) and
    carries the api_key — see the streaming note in architecture-api-first.md."""
    url: str
    container: str | None = None
    runtime_seconds: float | None = None
    audio_tracks: list[AudioTrackInfo] = Field(default_factory=list)
    subtitle_tracks: list[SubtitleTrackInfo] = Field(default_factory=list)
    segments: list[MediaSegment] = Field(default_factory=list)
    trickplay: TrickplayInfo | None = None


class ProgressUpdate(BaseModel):
    position_seconds: float
    is_paused: bool = False
    media_source_id: str | None = None


class RatingUpdate(BaseModel):
    rating: float = Field(ge=0, le=10)  # out-of-range → 422 from FastAPI


class WatchedUpdate(BaseModel):
    watched: bool


class ServiceStatus(BaseModel):
    name: str
    configured: bool
    ok: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    services: list[ServiceStatus]


class RatingSnapshotBody(BaseModel):
    title: str
    type: str  # "Movie" | "Series" | "Episode"
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    janno_rating: float | None = Field(default=None, ge=0, le=10)
    tanno_rating: float | None = Field(default=None, ge=0, le=10)
    # Tanno-Gruselfaktor: normal 0–10; für besonders brutale Titel darf der Wert
    # „aus Spaß" über 10 hinausgehen, daher Obergrenze 20.
    tanno_fear_factor: float | None = Field(default=None, ge=0, le=20)


class RatingSnapshot(RatingSnapshotBody):
    item_id: str
    updated_at: str


class PersonaProfile(BaseModel):
    person: str  # "janno" | "tanno"
    favorite_genres: list[str] = []
    fear_comfort: int = 5  # 0–10: 0 = no fear at all, 10 = bring it on


class PickerRequest(BaseModel):
    profile: str = "both"  # "janno" | "tanno" | "both"
    genres: list[str] = []
    mood_fear: int | None = None  # 0–10 desired intensity
    length: str | None = None  # "short" | "feature" | "series"
    surprise: bool = False
    exclude_ids: list[str] = []


class PickItem(BaseModel):
    id: str
    title: str
    type: str  # "Movie" | "Series"
    year: int | None = None
    overview: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    logo_url: str | None = None
    source: str  # "library" | "discover"
    status: str  # "playable" | "requestable"
    library_id: str | None = None
    tmdb_id: int | None = None
    reason: str
    fear_factor: int | None = None
    community_rating: float | None = None


class PickerResponse(BaseModel):
    library_pick: PickItem | None = None
    discover_pick: PickItem | None = None
    alternatives: list[PickItem] = []
    llm_used: bool = False
