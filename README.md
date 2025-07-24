# Music Transfer

This project helps you import, match, and report on music playlists from various sources. It processes playlist files (e.g., XML), matches tracks to online resources (such as YouTube), and generates summary reports in CSV format.

## Features

- Import playlists from XML files.
- Match tracks to online resources (YouTube Video IDs).
- Generate detailed CSV reports for each playlist.
- Summarize all playlists in a single CSV file.

## Prerequisites

- Python 3.7+
- pip (Python package manager)

## Setup

1. **Clone the repository**  
   ```sh
   git clone <your-repo-url>
   cd music-transfer
   ```

2. **Install dependencies**  
   ```sh
   pip install -r requirements.txt
   ```

3. **Prepare your data**  
   - Place your playlist XML files in the `playlists/` directory.
   - Ensure you have the necessary credentials in `oauth.json` (if required for API access).

## Usage

### Import Music

To import and process playlists, run:

```sh
python import_music.py
```

This will read playlists from the `playlists/` folder, match tracks, and generate reports in the `reports/` folder.

### View Results

- Individual playlist reports: `reports/<playlist_name>.csv`
- Summary of all playlists: `reports/all_playlists_summary.csv`

### Custom Scripts

You can also run custom scripts, such as:

```sh
python script.py
```

Refer to the script for specific functionality.

## File Structure

- `playlists/` — Source playlist files (XML)
- `reports/` — Generated CSV reports
- `import_music.py` — Main import and matching script
- `requirements.txt` — Python dependencies
- `oauth.json` — API credentials (if needed)
- `setup.py` — Project setup (optional)

## Example Output

Each report contains columns like:

- Playlist
- Original Title
- Original Artist
- Matched Title
- Matched Artist(s)
- TitleScore, ArtistScore, CombinedScore
- VideoId
- Status (MATCH/REVIEW)