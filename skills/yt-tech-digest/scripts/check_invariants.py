# -*- coding: utf-8 -*-
"""Проверка сюжетных инвариантов ролика против таблицы замеров.

Использование:
    python check_invariants.py "<таблица>.xlsx" "<лист>" invariants.json

invariants.json — список объектов:
    [
      {"name": "ПБО берёт CS2 у Лока",        "expr": "C10 > C12"},
      {"name": "лестница R23 монотонна",       "expr": "G7 < G10 < G12 < G13"},
      {"name": "платы равны в ПБО (<1%)",      "expr": "abs(G10 - G30) / G30 < 0.01"},
      {"name": "кап режет 0.1% low",           "expr": "D26 < D24"},
      {"name": "разброс повторов Лока < 1%",   "expr": "abs(48579 - 48189) / 48579 < 0.01"}
    ]

В expr доступны: адреса ячеек листа (A1-стиль, значения как числа/строки/None),
функции abs, min, max, round, sum, len, isinstance, int, float; переменная W — словарь
всех ячеек; col("C") — список числовых значений колонки (для «лучший в таблице»).
Ячейка пустая → None; сравнение с None даёт FAIL с пометкой «нет данных»,
что и требуется: инвариант про неснятое не может «пройти».

Код выхода 0 = все прошли, 1 = есть провалы (для CI/хуков).
"""
import json
import re
import sys

try:
    import openpyxl
except ImportError:
    print("нужен openpyxl: pip install openpyxl (в отдельном venv)")
    sys.exit(2)


def load_cells(path, sheet):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet]
    cells = {}
    for row in ws.iter_rows():
        for c in row:
            cells[c.coordinate] = c.value
    return cells


def evaluate(expr, cells):
    refs = sorted(set(re.findall(r"\b[A-Z]{1,3}[0-9]{1,5}\b", expr)))
    missing = [r for r in refs if cells.get(r) in (None, "")]
    if missing:
        return None, "нет данных: " + ", ".join(missing)
    def col(letter):
        return [v for k, v in cells.items()
                if k.rstrip("0123456789") == letter and isinstance(v, (int, float))]
    env = {"abs": abs, "min": min, "max": max, "round": round, "sum": sum, "len": len,
           "isinstance": isinstance, "int": int, "float": float, "W": cells, "col": col}
    for r in refs:
        env[r] = cells[r]
    try:
        return bool(eval(expr, {"__builtins__": {}}, env)), None
    except Exception as e:  # noqa: BLE001
        return None, "ошибка выражения: %s" % e


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    path, sheet, inv_path = sys.argv[1:]
    cells = load_cells(path, sheet)
    invariants = json.load(open(inv_path, encoding="utf-8"))
    failed = 0
    for inv in invariants:
        ok, note = evaluate(inv["expr"], cells)
        if ok is True:
            mark = "OK  "
        else:
            mark = "FAIL"
            failed += 1
        line = "%s  %-45s  %s" % (mark, inv["name"], inv["expr"])
        if note:
            line += "   [%s]" % note
        print(line)
    print("-" * 60)
    print("прошло %d из %d" % (len(invariants) - failed, len(invariants)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
