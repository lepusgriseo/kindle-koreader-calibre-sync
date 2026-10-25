# kindle-koreader-calibre-sync

Copy what you have read on a Kindle running **[KOReader](https://koreader.rocks/)** into your
**[Calibre](https://calibre-ebook.com/)** library: progress, reading status, start and finish
dates, time spent reading, star ratings, reviews, highlights and bookmarks. It works with the
newer Kindles that only connect over MTP, which the usual Calibre plugins cannot read.

Two scripts:

| Script | Language | What it does |
| --- | --- | --- |
| **`kosync`** | Python 3, standard library only | Reads KOReader's data off the Kindle and writes it into Calibre custom columns. This does the actual sync. |
| **`kindle`** | Bash | A menu (and subcommands) for Linux desktops that use gvfs. It shows the Kindle's state, mounts it, runs `kosync`, and switches the Kindle between "readable by kosync" and "usable by Calibre". |

> The name `kosync` is unrelated to KOReader's own *Progress sync* plugin and server, which share it.
> This script only reads from the Kindle and only writes to Calibre.

---

## Contents

- [What gets synced](#what-gets-synced)
- [Platform support](#platform-support)
- [Requirements](#requirements)
- [Installation](#installation)
- [Using kosync](#using-kosync)
- [Using kindle](#using-kindle-the-linux-menu)
- [How books are matched](#how-books-are-matched)
- [Safety](#safety)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [How it works](#how-it-works)
- [Running the tests](#running-the-tests)
- [Licence](#licence)

---

## What gets synced

`kosync` creates these custom columns the first time it runs (via `calibredb add_custom_column`),
then fills them for every book it can match:

| Column | Type | Contents | Source on the Kindle |
| --- | --- | --- | --- |
| `#ko_progfloat` — KOReader Precise Progress | float | Percent read, two decimals (`43.21`) | sidecar `percent_finished` |
| `#ko_progint` — KOReader Progress | integer | Percent read, whole number (`43`) | sidecar |
| `#ko_status` — KOReader Book Status | text | `reading`, `complete`, `abandoned`… as KOReader records it | sidecar `summary.status` |
| `#ko_statusbool` — KOReader Book Status Y/N | yes/no | Yes when the book is marked complete | sidecar |
| `#ko_loc` — KOReader Last Location | text | KOReader's last position (an xpointer or page) | sidecar |
| `#ko_start` — Date KOReader Started | date | First reading session, or failing that the first highlight | statistics database, annotations |
| `#ko_finish` — Date KOReader Finished | date | When the book was marked complete | sidecar, statistics database |
| `#ko_review` — KOReader Review | long text (HTML) | The review written in KOReader's book status screen | sidecar `summary.note` |
| `#koreader_highlights` — KOReader Highlights | long text (HTML) | Every highlight, grouped under its chapter, with page, date, colour and any note | sidecar / `*.annotations.lua` |
| `#ko_bookmarks` — KOReader Bookmarks | long text (HTML) | Page bookmarks (dog-ears), with chapter and date | sidecar / `*.annotations.lua` |
| `#ko_readtime` — KOReader Reading Time | integer | Minutes spent reading | statistics database |
| `#ko_readpages` — KOReader Pages Read | integer | Pages read | statistics database |

It also sets Calibre's own **rating** from KOReader's 1–5 stars (Calibre counts half stars, so
4 stars is stored as 8).

A book marked **complete** in KOReader is written as 100% even if the last page wasn't reached.

Besides updating books already in Calibre, `kosync` **imports books you sideloaded onto the Kindle**
that are not yet in the library (turn this off with `--no-add`). The book file is copied off the
device and added with `calibredb add`, and its reading data follows.

---

## Platform support

| Platform | `kosync` | `kindle` |
| --- | --- | --- |
| **Linux with gvfs** (GNOME, Cinnamon, MATE, Xfce, Budgie…) | ✅ **Supported and tested.** Finds the Kindle on its own, whether it is mounted over MTP or as a USB drive. | ✅ **Supported and tested.** |
| **Linux without gvfs** (KDE Plasma and others) | ⚠️ **Should work, untested.** KDE's MTP support doesn't expose a folder other programs can read. Mount the Kindle with gvfs (`gio mount`, if `gvfs-mtp` is installed) or a FUSE MTP tool, then pass the folder with `--device`. A Kindle that mounts as a USB drive is found on its own. | ❌ Needs gvfs. |
| **macOS** | ⚠️ **Untested.** An older Kindle that mounts as a USB drive should work with `--device /Volumes/Kindle`, if `calibredb` is on your `PATH` (it is in `/Applications/calibre.app/Contents/MacOS/`). macOS has no built-in way to mount an MTP-only Kindle as a folder, so newer Kindles would need a third-party MTP filesystem. | ❌ Linux only. |
| **Windows** | ❌ **Not supported.** Windows doesn't give MTP devices a folder path, and `kosync` uses `ps` to check whether Calibre is open. | ❌ Linux only. |

**Tested on:** Fedora Linux 44 (GNOME, gvfs-mtp 1.60), Python 3.14, Calibre 9.13 (Flathub
Flatpak), with a Kindle Paperwhite Signature Edition that connects over MTP only.

**Kindles.** Any Kindle running KOReader. Newer models connect over MTP only, so they appear in
the file manager rather than as a drive. Older ones mount as a USB drive. `kosync` handles both.

**Calibre.** Works with Calibre installed from your distribution or the official installer
(`calibredb` on the `PATH`), or with the Flathub Flatpak (`com.calibre_ebook.calibre`), which
`kosync` detects and runs through `flatpak run`.

---

## Requirements

- **A Kindle with KOReader installed.** On a Kindle, that needs a jailbreak. `kosync` reads
  KOReader's files, not Amazon's own reader. It expects the usual layout: books under
  `documents/`, KOReader in `koreader/`.
- **KOReader's reading statistics plugin** enabled (it is on by default). Without it you still get
  progress, status, highlights and bookmarks, but not reading time, pages read or start dates.
- **Python 3.8 or newer.** Standard library only, nothing to `pip install`.
- **Calibre**, with its `calibredb` command line tool (see above).
- For the `kindle` menu: **Bash 4+, gvfs with MTP support** (`gvfs-mtp` / `gvfs-backends`),
  `gio`, `pgrep`/`pkill`, and `sudo` rights for switching modes.

---

## Installation

```bash
git clone https://github.com/lepusgriseo/kindle-koreader-calibre-sync.git
cd kindle-koreader-calibre-sync
install -m 755 kosync kindle ~/.local/bin/     # or ~/bin, or anywhere on your PATH
```

`kindle` calls `kosync` by name, so both need to be on your `PATH`.

The first run creates the twelve custom columns in your library. To show them in Calibre, right-click
the column headers in the book list and tick the ones you want.

---

## Using kosync

1. **Quit Calibre.** `calibredb` refuses to write to a library that the Calibre window has open.
   `kosync` checks this and stops with a message rather than failing halfway.
2. **Connect the Kindle and unlock it.** On Linux with gvfs it appears in the file manager. Over
   MTP it mounts under `/run/user/<uid>/gvfs/`, which `kosync` searches; a USB-drive Kindle under
   `/run/media/<user>/` or `/media/` is found too.
3. Run it:

```bash
kosync --dry-run      # preview: what would be synced or imported, nothing written (safe with Calibre open)
kosync                # sync
kosync -v             # sync, with a line per book
```

Typical output:

```
Device:  /run/user/1000/gvfs/mtp:host=Amazon_Kindle_.../Internal Storage
Library: /home/you/Calibre Library
Staging KOReader data off the device...
Backup:  /home/you/.cache/kosync/backups/metadata-20261025-101500.db
Found 82 sidecars and 97 books with reading statistics.

Synced: 75 book(s)
Imported: 7 new book(s)

No Calibre match (23) - these were left alone:
  - Daily News 2026-10-20
  ...
```

### Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--library PATH` | `~/Calibre Library` | The Calibre library to update. |
| `--device PATH` | found automatically | The Kindle's root: the folder holding `documents/` and `koreader/`. Use it when auto-detection fails, or on platforms other than Linux. |
| `--dry-run` | off | Report what would change. Nothing is written to Calibre and no backup is made. Safe while Calibre is open. |
| `--no-add` | off | Don't import sideloaded books that aren't in the library. They are listed as unmatched instead. |
| `--min-seconds N` | `0` | Skip books that KOReader only has statistics for (no sidecar left on the device) when they were open for less than *N* seconds. Books opened by accident then stay out of Calibre. Books with a sidecar always sync. |
| `-v`, `--verbose` | off | One line per book: the Calibre id, progress, status, reading time, highlight count and how it was matched. |

Running it again is safe. Each run writes the current KOReader values over the previous ones, so a
second run with no reading in between changes nothing.

---

## Using kindle (the Linux menu)

An MTP device can only be held by **one program at a time**. On Linux that is normally gvfs, which
mounts the Kindle in the file manager. That is what `kosync` needs, but it also stops Calibre
from opening the Kindle to send books to it. `kindle` switches between the two:

| Mode | gvfs MTP | You can… | You can't… |
| --- | --- | --- | --- |
| **gvfs** (normal) | on | browse the Kindle in Files, run `kosync` | open the Kindle in Calibre |
| **calibre** | off | send books to the Kindle from Calibre | run `kosync`, browse it in Files |

```
$ kindle
Kindle — Kindle Paperwhite
  Mode:     gvfs (Files + kosync; Calibre can't open it)
  USB:      connected
  Mounted:  yes /run/user/1000/gvfs/mtp:host=Amazon_Kindle_Paperwhite_...
  Calibre:  not running

  1) Sync reading progress into Calibre     kosync
  2) Preview a sync (writes nothing)        kosync --dry-run
  3) Switch to Calibre mode  (manage books in Calibre)
  4) Switch to gvfs mode     (Files + kosync)
  5) Mount the Kindle now
  6) Refresh status
  q) Quit
```

Or skip the menu:

| Command | What it does |
| --- | --- |
| `kindle status` | Mode, whether the Kindle is on USB, where it's mounted, whether Calibre is running. |
| `kindle sync [kosync options]` | Checks the mode and that Calibre is closed, mounts the Kindle if needed, then runs `kosync` with any options you add (`kindle sync --dry-run -v`). |
| `kindle calibre` | Switch to calibre mode (asks for `sudo`). |
| `kindle gvfs` | Switch back to gvfs mode (asks for `sudo`). |
| `kindle mount` | Mount the Kindle over gvfs now, without opening Files. |
| `kindle help` | Usage. |

**Replug the Kindle after every mode switch.** Some Kindles drop their USB connection when an MTP
session ends and don't reconnect on their own.

Switching modes renames `/usr/share/gvfs/remote-volume-monitors/mtp.monitor` to
`mtp.monitor.disabled` and back, which is why it needs `sudo`, and it stops the running gvfs MTP
processes. It affects every MTP device on the machine (phones too) while in calibre mode.
`kindle` finds the Kindle by Amazon's USB vendor id (`1949`) and builds the gvfs address from the
device's USB descriptors.

---

## How books are matched

Each book KOReader knows about is matched to a Calibre book in this order. The first match wins:

1. **Calibre's id in the filename.** Books Calibre sends to a device are named
   `Title - Author (123).epub`. The id is used only if that Calibre book's title and author agree
   with the file: an id goes stale when a book is removed and added again, and can later belong
   to a different book.
2. **Title and author.** Titles are compared ignoring case, accents, punctuation, a leading
   "The/A/An", and `&` versus `and`. Authors only need to share a name, and spelling variants
   (Dostoyevsky / Dostoevsky) count as agreeing.
3. **Title without its subtitle**, so `Animal Farm` finds `Animal Farm: A Fairy Story`.
4. **A close fuzzy match** on the title (similarity ≥ 0.88) whose authors don't disagree.
5. **A run-together filename**, such as `Dracula-Bram-Stoker.epub`. The leading words must form a
   Calibre title and the remaining words must name that book's author.
6. **Import**, for a sideloaded book file with no match (unless `--no-add`).

If two records turn out to be the same Calibre book (a sidecar plus a statistics row, or the same
book read under two filenames), they are merged. Reading time and progress keep the larger value,
the start date the earlier one, the finish date the later one, and text the longer version.

Anything still unmatched is **listed and left alone**, never guessed. That is typically news or RSS
downloads, PDFs with meaningless names, and books that aren't in the library.

---

## Safety

- **The Kindle is only read.** Its files are copied to `~/.cache/kosync/` first. All parsing
  happens on those copies, which also avoids MTP's slow and occasionally dropped reads.
- **Calibre's database is backed up before every write**, to
  `~/.cache/kosync/backups/metadata-<timestamp>.db`, keeping the five most recent. To undo a run,
  quit Calibre and copy a backup over `metadata.db` in your library folder.
- **Writes go through `calibredb`**, Calibre's own tool, never straight into the database.
- **It refuses to run while Calibre is open**, except for `--dry-run`.
- **`--dry-run`** shows everything a real run would do, including which books it would import.
- **It only writes its own columns, plus the rating.** Titles, authors, tags and other metadata are
  never touched.

---

## Troubleshooting

**`error: Calibre is running`**
Quit Calibre, including any content server, and try again. `kosync --dry-run` works with Calibre
open.

**`error: no Kindle found`**
Unlock the Kindle and check it appears in your file manager. Over MTP, open it once in Files so
gvfs mounts it, or run `kindle mount`. If it still isn't found, point at it directly:
`kosync --device "/run/user/1000/gvfs/mtp:host=…/Internal Storage"`.

**Calibre can't open the Kindle: `libusb_claim_interface() … busy … in use by GVFS`**
gvfs is holding the MTP connection. Run `kindle calibre`, then replug the Kindle. Run `kindle gvfs`
when you want to sync again.

**`kindle` says the mode is `unknown`**
Neither `mtp.monitor` nor `mtp.monitor.disabled` exists in `/usr/share/gvfs/remote-volume-monitors/`.
A gvfs package update can reinstall `mtp.monitor` (putting you back in gvfs mode) or rename things.
Check that folder.

**`error: calibredb not found`**
Install Calibre, or put the folder containing `calibredb` on your `PATH`. The Flatpak is found on
its own.

**A book was matched to the wrong Calibre entry**
Restore the backup from before that run (see [Safety](#safety)). Then rename the book on the
Kindle, or fix its title or author in Calibre so they agree, and run again. Please open an issue
with the `-v` line for that book.

**Reading time or start dates are missing**
Enable KOReader's *Reading statistics* plugin. Time read before it was enabled can't be recovered.

---

## Limitations

- One way only: Kindle → Calibre. Nothing is written to the Kindle, and Calibre's data isn't sent
  back to KOReader.
- Only KOReader's data. Amazon's own reader keeps its progress and highlights elsewhere.
- One Kindle at a time. With two plugged in, the first one found is used; choose with `--device`.
- KOReader's statistics database identifies books by a partial MD5 of the file. A book replaced by
  a different file (a new edition) starts a new statistics entry.
- A record that KOReader keeps only in its statistics database, with no sidecar on the device,
  carries reading time, pages and dates, but no progress, status or highlights.

---

## How it works

1. **Find the Kindle.** Search gvfs MTP mounts and removable-drive mounts for a folder holding both
   `documents/` and `koreader/`, at the top level or inside `Internal Storage/`.
2. **Stage.** Copy `koreader/settings/statistics.sqlite3` and every `*.sdr/metadata.*.lua` and
   `*.annotations.lua` sidecar into `~/.cache/kosync/`.
3. **Parse.** Sidecars are KOReader's Lua tables (`return { … }`), read with a small parser built
   into the script, so no Lua is needed. It understands KOReader's `%q` string escapes, nested
   tables, numbers, booleans and `nil`. The statistics database is read with `sqlite3` in read-only
   mode.
4. **Combine.** Each sidecar is joined to its statistics row by KOReader's partial MD5. Books with
   statistics but no sidecar (deleted from the device) are kept too.
5. **Match.** See [How books are matched](#how-books-are-matched).
6. **Write.** One `calibredb set_metadata` call per Calibre book, after a backup.

KOReader stores highlights and page bookmarks in the same list; a highlight carries a selected
range (`pos0`/`pos1`) and a bookmark doesn't, which is how they are told apart.

---

## Running the tests

```bash
python3 -m unittest discover tests
```

The tests cover the Lua parser, highlight and bookmark handling, title and author matching
(including the stale-id rule), the fields written to Calibre, and staging from a fake device.
They need nothing beyond the Python standard library, and don't need Calibre or a Kindle.

---

## Licence

[MIT](LICENSE).
