#!/usr/bin/env python
"""Neural forced alignment of Jonah 1 using the MMS multilingual CTC model
(ctc-forced-aligner, ONNX). Romanizes the Hebrew via uroman and aligns each word
to the human audio with a real acoustic model.

Produces word_times.json: [{"index": i, "begin": sec, "end": sec}, ...].
"""
import json
import os
import re

from ctc_forced_aligner import (
    AlignmentSingleton,
    load_audio,
    generate_emissions,
    preprocess_text,
    get_alignments,
    get_spans,
    postprocess_results,
)

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "jonah1.mp3")
LANG = "heb"

# Strip cantillation accents, maqqef and sof-pasuq; keep vowel points. Keep each
# word a single whitespace token so result count matches our word list.
CANT = re.compile("[\u0591-\u05AF\u05BD\u05BE\u05C0\u05C3\u05C6]")
def clean(s):
    return CANT.sub("", s).strip()

words = json.load(open(os.path.join(HERE, "..", "BibleReader", "Resources", "jonah1.json"), encoding="utf-8"))
tokens = [clean(w["heb"]) or w["heb"].strip() for w in words]
text = " ".join(tokens)

print("loading MMS ONNX alignment model (first run downloads it)...")
aligner = AlignmentSingleton()

audio_waveform = load_audio(AUDIO)
emissions, stride = generate_emissions(aligner.model, audio_waveform, batch_size=4)

tokens_starred, text_starred = preprocess_text(text, romanize=True, language=LANG)
segments, scores, blank_token = get_alignments(emissions, tokens_starred, aligner.tokenizer)
spans = get_spans(tokens_starred, segments, blank_token)
results = postprocess_results(text_starred, spans, stride, scores)

print(f"aligner returned {len(results)} words for {len(words)} expected")

rows = []
last = 0.0
for i, r in enumerate(results):
    b = max(float(r["start"]), last)
    e = max(float(r["end"]), b)
    rows.append({"index": i, "begin": round(b, 3), "end": round(e, 3)})
    last = b

out = os.path.join(HERE, "word_times.json")
json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"wrote {len(rows)} word timings to {out}")
print("samples:", [(r["index"], r["begin"]) for r in rows[::30]])
