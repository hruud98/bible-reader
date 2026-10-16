#!/usr/bin/env python
"""Hierarchical forced alignment of Jonah 1 (verse -> word) via aeneas + espeak-ng.

Using the multilevel ``mplain`` text (one verse per paragraph) constrains each
word to its verse, which avoids the DTW drift seen with flat alignment.
Produces word_times.json: [{"index": i, "begin": sec, "end": sec}, ...] in the
original word order.
"""
import json
import os
import re

from aeneas.task import Task
from aeneas.executetask import ExecuteTask
from aeneas.runtimeconfiguration import RuntimeConfiguration
from aeneas.ttswrappers.espeakngttswrapper import ESPEAKNGTTSWrapper

# aeneas ships no Hebrew mapping, but espeak-ng has the "he" voice.
ESPEAKNGTTSWrapper.LANGUAGE_TO_VOICE_CODE["heb"] = "he"
ESPEAKNGTTSWrapper.LANGUAGE_TO_VOICE_CODE["he"] = "he"

HERE = os.path.dirname(os.path.abspath(__file__))
words = json.load(open(os.path.join(HERE, "..", "BibleReader", "Resources", "jonah1.json"), encoding="utf-8"))

# Strip cantillation accents (keep vowel points) so espeak-ng pronounces cleanly.
CANT = re.compile("[\u0591-\u05AF\u05BD]")
def clean(s):
    s = CANT.sub("", s).replace("\u05BE", " ").replace("\u05C3", "")
    return s.strip()

# Build mplain: one verse per paragraph, words space-separated, blank line between.
verses = []
for w in words:
    tok = clean(w["heb"]) or w["heb"].strip()
    tok = tok.replace(" ", "\u05BE")  # keep maqqef-joined word as a single token
    if verses and verses[-1][0] == w["verse"]:
        verses[-1][1].append(tok)
    else:
        verses.append((w["verse"], [tok]))

mplain_path = os.path.join(HERE, "words_mplain.txt")
with open(mplain_path, "w", encoding="utf-8") as f:
    f.write("\n\n".join(" ".join(toks) for _, toks in verses) + "\n")

config = "task_language=heb|is_text_type=mplain|os_task_file_format=json|os_task_file_levels=3"
task = Task(config_string=config)
task.audio_file_path_absolute = os.path.join(HERE, "jonah1.mp3")
task.text_file_path_absolute = mplain_path

rconf = RuntimeConfiguration("tts=espeak-ng|tts_path=/opt/homebrew/bin/espeak-ng|allow_unlisted_languages=True")
ExecuteTask(task, rconf=rconf).execute()

# Finest-level leaves are individual words, in reading order.
rows = []
for leaf in task.sync_map_leaves():
    if leaf.is_regular and leaf.text and leaf.text.strip():
        rows.append({"index": len(rows), "begin": float(leaf.begin), "end": float(leaf.end)})

out = os.path.join(HERE, "word_times.json")
json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"wrote {len(rows)} word timings (expected {len(words)}) to {out}")
print("samples:", [(r["index"], round(r["begin"], 1)) for r in rows[::40]])
