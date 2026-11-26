#!/usr/bin/env python3
"""Структурный валидатор SRT-файлов для субтитров CapCut.

Проверяет то, что можно проверить без понимания смысла: синтаксис, тайминги,
наложения, длину строк. Смысловые правки (ошибки распознавания, паразиты) —
работа модели, не скрипта.

Использование:
    python srt_check.py file.srt [--max-chars 28] [--max-lines 2]
                                 [--min-dur 0.8] [--max-dur 8.0]

Выход: 0 — только предупреждения или чисто; 1 — есть ошибки.
"""
import argparse
import re
import sys

TS = re.compile(r"^(\d{2,}):([0-5]\d):([0-5]\d),(\d{3})$")


def parse_ts(s: str):
    m = TS.match(s.strip())
    if not m:
        return None
    h, mi, se, ms = map(int, m.groups())
    return ((h * 60 + mi) * 60 + se) * 1000 + ms


def fmt_ts(ms: int) -> str:
    h, rest = divmod(ms, 3600000)
    mi, rest = divmod(rest, 60000)
    se, ms = divmod(rest, 1000)
    return f"{h:02d}:{mi:02d}:{se:02d},{ms:03d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--max-chars", type=int, default=28, help="макс. символов в строке")
    ap.add_argument("--max-lines", type=int, default=2, help="макс. строк в блоке")
    ap.add_argument("--min-dur", type=float, default=0.8, help="мин. длительность, сек")
    ap.add_argument("--max-dur", type=float, default=8.0, help="макс. длительность, сек")
    args = ap.parse_args()

    try:
        raw = open(args.file, encoding="utf-8-sig").read()
    except OSError as e:
        print(f"ERROR: cannot open file: {e}")
        return 1

    errors, warns = [], []
    blocks = re.split(r"\n\s*\n", raw.strip().replace("\r\n", "\n"))
    cues = []

    for bi, block in enumerate(b for b in blocks if b.strip()):
        lines = block.split("\n")
        if len(lines) < 2:
            errors.append(f"cue #{bi + 1}: less than two lines, not an SRT block: {lines!r}")
            continue
        idx_line, time_line, text_lines = lines[0].strip(), lines[1].strip(), lines[2:]
        if not idx_line.isdigit():
            errors.append(f"cue #{bi + 1}: first line is not a number: {idx_line!r}")
        if "-->" not in time_line:
            errors.append(f"cue #{bi + 1}: missing timecode line: {time_line!r}")
            continue
        start_s, _, end_s = time_line.partition("-->")
        start, end = parse_ts(start_s), parse_ts(end_s)
        if start is None or end is None:
            errors.append(f"cue #{bi + 1}: malformed timecode: {time_line!r}")
            continue
        cues.append((bi + 1, idx_line, start, end, text_lines))

    prev_end = None
    for n, idx, start, end, text_lines in cues:
        where = f"cue {idx} ({fmt_ts(start)})"
        if end <= start:
            errors.append(f"{where}: end before start")
        dur = (end - start) / 1000
        if dur < args.min_dur:
            warns.append(f"{where}: duration {dur:.2f}s < {args.min_dur}s")
        if dur > args.max_dur:
            warns.append(f"{where}: duration {dur:.2f}s > {args.max_dur}s - consider splitting")
        if prev_end is not None and start < prev_end:
            errors.append(f"{where}: overlaps previous cue")
        prev_end = end

        if not any(l.strip() for l in text_lines):
            errors.append(f"{where}: empty text")
        if len(text_lines) > args.max_lines:
            warns.append(f"{where}: {len(text_lines)} lines > {args.max_lines}")
        for l in text_lines:
            if len(l) > args.max_chars:
                warns.append(f"{where}: line longer than {args.max_chars} chars: {l!r}")
            if "  " in l:
                errors.append(f"{where}: double space: {l!r}")
            if l != l.rstrip():
                errors.append(f"{where}: trailing space")

    nums = [int(i) for _, i, *_ in [(0, c[1], 0) for c in cues] if i.isdigit()]
    if nums and nums != list(range(1, len(nums) + 1)):
        warns.append(f"numbering is not sequential from 1: {nums[:8]}…")

    print(f"Cues: {len(cues)}")
    for e in errors:
        print(f"ERROR: {e}")
    for w in warns:
        print(f"warning: {w}")
    if not errors and not warns:
        print("All clean.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

