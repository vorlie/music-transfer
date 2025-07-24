import os
import plistlib
import re
import csv
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple
from unidecode import unidecode
from rapidfuzz import fuzz
from ytmusicapi import YTMusic, OAuthCredentials

PLAYLISTS_DIR = Path("playlists")          
OAUTH_FILE = "oauth.json"
CLIENT_ID = os.getenv("YTMUSIC_CLIENT_ID")
CLIENT_SECRET = os.getenv("YTMUSIC_CLIENT_SECRET")

ACCEPT_TITLE_MIN = 88
ACCEPT_ARTIST_MIN = 75
ACCEPT_COMBINED_MIN = 85
SEARCH_RESULT_LIMIT_PER_QUERY = 6
ADD_CHUNK = 90
DRY_RUN = False  # set True to test without actually adding tracks

OUTPUT_DIR = Path("reports")
OUTPUT_DIR.mkdir(exist_ok=True)

yt = YTMusic(
    OAUTH_FILE,
    oauth_credentials=OAuthCredentials(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
)

_feat_pattern = re.compile(r'\s*(\(|\[)?feat\.?[^)\]]*(\)|\])?', re.IGNORECASE)

def load_plist(path: Path):
    with open(path, "rb") as f:
        return plistlib.load(f)

def extract_playlist_entries(root) -> List[dict]:
    """
    Returns a list of (playlist_name, track_dicts) for every playlist in this file.
    (Usually you expect just one, but we allow >1 for robustness.)
    """
    tracks_dict = root.get("Tracks", {})
    playlists = []
    for plist in root.get("Playlists", []):
        name = plist.get("Name")
        t_ids = [item["Track ID"] for item in plist.get("Playlist Items", [])]
        track_objs = []
        for tid in t_ids:
            t = tracks_dict.get(str(tid)) or tracks_dict.get(tid)
            if t:
                track_objs.append(t)
        if name and track_objs:
            playlists.append({"name": name, "tracks": track_objs})
    return playlists

def normalize_title(title: str) -> str:
    return unidecode(title).strip()

def base_title(title: str) -> str:
    t = _feat_pattern.sub("", title)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def primary_artist(artist_field: str) -> str:
    parts = re.split(r'[,/&]', artist_field)
    if parts:
        return parts[0].strip()
    return artist_field.strip()

def build_queries(track: dict) -> List[str]:
    title = (track.get("Name") or "").strip()
    artist = (track.get("Artist") or "").strip()
    bt = base_title(title)
    queries = [f"{title} {artist}"]
    if bt.lower() != title.lower():
        queries.append(f"{bt} {artist}")
    queries.append(title)
    if bt.lower() != title.lower():
        queries.append(bt)
    uniq, seen = [], set()
    for q in queries:
        key = q.lower()
        if key and key not in seen:
            seen.add(key)
            uniq.append(q)
    return uniq

def score_candidate(track: dict, candidate: dict) -> Tuple[float, float, float]:
    title = track.get("Name", "")
    artist = track.get("Artist", "")
    cand_title = candidate.get("title", "")
    cand_artists = " ".join(a['name'] for a in candidate.get("artists", []) or [])

    t_norm = normalize_title(title).lower()
    bt_norm = normalize_title(base_title(title)).lower()
    c_norm = normalize_title(cand_title).lower()
    a_norm = normalize_title(primary_artist(artist)).lower()
    cand_a_norm = normalize_title(primary_artist(cand_artists)).lower()

    title_score = max(
        fuzz.token_set_ratio(t_norm, c_norm),
        fuzz.token_set_ratio(bt_norm, c_norm)
    )
    artist_score = fuzz.partial_ratio(a_norm, cand_a_norm)
    combined = 0.6 * title_score + 0.4 * artist_score
    return title_score, artist_score, combined

def search_and_match(track: dict):
    queries = build_queries(track)
    best = None
    # store as (title_score, artist_score, combined)
    best_scores = (0.0, 0.0, 0.0)

    for q in queries:
        results = yt.search(q, filter="songs")
        if not results:
            results = yt.search(q)
        for r in results[:SEARCH_RESULT_LIMIT_PER_QUERY]:
            ts, as_, comb = score_candidate(track, r)
            # Small preference for songs
            comb_adj = comb + (0.5 if r.get("resultType") == "song" else 0.0)
            if comb_adj > best_scores[2] + 0.001:  # minor guard
                best = r
                best_scores = (ts, as_, comb)
            if ts >= 95 and as_ >= 85:
                return best, best_scores
    return best, best_scores

def is_accepted(scores: Tuple[float, float, float]) -> bool:
    ts, as_, comb = scores
    return (ts >= ACCEPT_TITLE_MIN and as_ >= ACCEPT_ARTIST_MIN) or comb >= ACCEPT_COMBINED_MIN

def find_or_create_playlist(name: str, description="Imported from Apple Music") -> str:
    existing = yt.get_library_playlists(limit=100)
    for pl in existing:
        if pl.get("title") == name:
            return pl["playlistId"]
    if DRY_RUN:
        return "DRY_RUN_PLAYLIST_ID"
    return yt.create_playlist(name, description, privacy_status="PRIVATE")

@dataclass
class MatchRecord:
    original_title: str
    original_artist: str
    matched_title: str
    matched_artists: str
    title_score: float
    artist_score: float
    combined_score: float
    video_id: str
    status: str  # MATCH / REVIEW / NO_RESULT

def process_playlist(playlist_name: str, tracks: List[dict]) -> List[MatchRecord]:
    print(f"\n=== Processing playlist: {playlist_name} ({len(tracks)} tracks) ===")
    records: List[MatchRecord] = []
    for t in tracks:
        m, scores = search_and_match(t)
        ts, as_, comb = scores
        if m:
            vid = m.get("videoId", "")
            artists_joined = " | ".join(a['name'] for a in m.get("artists", []) or [])
            status = "MATCH" if is_accepted(scores) else "REVIEW"
            label = "[MATCH]" if status == "MATCH" else "[REVIEW]"
            print(f"{label} {t.get('Name')} -> {m.get('title')} (T:{ts:.1f} A:{as_:.1f} C:{comb:.1f})")
            records.append(MatchRecord(
                original_title=t.get("Name",""),
                original_artist=t.get("Artist",""),
                matched_title=m.get("title",""),
                matched_artists=artists_joined,
                title_score=ts,
                artist_score=as_,
                combined_score=comb,
                video_id=vid,
                status=status
            ))
        else:
            print(f"[NO RESULT] {t.get('Name')}")
            records.append(MatchRecord(
                original_title=t.get("Name",""),
                original_artist=t.get("Artist",""),
                matched_title="",
                matched_artists="",
                title_score=0,
                artist_score=0,
                combined_score=0,
                video_id="",
                status="NO_RESULT"
            ))
    return records

def add_tracks_to_yt_playlist(playlist_id: str, records: List[MatchRecord]):
    video_ids = [r.video_id for r in records if r.status == "MATCH" and r.video_id]
    if DRY_RUN:
        print(f"[DRY RUN] Would add {len(video_ids)} tracks.")
        return
    for i in range(0, len(video_ids), ADD_CHUNK):
        chunk = video_ids[i:i+ADD_CHUNK]
        yt.add_playlist_items(playlist_id, chunk)
        print(f"Added {len(chunk)} tracks (chunk {i//ADD_CHUNK + 1}).")

def write_playlist_report(playlist_name: str, records: List[MatchRecord]):
    safe_name = re.sub(r'[^A-Za-z0-9._-]+','_', playlist_name).strip('_') or "playlist"
    report_file = OUTPUT_DIR / f"{safe_name}.csv"
    with open(report_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Original Title","Original Artist","Matched Title","Matched Artist(s)",
                         "TitleScore","ArtistScore","CombinedScore","VideoId","Status"])
        for r in records:
            writer.writerow([
                r.original_title, r.original_artist, r.matched_title, r.matched_artists,
                f"{r.title_score:.1f}", f"{r.artist_score:.1f}", f"{r.combined_score:.1f}",
                r.video_id, r.status
            ])
    print(f"Report written: {report_file}")

def main():
    if not PLAYLISTS_DIR.is_dir():
        raise SystemExit(f"Folder '{PLAYLISTS_DIR}' not found.")

    all_records_master: List[Tuple[str, MatchRecord]] = []

    xml_files = sorted(PLAYLISTS_DIR.glob("*.xml"))
    if not xml_files:
        print("No XML files found in 'playlists/'")
        return

    for xml_path in xml_files:
        print(f"\n>>> Reading file: {xml_path.name}")
        try:
            root = load_plist(xml_path)
        except Exception as e:
            print(f"Failed to parse {xml_path.name}: {e}")
            continue

        playlist_entries = extract_playlist_entries(root)
        if not playlist_entries:
            # fallback: use filename as playlist name if structure is unusual
            print(f"No playlist objects found in {xml_path.name}; skipping.")
            continue

        for entry in playlist_entries:
            pl_name = entry["name"]
            records = process_playlist(pl_name, entry["tracks"])
            playlist_id = find_or_create_playlist(pl_name)
            add_tracks_to_yt_playlist(playlist_id, records)
            write_playlist_report(pl_name, records)
            all_records_master.extend((pl_name, r) for r in records)

    # Master summary CSV (optional)
    if all_records_master:
        master_file = OUTPUT_DIR / "all_playlists_summary.csv"
        with open(master_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Playlist","Original Title","Original Artist","Matched Title",
                             "Matched Artist(s)","TitleScore","ArtistScore","CombinedScore","VideoId","Status"])
            for pl_name, r in all_records_master:
                writer.writerow([
                    pl_name, r.original_title, r.original_artist, r.matched_title,
                    r.matched_artists, f"{r.title_score:.1f}", f"{r.artist_score:.1f}",
                    f"{r.combined_score:.1f}", r.video_id, r.status
                ])
        print(f"\nMaster summary: {master_file}")

    print("\nDone.")

if __name__ == "__main__":
    main()
