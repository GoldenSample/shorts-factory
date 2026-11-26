# -*- coding: utf-8 -*-
"""Живой фон ДЕТЕРМИНИРОВАННО: пульс света процедурой, без генеративной лотереи.

ИСТОРИЯ РЕШЕНИЯ, чтобы не ходить по кругу.
1. Wan 2.2 i2v на наших почти-чёрных фонах тихо дорисовывает: лента кадров
   (не краевой контроль!) показала силуэт из углей, морф луны в вихрь, фигурку
   у лампы и посинение неба — у 4 сцен из 5 при cfg 2.0 и промпте без объектов.
2. Маска света поверх Wan (maskedmerge) НЕ спасла: дефекты растут ровно из
   световых зон — из углей, из луны — то есть прямо внутри маски.
⚑ Вывод: i2v для тёмных статичных задников не production-ready без пофреймовой
   верификации каждой попытки. Wan остаётся для сцен с нормальной экспозицией
   (осветлённый тест был чист) — а здесь движение делается процедурой.

КАК УСТРОЕН ПУЛЬС. Два статичных кадра: база и она же с приподнятым светом
(маска = порог яркости базы + растушёвка; вне маски кадры идентичны).
Финал — качание между ними по сумме двух косинусов с КРАТНЫМИ частотами
(1x и 3x за период): свет дышит неравномерно, как живой, а петля замыкается
покадрово, потому что обе гармоники целые на длине петли.
Никакой генерации → никакого крипа, воспроизводимо байт-в-байт.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BG = HERE / "reel_bg"
V = HERE / "reel_bg_video"
W, H = 1920, 1088
PERIOD = 4.0          # секунд на полный вдох-выдох; петля замыкается ровно тут
FPS = 24

# Порог маски и сила подсветки на сцену: у кого свет ярче — у того порог выше
# и пульс тише, иначе дыхание читается как мигание лампочки.
SCENES = {
    #            порог  яркость+  насыщенность
    "01_problem": (110,  0.045,    1.03),   # луна: едва заметное дыхание гало
    "02_built":   (48,   0.075,    1.08),   # угли: самое живое место
    "03_rules":   (55,   0.050,    1.02),   # холодный луч: дышит еле-еле
    "04_swarm":   (62,   0.070,    1.06),   # лампы по полу
    "05_market":  (72,   0.060,    1.05),   # окно башни и последний свет неба
    # вторая волна — сцены скринплея доклада (29-07)
    "06_study":   (55,   0.070,    1.07),   # свеча на столе
    "07_village": (95,   0.075,    1.06),   # окна ратуши: точечный тёплый свет
    "08_mine":    (70,   0.050,    1.03),   # жилы руды: холодное свечение
    "09_library": (58,   0.055,    1.03),   # луч на кафедру
    "10_market":  (52,   0.070,    1.07),   # лампа над прилавком
    "11_twodoors": (60,  0.065,    1.05),   # тёплый свет из двух проёмов
}


def run(cmd):
    return subprocess.run(cmd, capture_output=True)


def pulse(name: str, thr: int, gain: float, sat: float) -> bool:
    base = BG / f"{name}.png"
    dest = V / f"{name}_safe.mp4"
    if not base.exists():
        print(f"  {name}: нет базы")
        return False
    # w(T) = 0.35*(1-cos(w0*T)) + 0.15*(1-cos(3*w0*T)) ∈ [0..1], w(0)=w(PERIOD)=0.
    w = (f"0.35*(1-cos(2*PI*T/{PERIOD}))+0.15*(1-cos(6*PI*T/{PERIOD}))")
    vf = (
        f"[0:v]scale={W}:{H},format=yuv420p,setsar=1,split=3[a][b][c];"
        f"[b]eq=brightness={gain}:saturation={sat}[br];"
        f"[c]format=gray,lut=y='clip((val-{thr})*6,0,255)',"
        f"gblur=sigma=12,format=yuv420p[m];"
        f"[a]split[a0][a1];"
        f"[a0][br][m]maskedmerge[lit];"
        # качание база↔lit; вне маски оба кадра равны, так что дышит только свет
        f"[a1][lit]blend=all_expr='A+(B-A)*({w})',format=yuv420p[v]"
    )
    r = run(["ffmpeg", "-y", "-v", "error",
             "-loop", "1", "-framerate", str(FPS), "-t", f"{PERIOD:.3f}",
             "-i", str(base),
             "-filter_complex", vf, "-map", "[v]", "-r", str(FPS),
             "-c:v", "libx264", "-crf", "16", "-preset", "medium",
             "-pix_fmt", "yuv420p", str(dest)])
    if r.returncode != 0:
        print(f"  {name}: {r.stderr.decode('utf-8', 'replace')[-300:]}")
        return False
    print(f"  {name}: ок · порог {thr} · +{gain}")
    return True


def main() -> int:
    ok = 0
    for name, (thr, gain, sat) in SCENES.items():
        ok += pulse(name, thr, gain, sat)
    print(f"готово {ok}/{len(SCENES)}")
    return 0 if ok == len(SCENES) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
