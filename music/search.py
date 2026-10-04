import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from music.models import ParsedQuery, SearchDecision

DATA_FILE = Path(__file__).with_name("artist_aliases.json")

DEFAULT_ARTIST_ALIASES = {
    "the weeknd": "The Weeknd",
    "weeknd": "The Weeknd",
    "the weekend": "The Weeknd",
    "weekend": "The Weeknd",
    "kendric lamar": "Kendrick Lamar",
    "travis scot": "Travis Scott",
    "post malon": "Post Malone",
}

DEFAULT_KNOWN_ARTISTS = [
    "The Weeknd", "Drake", "Taylor Swift", "Kendrick Lamar", "Travis Scott",
    "Post Malone", "Billie Eilish", "Ariana Grande", "Ed Sheeran", "Rihanna",
    "Beyonce", "Justin Bieber", "SZA", "Dua Lipa", "Doja Cat",
    "Bruno Mars", "Bad Bunny", "J Balvin", "Karol G", "Shakira",
]

def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _load_artist_data() -> tuple[list[str], dict[str, str]]:
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)

        known = data.get("known_artists", [])
        aliases = data.get("aliases", {})

        known_artists = [str(a).strip() for a in known if str(a).strip()]
        artist_aliases = {
            str(alias).strip().lower(): str(canonical).strip()
            for alias, canonical in aliases.items()
            if str(alias).strip() and str(canonical).strip()
        }

        if known_artists:
            return known_artists, artist_aliases
    except Exception:
        pass

    return DEFAULT_KNOWN_ARTISTS, DEFAULT_ARTIST_ALIASES


def _init_artist_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for artist in KNOWN_ARTISTS:
        mapping[normalize_text(artist)] = artist
    for alias, canonical in ARTIST_ALIASES.items():
        mapping[normalize_text(alias)] = canonical
    return mapping


KNOWN_ARTISTS, ARTIST_ALIASES = _load_artist_data()
KNOWN_ARTIST_NORMALIZED = _init_artist_map()


def _apply_common_stt_corrections(text: str) -> str:
    """Swap known misheard artist aliases (e.g. "kendric lamar") for their
    canonical spelling, preserving the surrounding text's case and
    punctuation so song titles aren't mangled."""
    corrected = text or ""
    for alias, canonical in ARTIST_ALIASES.items():
        if alias:
            corrected = re.sub(rf"\b{re.escape(alias)}\b", canonical, corrected, flags=re.IGNORECASE)

    return corrected.strip()


def _closest_artist(text: str, threshold: float = 0.84) -> str | None:
    candidate = normalize_text(text)
    if not candidate:
        return None

    if candidate in KNOWN_ARTIST_NORMALIZED:
        return KNOWN_ARTIST_NORMALIZED[candidate]

    best_name = None
    best_score = 0.0
    for normalized_name, canonical in KNOWN_ARTIST_NORMALIZED.items():
        score = SequenceMatcher(None, candidate, normalized_name).ratio()
        if score > best_score:
            best_score = score
            best_name = canonical

    if best_name and best_score >= threshold:
        return best_name
    return None


def _looks_like_artist_query(text: str) -> bool:
    n = normalize_text(text)
    if not n:
        return False
    if len(n.split()) > 4:
        return False
    return not any(token in n for token in ["remix", "version", "feat", "featuring", "live", "acoustic"])


def _clean_query(query: str) -> str:
    q = (query or "").strip()
    q = q.strip('"').strip("'")

    q = re.sub(r"^\s*play\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^\s*the\s+song\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^\s*song\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^\s*some\s+music\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^\s*music\s+", "", q, flags=re.IGNORECASE)

    return q.strip()


def parse_song_and_artist(query: str) -> ParsedQuery:
    q = _clean_query(query)
    q = _apply_common_stt_corrections(q) or q

    artist_only_patterns = [
        r"^(songs?|music)\s+by\s+(.+)$",
        r"^artist\s+(.+)$",
        r"^by\s+(.+)$",
    ]

    for pattern in artist_only_patterns:
        match = re.match(pattern, q, flags=re.IGNORECASE)
        if match:
            artist = (
                match.group(2)
                if match.lastindex and match.lastindex >= 2
                else match.group(1)
            ).strip().strip('"').strip("'")
            artist = _closest_artist(artist) or artist
            return ParsedQuery(
                raw_query=q,
                song=artist,
                artist=artist or None,
                intent="artist",
                song_normalized=normalize_text(artist),
                artist_normalized=normalize_text(artist),
            )

    parts = re.split(r"\s+by\s+", q, maxsplit=1, flags=re.IGNORECASE)

    if len(parts) == 2:
        song = parts[0].strip().strip('"').strip("'")
        artist = parts[1].strip().strip('"').strip("'")
        artist = _closest_artist(artist) or artist
        return ParsedQuery(
            raw_query=q,
            song=song or q,
            artist=artist or None,
            intent="song",
            song_normalized=normalize_text(song or q),
            artist_normalized=normalize_text(artist or ""),
        )

    canonical_artist = _closest_artist(q) if _looks_like_artist_query(q) else None

    if canonical_artist:
        return ParsedQuery(
            raw_query=q,
            song=canonical_artist,
            artist=canonical_artist,
            intent="artist",
            song_normalized=normalize_text(canonical_artist),
            artist_normalized=normalize_text(canonical_artist),
        )

    return ParsedQuery(
        raw_query=q,
        song=q,
        artist=None,
        intent="song",
        song_normalized=normalize_text(q),
        artist_normalized=None,
    )


def build_search_decision(parsed: ParsedQuery) -> SearchDecision:
    if parsed.intent == "artist" and parsed.artist:
        return SearchDecision(
            should_try_library=False,
            should_try_catalog_ui=True,
            strict_artist_match=True,
            verify_by_artist_only=True,
            reason="Artist intent detected; prioritize Apple Music catalog and verify by artist.",
        )

    has_artist = bool(parsed.artist and parsed.artist.strip())

    return SearchDecision(
        should_try_library=True,
        should_try_catalog_ui=True,
        strict_artist_match=has_artist,
        reason=(
            "Artist specified; use stricter verification and catalog fallback."
            if has_artist
            else "Song-only query; try library first, then catalog UI fallback."
        ),
    )