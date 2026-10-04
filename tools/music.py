from music.playback import play_music_premium


def play_music_any(query: str) -> bool:
    query = (query or "").strip()

    if not query:
        print("⚠️ Empty music query")
        return False

    print(f"🎵 Trying to play: {query}")

    try:
        ok = play_music_premium(query)

        if ok:
            print("🎵 Playback success")
            return True

        print("⚠️ Premium playback failed")
        return False

    except Exception as e:
        print(f"❌ Music error: {e}")
        return False