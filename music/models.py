from dataclasses import dataclass


@dataclass
class ParsedQuery:
    raw_query: str
    song: str
    artist: str | None = None
    intent: str = "song"  # "song" | "artist"

    # future-ready (not required yet, but useful)
    song_normalized: str | None = None
    artist_normalized: str | None = None


@dataclass
class SearchDecision:
    should_try_library: bool
    should_try_catalog_ui: bool
    reason: str

    # NEW (used by verify logic)
    strict_artist_match: bool = False
    verify_by_artist_only: bool = False


@dataclass
class PlaybackVerification:
    success: bool
    current_name: str | None
    current_artist: str | None
    reason: str