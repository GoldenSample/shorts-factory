"""Перевыпуск карточек шортса SSD 9100 Pro в новой айдентике (style_lab), без начитки и сборки. Кладёт PNG в work_short2/lab/."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import short2, style_lab as SL
_k = SL.kick_html
TONE = {"ПОДВОХ ПЕРВЫЙ": "terra", "ФОРУМ SAMSUNG": "terra", "REDDIT · R/BUILDAPC": "", "ИТОГО": "gold", "ПРАВИЛО": "gold"}
SL.kick_html = lambda kick, tone="": _k(kick, TONE.get(kick, tone))
short2.WORK = short2.WORK / "lab"; short2.WORK.mkdir(exist_ok=True)
from short2 import render_panel, render_quote, render_statement
render_statement("s01", "ЖЕЛЕЗО БЕЗ ХАЙПА", "Самый быстрый SSD Самсунга <em>подешевел на треть</em>.<br>Но заголовки молчат о трёх вещах.")
render_panel("s03", "ЧТО ВНУТРИ", "SAMSUNG 9100 PRO 4TB", [("Чтение", "14 800", "мегабайт в секунду · PCIe 5.0"), ("Запись", "13 400", "мегабайт в секунду"),
             ("Цена на Woot", "−36%", "$619.99 против $972"), ("Гарантия Woot", "90 дней", "своя, не самсунговская", True)])
render_quote("s04", "REDDIT · R/BUILDAPC", "У меня 990 Pro уже два года: разницы в играх ноль", "тред «990 Pro vs 9100 Pro 4TB»")
render_panel("s05", "ПОДВОХ ПЕРВЫЙ", "БЕЗ PCIE 5.0 ПЛАТЫ", [("Твоя материнка Gen4?", "≈7 000", "мегабайт в секунду: потолок слота"),
             ("То есть платишь за", "×2", "скорость, которую не увидишь", True)])
render_quote("s06", "REDDIT · R/BUILDAPC", "Gen5 disk errors на ASUS X870: после холодного старта диск не определяется", "тред про 9100 Pro на X870-I")
render_quote("s07", "ФОРУМ SAMSUNG", "BSOD, диск исчезает из BIOS: помогает только передёрнуть питание", "тред про 9100 Pro 4TB · прошивка 0B2QNXH7")
render_panel("s08", "ИТОГО", "КОМУ ЧТО БРАТЬ", [("Для игр", "990 Pro", "дешевле, холоднее, разницы не увидишь", False, True),
             ("Монтаж и большие файлы", "9100 Pro", "если платформа реально Gen5")])
render_statement("s09", "ПРАВИЛО", "Плати за скорость, которую твоя система <em class=gold>реально умеет использовать</em>.")
print("готово:", sorted(p.name for p in short2.WORK.glob("*.png")))
