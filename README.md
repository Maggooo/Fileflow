# 📁 FileFlow

> A file organizer with a modern web UI — zero external dependencies, single Python file.

![Python](https://img.shields.io/badge/python-3.8+-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Zero deps](https://img.shields.io/badge/dependencies-zero-purple?style=flat-square)
![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey?style=flat-square)

---

## What it does

FileFlow scans a source folder and automatically organizes files by **extension → year → month**, using the file's actual creation date.

```
Source/
├── photo.jpg
├── report.pdf
└── clip.mp4

Destination/
├── jpg/
│   └── 2024/
│       └── 03-March/
│           └── photo.jpg
├── pdf/
│   └── 2023/
│       └── 11-November/
│           └── report.pdf
└── mp4/
    └── 2024/
        └── 01-January/
            └── clip.mp4
```

---

## Features

- **Modern web UI** — opens automatically in your browser, no installation needed
- **Copy or move** — choose what happens to the originals
- **Filter by extension** — include only `jpg png pdf` or exclude `tmp log`
- **Delete small files** — configurable size threshold (e.g. under 50 KB), with optional backup
- **Duplicate detection** — via MD5 hash, skips identical files
- **Filename conflict resolution** — automatically appends a suffix if the file already exists
- **Dry-run mode** — full simulation with no actual changes made
- **Live progress bar** — real-time updates as files are processed
- **Interactive report** — filterable and sortable table of all operations performed
- **Zero dependencies** — uses only the Python standard library

---

## Getting started

### Requirements

- Python 3.8+
- Nothing else

### Run

```bash
# Clone the repo
git clone https://github.com/USERNAME/fileflow.git
cd fileflow

# Start
python3 organizator.py
```

Your browser opens automatically at `http://127.0.0.1:7491`.

### Linux — clean terminal output (suppress GPU/browser noise)

```bash
python3 organizator.py 2>/dev/null
```

### Stop

Press `Ctrl+C` in the terminal.

---

## How it works

FileFlow spins up a minimal HTTP server using Python's built-in `http.server`, serves the entire web UI as inline HTML/CSS/JS, and exposes three endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the web interface |
| `/start` | POST | Receives config and starts organizing in a background thread |
| `/progress` | GET | Returns current state (progress + result) |

The UI polls `/progress` every 400ms until the job is complete.

---

## Repository structure

```
fileflow/
├── organizator.py   # everything — server + logic + UI
├── README.md
├── LICENSE
└── .gitignore
```

---

## License

MIT — see [LICENSE](LICENSE)
