"""Тест build_kenburns (forge.py): путь libplacebo / scale 4x -> zoompan, без заморозки кадров.

Офлайн, без сети: PNG 2160x3840 с шумом и сеткой, тишина 3 с, сборка, ffprobe, замер пар
соседних кадров (tblend difference + signalstats, как в visual-fx.md). Без ffmpeg тест пропускается.
Контраст: голый zoompan против scale 4x при ОДИНАКОВОМ медленном движении (900 кадров) и
старая строка forge.py на озвучке 14 с (упирается в 1.25 и стоит: заморозка больше 0).
Запуск: python3.12 -m unittest projects/shorts-forge/tests/test_forge_kenburns.py -v
"""
import contextlib
import io
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

FORGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE_DIR))
try:
    import httpx  # noqa: F401
except ImportError:
    sys.modules["httpx"] = types.ModuleType("httpx")   # forge.py тянет httpx на импорте, здесь он не нужен
import forge  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
FROZEN_LIMIT = 0.05      # средняя разница яркости соседних кадров (0..255) ниже этой = кадр стоит

# Старая строка фильтра forge.py до лечения долга (голый zoompan, scale 2160, шаг 0.0007 за кадр).
OLD_VF = (
    "scale=2160:-2,zoompan=z='min(zoom+0.0007,1.25)':d={frames}:x='iw/2-(iw/zoom/2)'"
    ":y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,setsar=1"
)


def make_png(dest: Path) -> None:
    """Контрастный шум с сеткой 2160x3840: PIL (шум с сидом через numpy), без PIL lavfi."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "nullsrc=s=2160x3840,geq=random(1)*255:128:128",
                        "-frames:v", "1", str(dest)], check=True)
        return
    try:
        import numpy as np
        im = Image.fromarray(np.random.default_rng(0).integers(0, 256, (3840, 2160), dtype=np.uint8), "L")
    except ImportError:
        im = Image.effect_noise((2160, 3840), 80)
    im = im.convert("RGB")
    d = ImageDraw.Draw(im)
    for x in range(0, 2160, 120):
        d.line([(x, 0), (x, 3840)], fill=(255, 255, 255), width=6)
    for y in range(0, 3840, 120):
        d.line([(0, y), (2160, y)], fill=(0, 0, 0), width=6)
    im.save(dest)


def frame_diffs(video: Path) -> list[float]:
    """Средняя |разница| яркости каждой пары соседних кадров (0..255)."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(video),
         "-vf", "tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
         "-f", "null", "-"],
        capture_output=True, text=True, errors="replace",
    )
    vals = [float(line.split("=", 1)[1]) for line in p.stdout.splitlines() if "YAVG=" in line]
    return vals[1:]      # первая строка = кадр 0, смешанный сам с собой


def frozen_share(diffs: list[float]) -> float:
    return sum(1 for d in diffs if d < FROZEN_LIMIT) / max(1, len(diffs))


def jitter(diffs: list[float]) -> float:
    """Неравномерность хода: stdev/mean разниц соседних кадров (целочисленный кроп даёт рваный шаг)."""
    return statistics.pstdev(diffs) / max(1e-9, statistics.fmean(diffs))


def render_vf(png: Path, voice: Path, vf: str, dest: Path, dur: float) -> int:
    """Сборка клипа с произвольной строкой фильтра, кодеки как в forge._kenburns_cmd."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png),
        "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        "-vf", vf, "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(dest),
    ]
    return subprocess.run(cmd, capture_output=True).returncode


def probe(video: Path) -> dict:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate:format=duration",
         "-of", "default=nw=1", str(video)],
        capture_output=True, text=True,
    )
    return dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)


@unittest.skipUnless(HAVE_FFMPEG, "нет ffmpeg/ffprobe на PATH")
class KenBurnsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="kb_")
        cls.dir = Path(cls.tmp.name)
        cls.png = cls.dir / "src.png"
        cls.voice = cls.dir / "silence.wav"
        make_png(cls.png)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "anullsrc=r=44100:cl=mono", "-t", "3", str(cls.voice)], check=True)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FORGE_KB", None)
            forge._KB_BACKEND = None
            cls.placebo = forge.kenburns_backend() == "placebo"     # одна Vulkan-проба, кэш остаётся

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def build(self, dest: Path, zoom_in: bool = True, kb: str | None = None) -> tuple[bool, str]:
        env = {"FORGE_KB": kb} if kb else {}
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False):
            if not kb:
                os.environ.pop("FORGE_KB", None)
            with contextlib.redirect_stdout(buf):
                ok = forge.build_kenburns(self.png, self.voice, dest, zoom_in=zoom_in)
        return ok, buf.getvalue()

    def check_clip(self, dest: Path) -> list[float]:
        info = probe(dest)
        self.assertEqual((info["width"], info["height"]), ("1080", "1920"))
        self.assertEqual(info["r_frame_rate"], "30/1")
        self.assertAlmostEqual(float(info["duration"]), 3.0, delta=0.25)
        diffs = frame_diffs(dest)
        self.assertGreaterEqual(len(diffs), 80)
        return diffs

    def test_backend_detection_and_forcing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FORGE_KB", None)
            forge._KB_BACKEND = None
            auto = forge.kenburns_backend()
            self.assertIn(auto, ("placebo", "zoompan"))
            self.assertEqual(auto, "placebo" if self.placebo else "zoompan")
            self.assertEqual(forge._KB_BACKEND, auto)          # кэш заполнен
        with mock.patch.dict(os.environ, {"FORGE_KB": "placebo"}):
            self.assertEqual(forge.kenburns_backend(), "placebo")
        with mock.patch.dict(os.environ, {"FORGE_KB": "ZOOMPAN"}):
            self.assertEqual(forge.kenburns_backend(), "zoompan")
        self.assertEqual(forge._KB_BACKEND, auto)              # принуждение кэш не трогает

    def test_vf_strings(self):
        pl = forge.kenburns_vf("placebo", 90, True)
        self.assertIn("libplacebo=w=1080:h=1920", pl)
        self.assertIn("crop_w='iw/(1+0.25*n/90)'", pl)
        self.assertIn("crop_w='iw/(1+0.06*n/90)'", forge.kenburns_vf("placebo", 90, True, 0.06))
        self.assertIn("upscaler=ewa_lanczos", pl)
        self.assertTrue(pl.endswith("hwdownload,format=yuv420p,setsar=1"))
        self.assertIn("1+0.25-0.25*n/90", forge.kenburns_vf("placebo", 90, False))
        zp = forge.kenburns_vf("zoompan", 90, True)
        self.assertTrue(zp.startswith("scale=4320:-2:flags=lanczos,zoompan="))
        self.assertIn("z='min(1+0.25,1+0.25*on/90)'", zp)
        self.assertIn("s=1080x1920:fps=30,setsar=1", zp)
        self.assertIn("z='max(1,1+0.25-0.25*on/90)'", forge.kenburns_vf("zoompan", 90, False))

    def test_zoom_rate_follows_duration(self):
        """Закон 05_motion.md: 2 %/с, потолок 1.25 (HANDOFF §3 строка 5а: k = min(0.20, 0.02*d))."""
        def vf(dur):
            cmd = forge._kenburns_cmd("zoompan", self.png, self.voice, self.dir / "x.mp4", dur, True)
            return cmd[cmd.index("-vf") + 1]
        self.assertIn("z='min(1+0.06,1+0.06*on/90)'", vf(3.0))          # 3 с: наезд 6 %
        self.assertIn("z='min(1+0.14,1+0.14*on/210)'", vf(7.0))         # 7 с: 14 %, без хвоста float
        self.assertIn("z='min(1+0.25,1+0.25*on/900)'", vf(30.0))        # 30 с: потолок 0.25
        cmd = forge._kenburns_cmd("placebo", self.png, self.voice, self.dir / "x.mp4", 3.0, False)
        self.assertIn("crop_w='iw/(1+0.06-0.06*n/90)'", cmd[cmd.index("-vf") + 1])

    def test_fallback_zoompan_no_frozen_frames(self):
        dest = self.dir / "fallback_in.mp4"
        ok, out = self.build(dest, kb="zoompan")
        self.assertTrue(ok, "build_kenburns на запасном пути вернул False")
        self.assertIn("кен бёрнс: scale 4x -> zoompan", out)
        diffs = self.check_clip(dest)
        self.assertEqual(frozen_share(diffs), 0.0, f"замороженные пары: {frozen_share(diffs):.3f}")

    def test_fallback_zoom_out(self):
        dest = self.dir / "fallback_out.mp4"
        ok, _ = self.build(dest, zoom_in=False, kb="zoompan")
        self.assertTrue(ok)
        diffs = self.check_clip(dest)
        self.assertEqual(frozen_share(diffs), 0.0)

    def test_auto_path(self):
        """Автовыбор: без Vulkan уходит на zoompan, с Vulkan (риг) собирает через libplacebo."""
        dest = self.dir / "auto.mp4"
        ok, out = self.build(dest)
        self.assertTrue(ok)
        self.assertIn("libplacebo (Vulkan)" if self.placebo else "scale 4x -> zoompan", out)
        self.assertNotIn("упал", out)
        diffs = self.check_clip(dest)
        self.assertEqual(frozen_share(diffs), 0.0)

    def test_forced_placebo_without_vulkan_fails_fast(self):
        if self.placebo:
            self.skipTest("libplacebo+Vulkan доступны: принудительный путь здесь не падает")
        dest = self.dir / "forced.mp4"
        ok, out = self.build(dest, kb="placebo")
        self.assertFalse(ok)                      # принуждение: запасного пути нет, честный False
        self.assertIn("libplacebo (Vulkan) [FORGE_KB]", out)
        self.assertFalse(dest.exists())

    def test_bare_zoompan_is_rougher_than_scale4x(self):
        """Контраст при ОДИНАКОВОМ движении: наезд 0.25 за 900 кадров (как 30-секундная сцена),
        рендерим первые 3 с. Голый zoompan по 2160 режет кроп по целому пикселю: шаг рваный,
        scale 4x перед ним выравнивает ход (visual-fx.md таблица: jitter 1.235 -> 0.310)."""
        fr = 900
        new_vf = forge.kenburns_vf("zoompan", fr, True)
        bare_vf = new_vf.replace("scale=4320:-2:flags=lanczos,", "scale=2160:-2,")
        self.assertNotEqual(bare_vf, new_vf)
        bare, new = self.dir / "bare900.mp4", self.dir / "new900.mp4"
        self.assertEqual(render_vf(self.png, self.voice, bare_vf, bare, 3.0), 0)
        self.assertEqual(render_vf(self.png, self.voice, new_vf, new, 3.0), 0)
        d_bare, d_new = frame_diffs(bare), frame_diffs(new)
        msg = (f"голый 2160: заморожено {frozen_share(d_bare):.3f}, рваность {jitter(d_bare):.3f}; "
               f"scale 4x: заморожено {frozen_share(d_new):.3f}, рваность {jitter(d_new):.3f}")
        print("  " + msg)
        self.assertEqual(frozen_share(d_new), 0.0, msg)
        self.assertGreater(jitter(d_bare), 1.5 * jitter(d_new), msg)

    def test_old_forge_filter_freezes_on_long_voice(self):
        """Старая строка forge.py (zoom+0.0007 за кадр, потолок 1.25): на озвучке 14 с упирается
        в 1.25 на кадре 357 и дальше стоит, заморозка больше 0. На 3 с заморозки нет (печать факта).
        Новый путь тянет наезд на всю длительность: заморожено 0 (test_fallback_*, и на медленном
        900-кадровом ходе в test_bare_zoompan_is_rougher_than_scale4x, где шаг кропа ещё мельче)."""
        long_voice = self.dir / "silence14.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "anullsrc=r=44100:cl=mono", "-t", "14", str(long_voice)], check=True)
        old3, old14 = self.dir / "old3.mp4", self.dir / "old14.mp4"
        self.assertEqual(render_vf(self.png, self.voice, OLD_VF.format(frames=90), old3, 3.0), 0)
        self.assertEqual(render_vf(self.png, long_voice, OLD_VF.format(frames=420), old14, 14.0), 0)
        d3, d14 = frame_diffs(old3), frame_diffs(old14)
        msg = (f"старый forge 3 с: заморожено {frozen_share(d3):.3f}; "
               f"старый forge 14 с: заморожено {frozen_share(d14):.3f} из {len(d14)} пар")
        print("  " + msg)
        self.assertGreaterEqual(len(d14), 400)
        self.assertGreater(frozen_share(d14), 0.0, msg)

if __name__ == "__main__":
    unittest.main()
