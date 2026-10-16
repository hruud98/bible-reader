#!/usr/bin/env python3
"""Neural forced alignment of Jonah 1 Hebrew audio using torchaudio MMS_FA.

- Romanizes each Hebrew word (unidecode), matching how the MMS multilingual
  uroman model expects input.
- Runs torchaudio.pipelines.MMS_FA (downloads from pytorch.org, not HuggingFace).
- Produces per-word begin/end timestamps aligned 1:1 with the 269 source words.
"""
import json
import os
import re
import sys

import uroman as ur
import torchaudio
from ctc_forced_aligner import get_word_stamps

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "BibleReader", "Resources", "jonah1.json")
AUDIO = os.path.join(HERE, "jonah1.mp3")
TRANSCRIPT = os.path.join(HERE, "transcript_roman.txt")
OUT = os.path.join(HERE, "word_times.json")

# Cantillation + meteg etc. (unidecode drops these anyway, but strip for safety).
CANT = re.compile("[\u0591-\u05AF\u05BD\u05BE\u05C0\u05C3\u05C6]")

# MMS_FA romanized character vocabulary (a-z + apostrophe), index 0 is blank.
DICT = torchaudio.pipelines.MMS_FA.get_dict(star=None)

# uroman is the romanizer the MMS_FA ("mling_uroman") model was trained on; it
# uses the niqqud vowels, giving far better phonetic matches than unidecode.
_UROMAN = ur.Uroman()


def romanize(heb):
    s = CANT.sub("", heb)
    s = _UROMAN.romanize_string(s).lower()
    s = "".join(c for c in s if c in DICT and DICT[c] != 0)
    return s


def main():
    with open(DATA, encoding="utf-8") as f:
        words = json.load(f)
    print(f"{len(words)} source words")

    cleaned = []
    for i, w in enumerate(words):
        r = romanize(w["heb"])
        if not r:
            # Fallback so every source word keeps a transcript token and the
            # 1:1 index mapping is preserved.
            r = "a"
            print(f"  WARN word {i} ({w['heb']!r}) romanized empty -> placeholder")
        cleaned.append(r)

    with open(TRANSCRIPT, "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned) + "\n")

    print("Running MMS_FA forced alignment (first run downloads ~1.2GB model)...")
    results, _model, _lines = get_word_stamps(AUDIO, TRANSCRIPT, model_type="MMS_FA")

    if len(results) != len(words):
        print(
            f"ERROR: alignment produced {len(results)} spans but there are "
            f"{len(words)} words; index mapping would be wrong.",
            file=sys.stderr,
        )
        sys.exit(1)

    out = [
        {"index": i, "begin": round(r["start"], 3), "end": round(r["end"], 3)}
        for i, r in enumerate(results)
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)

    # Sanity check: spread + monotonicity.
    print("\nSample timestamps:")
    for i in (0, 50, 100, 150, 200, 250, len(out) - 1):
        print(f"  word {i:3d}  begin={out[i]['begin']:7.3f}  end={out[i]['end']:7.3f}")
    last = out[-1]["end"]
    print(f"\nLast end = {last:.3f}s")
    backwards = sum(
        1 for i in range(1, len(out)) if out[i]["begin"] < out[i - 1]["begin"] - 0.5
    )
    print(f"Non-monotonic jumps (>0.5s backwards): {backwards}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
