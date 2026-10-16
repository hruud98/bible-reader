#!/usr/bin/env python3
"""Fetch + align any Hebrew Bible chapter.

For a given book/chapter this:
  1. Scrapes the BibleHub interlinear (Hebrew text, translit, gloss, parsing).
  2. Downloads the Mechon-Mamre cantillated audio and converts it to a
     seek-accurate mono WAV.
  3. Runs torchaudio MMS_FA neural forced alignment (uroman romanization) to
     produce per-word begin/end timestamps aligned 1:1 with the words.

Results are cached under web/chapters/<slug>/ as data.json, word_times.json and
audio.wav, with a manifest at web/chapters/index.json.
"""
import html as _html
import json
import os
import re
import subprocess
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "..", "web")
CHAPTERS = os.path.join(WEB, "chapters")
INDEX = os.path.join(CHAPTERS, "index.json")

UA = {"User-Agent": "Mozilla/5.0 (bible-reader)"}

# Catalog of books that have Mechon-Mamre audio. Each entry:
#   (book id/slug, display name, mechon code, biblehub slug, chapter count)
# Audio URL is https://mechon-mamre.org/mp3/t<code><CC>.mp3 (CC = 2-digit
# chapter). Two-part books use a letter-suffixed code (e.g. 1 Kings = "09a").
# All of these are single BibleHub books with matching chapter numbers.
BOOKS = [
    ("genesis", "Genesis", "01", "genesis", 50),
    ("exodus", "Exodus", "02", "exodus", 40),
    ("leviticus", "Leviticus", "03", "leviticus", 27),
    ("numbers", "Numbers", "04", "numbers", 36),
    ("deuteronomy", "Deuteronomy", "05", "deuteronomy", 34),
    ("joshua", "Joshua", "06", "joshua", 24),
    ("judges", "Judges", "07", "judges", 21),
    ("1_samuel", "1 Samuel", "08a", "1_samuel", 31),
    ("2_samuel", "2 Samuel", "08b", "2_samuel", 24),
    ("1_kings", "1 Kings", "09a", "1_kings", 22),
    ("2_kings", "2 Kings", "09b", "2_kings", 25),
    ("isaiah", "Isaiah", "10", "isaiah", 66),
    ("jeremiah", "Jeremiah", "11", "jeremiah", 52),
    ("ezekiel", "Ezekiel", "12", "ezekiel", 48),
    ("hosea", "Hosea", "13", "hosea", 14),
    ("joel", "Joel", "14", "joel", 4),
    ("amos", "Amos", "15", "amos", 9),
    ("obadiah", "Obadiah", "16", "obadiah", 1),
    ("jonah", "Jonah", "17", "jonah", 4),
    ("micah", "Micah", "18", "micah", 7),
    ("nahum", "Nahum", "19", "nahum", 3),
    ("habakkuk", "Habakkuk", "20", "habakkuk", 3),
    ("zephaniah", "Zephaniah", "21", "zephaniah", 3),
    ("haggai", "Haggai", "22", "haggai", 2),
    ("zechariah", "Zechariah", "23", "zechariah", 14),
    ("malachi", "Malachi", "24", "malachi", 3),
    ("1_chronicles", "1 Chronicles", "25a", "1_chronicles", 29),
    ("2_chronicles", "2 Chronicles", "25b", "2_chronicles", 36),
    ("psalms", "Psalms", "26", "psalms", 99),
    ("job", "Job", "27", "job", 42),
    ("proverbs", "Proverbs", "28", "proverbs", 31),
    ("ruth", "Ruth", "29", "ruth", 4),
    ("song_of_songs", "Song of Songs", "30", "songs", 8),
    ("ecclesiastes", "Ecclesiastes", "31", "ecclesiastes", 12),
    ("lamentations", "Lamentations", "32", "lamentations", 5),
    ("esther", "Esther", "33", "esther", 10),
    ("daniel", "Daniel", "34", "daniel", 12),
    ("ezra", "Ezra", "35a", "ezra", 10),
    ("nehemiah", "Nehemiah", "35b", "nehemiah", 13),
]
BOOK_BY_ID = {b[0]: b for b in BOOKS}

# Serialize heavy work: the alignment model is not safe to run concurrently.
_LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# Interlinear scraping (BibleHub)
# --------------------------------------------------------------------------- #
def _clean(s):
    s = _html.unescape(s)
    s = s.replace("\u2011", "-").replace("\u00a6", "|").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)


def scrape_interlinear(bh_slug, chapter):
    url = f"https://biblehub.com/interlinear/{bh_slug}/{chapter}.htm"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode("utf-8", "replace")

    parts = raw.split('class="tablefloatheb"')
    words = []
    cur_verse = 0
    for block in parts[1:]:
        heb = re.search(r'class="hebrew">([^<]+)</span>', block)
        if not heb:
            continue
        verse = re.search(r'class="reftop">(?:&nbsp;|\s)*(\d+)', block)
        if verse:
            cur_verse = int(verse.group(1))
        translit = re.search(r'class="translit">(.*?)</span>', block, re.S)
        eng = re.search(r'class="eng">(.*?)</span>', block, re.S)
        parse = re.search(
            r'href="/hebrewparse\.htm"\s+title="([^"]*)"[^>]*>(.*?)</a>', block, re.S
        )
        words.append(
            {
                "verse": cur_verse,
                "heb": _clean(heb.group(1)),
                "translit": _clean(_strip_tags(translit.group(1))) if translit else "",
                "gloss": _clean(_strip_tags(eng.group(1))) if eng else "",
                "parse": _clean(_strip_tags(parse.group(2))) if parse else "",
                "parseFull": _clean(parse.group(1)) if parse else "",
            }
        )
    if not words:
        raise RuntimeError(f"No words parsed from {url}")
    return words


# --------------------------------------------------------------------------- #
# Audio download (Mechon-Mamre) -> seek-accurate WAV
# --------------------------------------------------------------------------- #
def download_audio(mechon_code, chapter, out_wav):
    url = f"https://mechon-mamre.org/mp3/t{mechon_code}{chapter:02d}.mp3"
    tmp_mp3 = out_wav + ".src.mp3"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp_mp3, "wb") as f:
            f.write(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Audio not available ({url}): HTTP {e.code}") from e
    subprocess.run(
        ["ffmpeg", "-nostats", "-hide_banner", "-y", "-i", tmp_mp3,
         "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", out_wav],
        check=True,
        capture_output=True,
    )
    os.remove(tmp_mp3)
    return url


# --------------------------------------------------------------------------- #
# Forced alignment (torchaudio MMS_FA + uroman) -- loaded lazily
# --------------------------------------------------------------------------- #
_CANT = re.compile("[\u0591-\u05AF\u05BD\u05BE\u05C0\u05C3\u05C6]")
_CHUNK_SECONDS = 40  # forward-pass window; whole-file passes thrash memory
_ali = {}


def _load_aligner():
    """Load the MMS_FA model + helpers once and reuse across chapters.

    The conv forward pass runs on Apple's MPS GPU when available (~3x faster);
    the cheap CTC forced-align step always runs on CPU (no MPS kernel).
    """
    if _ali:
        return _ali
    import torch
    import torchaudio
    import torchaudio.functional as F
    import uroman as ur
    from ctc_forced_aligner import (
        align as fa_align,
        load_audio,
        load_transcript,
        unflatten,
        _postprocess_results,
    )

    bundle = torchaudio.pipelines.MMS_FA
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    _ali.update(
        torch=torch,
        F=F,
        bundle=bundle,
        device=device,
        model=bundle.get_model(with_star=False).to(device).eval(),
        dict=bundle.get_dict(star=None),
        uroman=ur.Uroman(),
        load_audio=load_audio,
        load_transcript=load_transcript,
        fa_align=fa_align,
        unflatten=unflatten,
        post=_postprocess_results,
    )
    return _ali


def _romanize(heb, a):
    s = _CANT.sub("", heb)
    s = a["uroman"].romanize_string(s).lower()
    s = "".join(c for c in s if c in a["dict"] and a["dict"][c] != 0)
    return s or "a"


def _emissions(a, waveform):
    """Run the model over the waveform in windows, returning CPU emissions."""
    torch = a["torch"]
    win = _CHUNK_SECONDS * a["bundle"].sample_rate
    wav = waveform.to(a["device"])
    chunks = []
    with torch.inference_mode():
        for s in range(0, wav.shape[1], win):
            emission, _ = a["model"](wav[:, s:s + win])
            chunks.append(emission.to("cpu"))
    return torch.cat(chunks, dim=1)


def align(words, wav_path, transcript_path):
    a = _load_aligner()
    F = a["F"]
    roman = [_romanize(w["heb"], a) for w in words]
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write("\n".join(roman) + "\n")

    waveform = a["load_audio"](wav_path, ret_type="torch")
    transcript, _lines = a["load_transcript"](transcript_path, a["dict"])
    emission = _emissions(a, waveform)
    tokens = [
        a["dict"][c]
        for word in transcript
        for c in word
        if c in a["dict"] and a["dict"][c] != 0
    ]
    aligned_tokens, scores = a["fa_align"](emission, tokens, "cpu")
    token_spans = F.merge_tokens(aligned_tokens[0], scores[0])
    word_spans = a["unflatten"](token_spans, [len(w) for w in transcript])
    results = a["post"](
        transcript, word_spans, waveform, emission.size(1),
        a["bundle"].sample_rate, scores,
    )
    if len(results) != len(words):
        raise RuntimeError(
            f"alignment produced {len(results)} spans for {len(words)} words"
        )
    return [
        {"index": i, "begin": round(r["start"], 3), "end": round(r["end"], 3)}
        for i, r in enumerate(results)
    ]


# --------------------------------------------------------------------------- #
# Cache + orchestration
# --------------------------------------------------------------------------- #
def _slug(book_id, chapter):
    return f"{book_id}_{chapter}"


def is_cached(book_id, chapter):
    d = os.path.join(CHAPTERS, _slug(book_id, chapter))
    return all(
        os.path.isfile(os.path.join(d, f))
        for f in ("data.json", "word_times.json", "audio.wav")
    )


def _write_index():
    entries = []
    for b in BOOKS:
        cached = [c for c in range(1, b[4] + 1) if is_cached(b[0], c)]
        entries.append(
            {"id": b[0], "name": b[1], "chapters": b[4], "cached": cached}
        )
    os.makedirs(CHAPTERS, exist_ok=True)
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump({"books": entries}, f, ensure_ascii=False, indent=1)


def process_chapter(book_id, chapter, force=False):
    """Fetch, align and cache a chapter. Returns its slug. Thread-safe."""
    if book_id not in BOOK_BY_ID:
        raise ValueError(f"unknown book '{book_id}'")
    b = BOOK_BY_ID[book_id]
    chapter = int(chapter)
    if not (1 <= chapter <= b[4]):
        raise ValueError(f"{b[1]} has chapters 1-{b[4]}")
    slug = _slug(book_id, chapter)
    out_dir = os.path.join(CHAPTERS, slug)

    with _LOCK:
        if not force and is_cached(book_id, chapter):
            _write_index()
            return slug
        os.makedirs(out_dir, exist_ok=True)
        words = scrape_interlinear(b[3], chapter)
        wav = os.path.join(out_dir, "audio.wav")
        download_audio(b[2], chapter, wav)
        times = align(words, wav, os.path.join(out_dir, "transcript.txt"))
        with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False)
        with open(os.path.join(out_dir, "word_times.json"), "w", encoding="utf-8") as f:
            json.dump(times, f, ensure_ascii=False)
        _write_index()
        return slug


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        print(process_chapter(sys.argv[1], int(sys.argv[2]),
                              force="--force" in sys.argv))
    else:
        print("usage: pipeline.py <book_id> <chapter> [--force]")
        print("books:", ", ".join(b[0] for b in BOOKS))
