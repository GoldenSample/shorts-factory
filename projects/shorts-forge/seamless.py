# -*- coding: utf-8 -*-
"""Бесшовная закольцовка генеративных футажей.

ЗАЧЕМ. Генератив отдаёт клип 4-8 секунд, а крутить его надо под озвучку 15-60 секунд.
Тупая петля (`-stream_loop -1`) стыкует последний кадр с первым, а они разные -
на стыке виден скачок, и он повторяется каждые несколько секунд. Глаз ловит именно
ритмичность скачка, поэтому дефект читается как дешёвая склейка.

КРИТЕРИЙ БЕСШОВНОСТИ (объективный, не на глаз).
Считаем межкадровую разницу внутри клипа - это "обычный ход" картинки. Потом считаем
разницу на стыке. Отношение seam_ratio = стык / обычный ход:
    ~1.0  стык неотличим от рядового межкадрового перехода = БЕСШОВНО
    >2.0  стык заметен
    >4.0  скачок бьёт в глаз
Порог приёмки SEAM_OK. Мерить надо именно отношением, а не абсолютом: у спокойного
клипа любой скачок заметен, у динамичного тот же абсолют тонет в движении.

ТРИ СТРАТЕГИИ, выбор замером (mode=auto):
  cut       найти внутри клипа пару похожих кадров и резать петлю по ним. Лучшее качество,
            когда генератив сам вернулся близко к начальной композиции. Ничего не искажает.
  pingpong  прямой ход + реверс. Стык идеален МАТЕМАТИЧЕСКИ (кадр стыкуется сам с собой),
            но заметен маятник, если в кадре есть направленное движение (дым, пролёт камеры).
  xfade     начало петли скрещено с хвостом. Работает всегда, но во время наложения
            картинка двоится - на резком движении видно.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SEAM_OK = 1.6          # во сколько раз стык может быть грубее обычного хода
PROBE_W, PROBE_H = 64, 114   # сетка анализа: 9:16, дёшево и достаточно для оценки движения


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


def ffprobe_dur(path: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    try:
        return float(r.stdout.decode().strip())
    except (ValueError, AttributeError):
        return 0.0


def ffprobe_fps(path: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=avg_frame_rate", "-of", "default=nw=1:nk=1", str(path)])
    try:
        num, den = r.stdout.decode().strip().split("/")
        return float(num) / float(den) if float(den) else 30.0
    except (ValueError, AttributeError):
        return 30.0


def frames(path: Path) -> np.ndarray:
    """Все кадры клипа как серая сетка PROBE_H x PROBE_W, float32.

    Гоним сырым потоком в память: клип короткий, а декодировать в файлы дороже и грязнее.
    """
    r = run(["ffmpeg", "-v", "error", "-i", str(path),
             "-vf", f"scale={PROBE_W}:{PROBE_H}:flags=bilinear,format=gray",
             "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    buf = np.frombuffer(r.stdout, dtype=np.uint8)
    n = buf.size // (PROBE_W * PROBE_H)
    if n < 2:
        raise RuntimeError(f"не удалось прочитать кадры: {path}")
    return buf[:n * PROBE_W * PROBE_H].reshape(n, PROBE_H, PROBE_W).astype(np.float32)


def diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


STATIC_EPS = 0.05   # ниже этого межкадрового хода клип считается статичным


def analyze(fr: np.ndarray) -> dict:
    """Обычный ход картинки и грубость стыка тупой петли.

    typical хранится НЕокруглённым: округлённый ноль на статичном клипе ронял деление.
    """
    steps = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    typical = max(float(np.median(steps)), 1e-6)
    seam = diff(fr[-1], fr[0])
    return {"n": len(fr), "typical": typical, "typical_r": round(typical, 3),
            "static": typical < STATIC_EPS,
            "seam_naive": round(seam, 3), "ratio_naive": round(seam / typical, 2),
            "steps": steps}


def best_cut(fr: np.ndarray, typical: float, min_frac: float = 0.55) -> dict | None:
    """Пара кадров (i, j), между которыми петля замыкается ровнее всего.

    Требуем, чтобы петля осталась достаточно длинной (min_frac от клипа): короткая
    петля крутится слишком часто и сама по себе читается как повтор, даже будучи бесшовной.
    """
    n = len(fr)
    lo = max(2, int(n * min_frac))
    flat = fr.reshape(n, -1)
    best = None
    for i in range(0, n - lo):
        # сравниваем кадр i со всеми возможными концами j
        js = np.arange(i + lo, n)
        if not js.size:
            break
        d = np.abs(flat[js] - flat[i]).mean(axis=1)
        k = int(np.argmin(d))
        val = float(d[k])
        if best is None or val < best["seam"]:
            best = {"i": i, "j": int(js[k]), "seam": val}
    if not best:
        return None
    best["ratio"] = round(best["seam"] / max(typical, 1e-6), 2)
    best["seam"] = round(best["seam"], 3)
    return best


def build_cut(src: Path, dst: Path, i: int, j: int, fps: float) -> bool:
    """Обрезать клип по найденным кадрам. Ничего не искажаем - только режем."""
    ss, to = i / fps, j / fps
    return run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                "-vf", f"trim={ss:.4f}:{to:.4f},setpts=PTS-STARTPTS",
                "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", str(dst)]).returncode == 0


def build_pingpong(src: Path, dst: Path, n_frames: int, fps: float) -> bool:
    """Прямой ход + реверс. ЕДИНСТВЕННАЯ стратегия с ТОЧНЫМ покадровым замыканием:
    петля стыкуется кадром сама с собой, а не похожим кадром.

    ⚑ Обе точки разворота обрезаются на кадр. Наивный `[a][r]concat` дублирует кадр
    и в конце прямого хода, и на замыкании петли — на воспроизведении это читается
    как двойное залипание каждый оборот. Реверс берём без первого и последнего кадра:
    A0..An-1 + A(n-2)..A1 — ход через оба разворота ровный, а A1 после A0 замыкает круг.

    Цена: маятник виден, если в кадре направленное движение (дым вверх, пролёт камеры).
    Для абстрактных текстур, боке, частиц и дыма — незаметен.
    """
    if n_frames < 4:
        return False
    vf = (f"[0:v]split[a][b];"
          f"[b]reverse,trim=start_frame=1:end_frame={n_frames - 1},setpts=PTS-STARTPTS[r];"
          f"[a][r]concat=n=2:v=1:a=0,setpts=N/{fps}/TB[v]")
    return run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                "-filter_complex", vf, "-map", "[v]", "-an", "-r", f"{fps}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", str(dst)]).returncode == 0


def build_xfade(src: Path, dst: Path, dur: float, overlap: float) -> bool:
    """Начало петли скрещено с хвостом: out длиной dur-overlap, замкнут плавно.

    ВНИМАНИЕ: в blend переменная времени называется T, поэтому длительность здесь
    обозначена dur - иначе выражение молча посчитает не то.
    """
    d = max(0.2, min(overlap, dur / 3))
    vf = (
        f"[0:v]trim=0:{d:.4f},setpts=PTS-STARTPTS[head];"
        f"[0:v]trim={dur - d:.4f}:{dur:.4f},setpts=PTS-STARTPTS[tail];"
        f"[head][tail]blend=all_expr='A*(T/{d:.4f})+B*(1-T/{d:.4f})'[mixed];"
        f"[0:v]trim={d:.4f}:{dur - d:.4f},setpts=PTS-STARTPTS[mid];"
        f"[mixed][mid]concat=n=2:v=1:a=0[v]"
    )
    return run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                "-filter_complex", vf, "-map", "[v]", "-an",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", str(dst)]).returncode == 0


def build_morph(src: Path, dst: Path, fps: float, n_frames: int, bridge: int = 8) -> bool:
    """TAPE LOOP: хвост клипа доводится до ПЕРВОГО кадра синтезированным движением.

    Отличие от xfade принципиальное. xfade РАСТВОРЯЕТ конец в начале - картинка на стыке
    двоится, кадры физически не совпадают, шов лишь замаскирован. Здесь последние `bridge`
    кадров выбрасываются и заменяются кадрами, которые minterpolate достраивает ДВИЖЕНИЕМ
    от кадра (N-bridge) к кадру 0. Итог: последний кадр петли естественно перетекает
    в первый, как на ленточной петле, и файл можно крутить по кругу вечно.

    Цена: minterpolate синтезирует по оптическому потоку, и если композиция за клип уехала
    далеко, на мосту возможны разводы. Поэтому мост короткий, а результат всё равно замеряется.
    """
    work = dst.parent
    a_png, b_png = work / f"_m_a_{dst.stem}.png", work / f"_m_b_{dst.stem}.png"
    body, bridge_mp4 = work / f"_m_body_{dst.stem}.mp4", work / f"_m_br_{dst.stem}.mp4"
    lst = work / f"_m_list_{dst.stem}.txt"
    try:
        keep = n_frames - bridge
        if keep < 2:
            return False
        # опорные кадры моста: откуда ведём и куда обязаны прийти (кадр 0)
        if run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf",
                f"select='eq(n\\,{keep - 1})'", "-frames:v", "1", "-update", "1",
                str(a_png)]).returncode != 0:
            return False
        if run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", "select='eq(n\\,0)'",
                "-frames:v", "1", "-update", "1", str(b_png)]).returncode != 0:
            return False

        # тело петли: всё до моста
        if run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf",
                f"select='lt(n\\,{keep})',setpts=N/{fps}/TB", "-an", "-r", f"{fps}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                "-pix_fmt", "yuv420p", str(body)]).returncode != 0:
            return False

        # мост: два опорных кадра -> minterpolate достраивает движение между ними
        two = work / f"_m_two_{dst.stem}.mp4"
        if run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", f"{1/fps:.5f}", "-i", str(a_png),
                "-loop", "1", "-t", f"{1/fps:.5f}", "-i", str(b_png),
                "-filter_complex", f"[0:v][1:v]concat=n=2:v=1:a=0,fps={fps}[v]",
                "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                str(two)]).returncode != 0:
            return False
        # растягиваем два кадра в bridge+1 кадров синтезом движения
        target = fps * (bridge + 1) / 2.0
        ok = run(["ffmpeg", "-y", "-v", "error", "-i", str(two), "-vf",
                  f"minterpolate=fps={target:.3f}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
                  f"trim=start_frame=1:end_frame={bridge + 1},setpts=N/{fps}/TB",
                  "-an", "-r", f"{fps}", "-c:v", "libx264", "-preset", "veryfast",
                  "-crf", "16", "-pix_fmt", "yuv420p", str(bridge_mp4)]).returncode == 0
        if not ok or not bridge_mp4.exists():
            return False

        lst.write_text(f"file '{body.name}'\nfile '{bridge_mp4.name}'\n", encoding="utf-8")
        return run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(dst)]).returncode == 0
    finally:
        for p in (a_png, b_png, body, bridge_mp4, lst, work / f"_m_two_{dst.stem}.mp4"):
            if p.exists():
                p.unlink()


def verify(path: Path) -> dict:
    """Замер готовой петли: во сколько раз её стык грубее обычного хода."""
    fr = frames(path)
    a = analyze(fr)
    return {"ratio": a["ratio_naive"], "seam": a["seam_naive"],
            "typical": a["typical"], "dur": round(ffprobe_dur(path), 2)}


def make_loop(src: Path, dst: Path, mode: str = "auto",
              overlap: float = 0.6, verbose: bool = True) -> dict:
    """Собрать бесшовную петлю. Возвращает отчёт с замерами всех проверенных стратегий."""
    dur, fps = ffprobe_dur(src), ffprobe_fps(src)
    fr = frames(src)
    base = analyze(fr)
    rep = {"src": src.name, "dur": round(dur, 2), "fps": round(fps, 2),
           "naive_ratio": base["ratio_naive"], "tried": {}}

    if verbose:
        print(f"  клип {dur:.2f}с {fps:.0f}fps, {base['n']} кадров")
        print(f"  обычный ход {base['typical_r']:.3f} | тупая петля: стык "
              f"{base['seam_naive']:.3f} = x{base['ratio_naive']} от хода")

    # Статичный кадр (заглушка, Ken Burns по статике) уже бесшовен по построению:
    # крутить нечего, любая стратегия только ухудшит и сожжёт время.
    if base["static"]:
        if verbose:
            print("  клип статичный (движения нет) — закольцовка не требуется")
        rep.update({"chosen": "none", "ratio": base["ratio_naive"], "dur": round(dur, 2),
                    "seamless": True, "gain": 1.0, "static": True})
        if src.resolve() != dst.resolve():
            dst.write_bytes(src.read_bytes())
        return rep

    tmp = dst.parent / f"_try_{dst.stem}"
    cands: list[tuple[str, Path, dict]] = []

    if mode in ("auto", "cut"):
        bc = best_cut(fr, base["typical"])
        if bc:
            p = tmp.with_name(tmp.name + "_cut.mp4")
            if build_cut(src, p, bc["i"], bc["j"], fps):
                v = verify(p)
                rep["tried"]["cut"] = {**v, "frames": [bc["i"], bc["j"]]}
                cands.append(("cut", p, v))
                if verbose:
                    print(f"  cut      кадры {bc['i']}-{bc['j']} -> {v['dur']}с, стык x{v['ratio']}")

    if mode in ("auto", "pingpong"):
        p = tmp.with_name(tmp.name + "_pp.mp4")
        if build_pingpong(src, p, base["n"], fps):
            v = verify(p)
            rep["tried"]["pingpong"] = v
            cands.append(("pingpong", p, v))
            if verbose:
                print(f"  pingpong -> {v['dur']}с, стык x{v['ratio']}")

    if mode in ("auto", "morph"):
        p = tmp.with_name(tmp.name + "_mo.mp4")
        if build_morph(src, p, fps, base["n"]):
            v = verify(p)
            rep["tried"]["morph"] = v
            cands.append(("morph", p, v))
            if verbose:
                print(f"  morph    -> {v['dur']}с, стык x{v['ratio']}")

    if mode in ("auto", "xfade"):
        p = tmp.with_name(tmp.name + "_xf.mp4")
        if build_xfade(src, p, dur, overlap):
            v = verify(p)
            rep["tried"]["xfade"] = v
            cands.append(("xfade", p, v))
            if verbose:
                print(f"  xfade    -> {v['dur']}с, стык x{v['ratio']}")

    if not cands:
        rep["error"] = "ни одна стратегия не собралась"
        return rep

    # ВЫБОР. Приоритет у ТОЧНОГО замыкания: петля должна стыковаться кадром сама с собой,
    # а не «похожим» кадром. cut и pingpong замыкаются точно (EXACT), xfade и morph лишь
    # маскируют шов растворением — картинка на переходе двоится, и по кругу это крутить
    # нельзя. Поэтому сначала берём точные, прошедшие порог; маскирующие — только фолбэк.
    EXACT = {"cut", "pingpong"}
    ok = [c for c in cands if c[2]["ratio"] <= SEAM_OK]
    exact_ok = [c for c in ok if c[0] in EXACT]
    if exact_ok:
        name, path, v = max(exact_ok, key=lambda c: c[2]["dur"])
    elif ok:
        name, path, v = max(ok, key=lambda c: c[2]["dur"])
    else:
        name, path, v = min(cands, key=lambda c: c[2]["ratio"])
    rep["closure"] = "точное (покадровое)" if name in EXACT else "маскировка растворением"

    path.replace(dst)
    for _, p, _ in cands:
        if p.exists():
            p.unlink()

    rep.update({"chosen": name, "ratio": v["ratio"], "dur": v["dur"],
                "seamless": v["ratio"] <= SEAM_OK,
                "gain": round(base["ratio_naive"] / max(v["ratio"], 1e-6), 1)})
    if verbose:
        mark = "БЕСШОВНО" if rep["seamless"] else "стык виден"
        print(f"  ВЫБРАНО {name} [{rep['closure']}]: стык x{v['ratio']} ({mark}), "
              f"было x{base['ratio_naive']} -> лучше в {rep['gain']} раз")
    return rep


def loop_to_length(loop: Path, dst: Path, seconds: float) -> bool:
    """Растянуть готовую петлю на нужную длину. Петля уже бесшовна, крутим тупо."""
    return run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(loop),
                "-t", f"{seconds:.3f}", "-an",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", str(dst)]).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="бесшовная закольцовка футажа")
    ap.add_argument("src", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--mode", choices=["auto","cut","pingpong","xfade","morph"], default="auto")
    ap.add_argument("--overlap", type=float, default=0.6)
    ap.add_argument("--seconds", type=float, help="сразу растянуть петлю на N секунд")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.src.exists():
        print(f"нет файла: {args.src}", file=sys.stderr)
        return 2

    dst = args.out or args.src.with_name(args.src.stem + "_loop.mp4")
    rep = make_loop(args.src, dst, args.mode, args.overlap, verbose=not args.json)

    if args.seconds and dst.exists():
        long = dst.with_name(dst.stem + f"_{int(args.seconds)}s.mp4")
        if loop_to_length(dst, long, args.seconds):
            rep["stretched"] = str(long)
            if not args.json:
                print(f"  растянуто на {args.seconds}с -> {long.name}")

    if args.json:
        rep.pop("tried", None)
        print(json.dumps(rep, ensure_ascii=False))
    return 0 if rep.get("seamless") else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
