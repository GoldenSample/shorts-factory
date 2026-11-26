def build_kenburns(image: Path, voice: Path, dest: Path, zoom_in: bool = True) -> bool:
    """Оживление СТАТИЧНОГО кадра (скриншот продукта) под длину озвучки.

    Генератив рисует «похожее», а не твой продукт, поэтому для презентаций
    визуал = реальные кадры + медленный наезд/отъезд (эффект Кена Бёрнса)."""
    dur = max(1.0, ffprobe_dur(voice))
    frames = int(dur * 30)
    z = "min(zoom+0.0007,1.25)" if zoom_in else "if(lte(zoom,1.0),1.25,max(1.0,zoom-0.0007))"
    vf = (
        f"scale=2160:-2,zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,setsar=1"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(image),
        "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        "-vf", vf, "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(dest),
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def srt_time(t: float) -> str:
    h, r = divmod(t, 3600)
    m, sec = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}".replace(".", ",")


def burn_subs(video: Path, lines: list[tuple[float, float, str]], dest: Path) -> bool:
    """Вжечь субтитры: ролики смотрят без звука, текст обязан быть в кадре."""
    srt = WORK_DIR / "subs.srt"
    blocks = []
    for i, (a, b, txt) in enumerate(lines, 1):
        blocks.append(str(i))
        blocks.append(f"{srt_time(a)} --> {srt_time(b)}")
        blocks.append(txt)
        blocks.append("")
    srt.write_text("\n".join(blocks), encoding="utf-8")

    style = (
        "FontName=Arial,FontSize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=140"
    )
    esc = srt.as_posix().replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
        "-vf", f"subtitles='{esc}':force_style='{style}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "copy", str(dest),
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0
