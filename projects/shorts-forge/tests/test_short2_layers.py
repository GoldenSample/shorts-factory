# -*- coding: utf-8 -*-
"""Слои карточки short2: текст стоит, фон под ним едет.

Проверяет закон «текст никогда не двигается, движется мир под ним» на живом рендере:
  1. render_* даёт фон RGB без текста и текстовый слой RGBA (большинство пикселей прозрачные, буквы непрозрачные);
  2. build_scene собирает 1080x1920 нужной длины;
  3. по маске альфы текстового слоя кадры на 1.0 и 2.5 с совпадают с точностью до кодека, а фон между ними различается;
  4. одиночный PNG (скриншот первоисточника) по умолчанию не двигается.
Без Chrome, ffmpeg, Pillow или numpy тесты пропускаются с понятным сообщением. Сеть не нужна.

Запуск из корня репо: python3.12 -m unittest projects/shorts-forge/tests/test_short2_layers.py -v
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import short2  # noqa: E402

try:
    import numpy as np
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def _ffmpeg_ok() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _chrome_ok() -> bool:
    return short2.CHROME is not None and Path(short2.CHROME).is_file()


def _frame(mp4: Path, t: float, dest: Path) -> "np.ndarray":
    """Кадр на секунде t как массив RGB int."""
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(mp4),
                        "-frames:v", "1", str(dest)], capture_output=True)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:])
    with Image.open(dest) as im:
        return np.asarray(im.convert("RGB")).astype(int)


def _erode(mask: "np.ndarray", r: int) -> "np.ndarray":
    """Сжать маску на r px: убрать кромку глифов (сглаживание и субдискретизация цветности)."""
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out &= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


class LayersOfTest(unittest.TestCase):
    """Чистая логика без Chrome и ffmpeg: как build_scene отличает карточку от скриншота."""

    def test_pair_single_and_siblings(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            shot = d / "src.png"
            shot.write_bytes(b"x")
            self.assertEqual(short2.layers_of(shot), (shot, None))
            self.assertEqual(short2.layers_of((d / "a.png", d / "b.png")), (d / "a.png", d / "b.png"))
            card = d / "s01.png"
            for p in (card, d / "s01_bg.png", d / "s01_txt.png"):
                p.write_bytes(b"x")
            self.assertEqual(short2.layers_of(card), (d / "s01_bg.png", d / "s01_txt.png"))

    def test_find_chrome_env_first(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "chrome"
            fake.write_bytes(b"x")
            old = os.environ.get("GS_CHROME")
            os.environ["GS_CHROME"] = str(fake)
            try:
                self.assertEqual(short2.find_chrome(), fake)
            finally:
                if old is None:
                    os.environ.pop("GS_CHROME", None)
                else:
                    os.environ["GS_CHROME"] = old


@unittest.skipUnless(HAVE_PIL, "нет Pillow или numpy (python3.12 с ними)")
@unittest.skipUnless(_ffmpeg_ok(), "нет ffmpeg/ffprobe в PATH")
@unittest.skipUnless(_chrome_ok(), "Chrome не найден: задайте GS_CHROME или поставьте chromium в PATH")
class RenderLayersTest(unittest.TestCase):
    """Живой рендер: Chrome, затем ffmpeg с тишиной вместо озвучки."""

    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.work = Path(cls.td.name)
        cls.old_work = short2.WORK
        short2.WORK = cls.work
        cls.card = short2.render_statement(
            "t01", "ЖЕЛЕЗО БЕЗ ХАЙПА",
            "Самый быстрый SSD <em>подешевел на треть</em>.<br>Но заголовки молчат.")
        cls.bg = cls.work / "t01_bg.png"
        cls.txt = cls.work / "t01_txt.png"
        # тишина 2.6 с: сцена = голос + 0.4 с = 3.0 с
        cls.voice = cls.work / "t01_voice.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                        "-t", "2.6", str(cls.voice)], capture_output=True, check=True)
        cls.mp4 = short2.build_scene("t01", cls.card, cls.voice, "Подешевел на треть. Но есть три «но»")

    @classmethod
    def tearDownClass(cls):
        short2.WORK = cls.old_work
        cls.td.cleanup()

    def test_layers_png(self):
        self.assertTrue(self.card.exists() and self.bg.exists() and self.txt.exists())
        with Image.open(self.txt) as txt:
            self.assertEqual(txt.mode, "RGBA")
            self.assertEqual(txt.size, (short2.W, short2.H))
            a = np.asarray(txt)[..., 3]
        self.assertGreater((a == 0).mean(), 0.6, "текстовый слой: большинство пикселей прозрачные")
        self.assertGreater((a == 255).mean(), 0.01, "текстовый слой: буквы непрозрачные")
        with Image.open(self.bg) as bg:
            self.assertEqual(bg.size, (short2.W, short2.H))
            if bg.mode == "RGBA":
                self.assertTrue((np.asarray(bg)[..., 3] == 255).all(), "фон непрозрачный")
            else:
                self.assertEqual(bg.mode, "RGB")

    def test_scene_geometry(self):
        self.assertIsNotNone(self.mp4, "build_scene вернул None")
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height:format=duration",
                            "-of", "default=nw=1:nk=1", str(self.mp4)], capture_output=True, text=True)
        w, h, dur = r.stdout.split()
        self.assertEqual((int(w), int(h)), (1080, 1920))
        self.assertAlmostEqual(float(dur), 3.0, delta=0.3)

    def test_text_static_background_moves(self):
        self.assertIsNotNone(self.mp4, "build_scene вернул None")
        f1 = _frame(self.mp4, 1.0, self.work / "f1.png")
        f2 = _frame(self.mp4, 2.5, self.work / "f2.png")
        with Image.open(self.txt) as im:
            layer = np.asarray(im.convert("RGBA")).astype(int)
        alpha = layer[..., 3]
        core = _erode(alpha == 255, 2)       # нутро глифов
        clear = _erode(alpha == 0, 3)        # чистый фон вдали от букв
        self.assertGreater(core.sum(), 5000)
        diff = np.abs(f1 - f2).max(axis=2)
        txt_moved = (diff[core] > 12).mean()
        bg_moved = (diff[clear] > 12).mean()
        self.assertLess(txt_moved, 0.005, f"текст поехал: доля изменённых пикселей {txt_moved:.4f}")
        self.assertLess(diff[core].mean(), 3.0, "текст между 1.0 и 2.5 с отличается сильнее шума кодека")
        self.assertGreater(bg_moved, 0.005, f"фон стоит, Ken Burns не сработал: {bg_moved:.4f}")
        self.assertGreater(bg_moved, 10 * max(txt_moved, 1e-6))
        # буквы в кадре там же, где в PNG слоя (сдвиг на 2 px даёт среднее выше 10)
        for f in (f1, f2):
            pos = np.abs(f - layer[..., :3]).max(axis=2)[core].mean()
            self.assertLess(pos, 8.0, f"текст в кадре не на месте слоя: {pos:.2f}")

    def test_single_screenshot_static_by_default(self):
        """Одиночный PNG без соседей _bg/_txt: Ken Burns по умолчанию выключен."""
        shot = self.work / "shot.png"
        shutil.copyfile(self.bg, shot)
        mp4 = short2.build_scene("shot", shot, self.voice, "скриншот")
        self.assertIsNotNone(mp4, "build_scene (одиночный кадр) вернул None")
        f1 = _frame(mp4, 1.0, self.work / "s1.png")
        f2 = _frame(mp4, 2.5, self.work / "s2.png")
        moved = (np.abs(f1 - f2).max(axis=2) > 12).mean()
        self.assertLess(moved, 0.001, f"скриншот поехал: {moved:.4f}")


if __name__ == "__main__":
    unittest.main()
