"""Стиль карточек шортсов = айдентика Golden Sample. Тонкая прокладка: все цвета и шрифты живут в C:/CLAUD/tools/gs_style.py,
правила в skills/golden-sample-style/SKILL.md. ⛔ Прежняя палитра «BR2049» (тёплый чёрный, крем, янтарь, засечки, моноширинные
подписи с ромбиком) снята со всех сборок словом Гора 21.09.2026: «палитра и шрифт дефолт клод запрещены»."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
import gs_style as GS  # noqa: E402

BG, TEXT, MUTED, LINE = GS.INK, GS.WHITE, GS.MUTED, GS.LINE
ICE, ALARM, OK = GS.BLUE, GS.TERRA, GS.PASS          # прежние имена оставлены для совместимости
GOLD = GS.GOLD


def css(w: int, h: int) -> str:
    return GS.card_css(w, h)


def kick_html(kick: str, tone: str = "") -> str:
    """tone: "" голубой (рубрика, данные), "gold" (вердикт, лучший результат), "terra" (подвох, предупреждение)."""
    return f"<div class='kick {tone}'>{kick}</div>"
