#!/usr/bin/env python
"""Two-pass forced alignment of Jonah 1 via aeneas + espeak-ng.

Pass 1 aligns the 17 verses to the full audio (robust: few fragments).
Pass 2 slices each verse's audio window and aligns that verse's words within it.
This manual hierarchy avoids the whole-chapter DTW drift.

Produces word_times.json: [{"index": i, "begin": sec, "end": sec}, ...].
"""
import json
import os
import re
import subprocess

from aeneas.task import Task
from aeneas.executetask import ExecuteTask
from aeneas.runtimeconfiguration import RuntimeConfiguration
from aeneas.ttswrappers.espeakngttswrapper import ESPEAKNGTTSWrapper

ESPEAKNGTTSWrapper.LANGUAGE_TO_VOICE_CODE["heb"] = "he"

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "jonah1.mp3")
TMP = os.path.join(HERE, "tmp")
os.makedirs(TMP, exist_ok=True)

RCONF = "tts=espeak-ng|tts_path=/opt/homebrew/bin/espeak-ng"
CANT = re.compile("[\u0591-\u05AF\u05BD]")

def clean(s):
    s = CANT.sub("", s).replace("\u05BE", " ").replace("\u05C3", "")
    return s.strip()

def audio_duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path]).decode().strip()
    return float(out)

def align(audio_path, lines, tag):
    """Flat-align the given text lines to audio_path; return list of (begin, end)."""
    txt = os.path.join(TMP, f"{tag}.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    task = Task(config_string="task_language=heb|is_text_type=plain|os_task_file_format=json")
    task.audio_file_path_absolute = audio_path
    task.text_file_path_absolute = txt
    ExecuteTask(task, rconf=RuntimeConfiguration(RCONF)).execute()
    leaves = [l for l in task.sync_map_leaves() if l.is_regular]
    return [(float(l.begin), float(l.end)) for l in leaves]

words = json.load(open(os.path.join(HERE, "..", "BibleReader", "Resources", "jonah1.json"), encoding="utf-8"))

# Group into verses, keeping each word's global index.
verses = []
for i, w in enumerate(words):
    tok = clean(w["heb"]) or w["heb"].strip()
    if verses and verses[-1]["n"] == w["verse"]:
        verses[-1]["toks"].append(tok)
        verses[-1]["idx"].append(i)
    else:
        verses.append({"n": w["verse"], "toks": [tok], "idx": [i]})

# Pass 1: verse-level windows.
total = audio_duration(AUDIO)
verse_lines = [" ".join(v["toks"]) for v in verses]
verse_spans = align(AUDIO, verse_lines, "verses")
print("pass1 verse spans:", [(verses[i]["n"], round(b, 1)) for i, (b, e) in enumerate(verse_spans)])

times = [None] * len(words)

# Pass 2: per-verse word alignment on a sliced clip.
for vi, v in enumerate(verses):
    vbegin, vend = verse_spans[vi]
    pad = 0.15
    clip_start = max(0.0, vbegin - pad)
    clip_end = min(total, vend + pad)
    clip = os.path.join(TMP, f"verse_{v['n']}.wav")
    subprocess.check_call(
        ["ffmpeg", "-y", "-v", "error", "-i", AUDIO,
         "-ss", f"{clip_start:.3f}", "-to", f"{clip_end:.3f}",
         "-ac", "1", "-ar", "22050", clip])
    spans = align(clip, v["toks"], f"w{v['n']}")
    if len(spans) != len(v["toks"]):
        print(f"  WARN verse {v['n']}: {len(spans)} spans for {len(v['toks'])} words")
    for k, gi in enumerate(v["idx"]):
        if k < len(spans):
            b, e = spans[k]
            times[gi] = (clip_start + b, clip_start + e)

# Fill any gaps defensively and enforce monotonic begins.
last = 0.0
rows = []
for i, t in enumerate(times):
    if t is None:
        t = (last, last)
    b = max(t[0], last)
    rows.append({"index": i, "begin": round(b, 3), "end": round(max(t[1], b), 3)})
    last = b

out = os.path.join(HERE, "word_times.json")
json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"wrote {len(rows)} word timings to {out}")
print("samples:", [(r["index"], r["begin"]) for r in rows[::30]])
