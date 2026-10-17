"""Подсказки по таблице: разбор csv и xlsx, кандидаты точной арифметикой, сверка чисел модели, API и план."""
from __future__ import annotations

import io
import json
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from designer import store
from designer.api.app import app, get_llm_client
from designer.contracts import DeckPlan, SlideIntent, SlideKind
from designer.insights.facts import find_facts
from designer.insights.suggest import insert_insight_slides, number_span, numbers_in, suggest
from designer.insights.table import TableError, parse_number, read_table
from designer.llm.client import LlmClient

QUARTERS = ("Квартал;Выручка, млн руб.;Клиенты;Доля онлайн, %\n"
            "I кв 2026;120;1 250;31,5\nII кв 2026;135;1 410;33\n"
            "III кв 2026;150;1 380;36,2\nIV кв 2026;177;1 690;40,1\n").encode("cp1251")
REGIONS = ("Регион,Q3 2026,Q4 2026\nСеверо-Запад,48,61\nЦентр,90,95\nУрал,30,28\n"
           "Сибирь,22,31\nЮг,40,40\nИтого,230,255\n").encode()


def _llm(payload: dict) -> LlmClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]})
    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("text,value", [("1 234,5", "1234.5"), ("-12.3", "-12.3"), ("18 %", "18"),
                                        ("−5", "-5"), ("120 ₽", "120"), ("1 250", "1250")])
def test_numbers_in_russian_formats(text, value):
    assert parse_number(text) == Decimal(value)


@pytest.mark.parametrize("text", ["=SUM(A1:A3)", "IV кв", "12.05.2026", "", "1,2,3"])
def test_not_numbers(text):
    assert parse_number(text) is None


def test_cp1251_semicolon_csv_reads():
    table = read_table(QUARTERS, "итоги.csv")
    assert table.headers[1] == "Выручка, млн руб."
    assert table.numbers[0][2] == Decimal(1250)


def test_xlsx_first_sheet_with_cached_formula_values():
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(["Квартал", "Выручка"])
    sheet.append(["Q1 2026", 100])
    sheet.append(["Q2 2026", 125.5])
    buffer = io.BytesIO()
    book.save(buffer)
    table = read_table(buffer.getvalue(), "q.xlsx")
    assert table.rows == [["Q1 2026", "100"], ["Q2 2026", "125.5"]]


@pytest.mark.parametrize("data,name,message", [
    (b"a,b\n1,2\n", "x.csv", "две строки"),
    (b",b\n1,2\n3,4\n", "x.csv", "шапку"),
    (b"a,b\n1,2\n3,4\n", "x.pdf", "xlsx, csv или картинка"),
    (b"x" * (1024 * 1024 + 1), "x.csv", "1 МБ"),
], ids=["one-row", "empty-header", "pdf", "too-big"])
def test_bad_tables_say_what_to_fix(data, name, message):
    with pytest.raises(TableError, match=message):
        read_table(data, name)


def test_quarter_facts_are_exact():
    facts = {f.kind + f.statement[:6]: f for f in find_facts(read_table(QUARTERS, "q.csv"))}
    revenue = next(f for f in facts.values() if f.kind == "change_last" and f.statement.startswith("Выручка"))
    assert revenue.numbers == ["+18 %", "150", "177"]
    share = next(f for f in facts.values() if f.kind == "change_last" and f.statement.startswith("Доля"))
    assert share.numbers[0] == "+3,9 п. п."  # доля меняется в процентных пунктах


def test_total_row_is_not_a_region():
    facts = find_facts(read_table(REGIONS, "r.csv"))
    grew = next(f for f in facts if f.kind == "rows_grew")
    assert grew.numbers == ["3", "5"]
    total = next(f for f in facts if f.kind == "total_change")
    assert total.numbers == ["+10,9 %", "230", "255"]


def test_model_number_not_from_facts_is_dropped():
    table = read_table(REGIONS, "r.csv")
    facts = find_facts(table)
    grew = next(f for f in facts if f.kind == "rows_grew")
    answer = {"suggestions": [
        {"fact_ids": [grew.id], "headline": "В Q4 выросли 3 из 5 регионов", "number": "3 из 5", "visual": "column",
         "why": "видно, где рост"},
        {"fact_ids": [grew.id], "headline": "Выручка выросла на 25 %", "number": "+25 %", "visual": "big_number",
         "why": "придуманное число"},
    ]}
    suggestions, note = suggest(table, facts, "итоги", "директора", _llm(answer))
    assert note == ""
    assert suggestions[0].headline == "В Q4 выросли 3 из 5 регионов" and suggestions[0].by_model
    assert all("25" not in numbers_in(s.headline + " " + s.number) for s in suggestions)
    assert len(suggestions) >= 3  # добрано кандидатами кода
    assert not suggestions[-1].by_model


def test_model_failure_falls_back_to_code_facts():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "не json"}}]})
    table = read_table(QUARTERS, "q.csv")
    suggestions, note = suggest(table, find_facts(table), "", "", LlmClient("http://test/v1", "m", transport=httpx.MockTransport(handler)))
    assert note and len(suggestions) == 3 and not any(s.by_model for s in suggestions)


def test_model_headline_must_keep_period_sign_and_metric():
    """Ред-тим 17.10: «за 2026 год» при сравнении кварталов, спад при росте, чужая метрика не проходят."""
    table = read_table(QUARTERS, "q.csv")
    facts = find_facts(table)
    total = next(f for f in facts if f.kind == "change_total" and f.topic == "Выручка")
    last = next(f for f in facts if f.kind == "change_last" and f.topic == "Клиенты")
    answer = {"suggestions": [
        {"fact_ids": [total.id], "headline": "Выручка выросла на 47,5 % за 2026 год", "number": "+47,5 %",
         "visual": "line", "why": "рост на 99 % нужен совету"},
        {"fact_ids": [last.id], "headline": "Клиентов в IV квартале на 22,5 % меньше", "number": "−22,5 %",
         "visual": "column", "why": ""},
        {"fact_ids": [last.id], "headline": "Выручка в IV квартале выросла на 22,5 %", "number": "+22,5 %",
         "visual": "column", "why": ""},
    ]}
    suggestions, _ = suggest(table, facts, "", "", _llm(answer))
    by_model = [s for s in suggestions if s.by_model]
    # «За 2026 год» у сравнения кварталов чинится точным периодом, спад при росте и чужая метрика отбрасываются.
    assert [s.headline for s in by_model] == ["Выручка выросла на 47,5 % с I кв 2026 по IV кв 2026"]
    assert by_model[0].why == ""  # число в «зачем показывать» не из таблицы


def test_newest_first_table_keeps_time_order():
    reversed_quarters = ("Квартал;Выручка\nIV кв 2026;177\nIII кв 2026;150\nII кв 2026;135\nI кв 2026;120\n").encode()
    facts = find_facts(read_table(reversed_quarters, "r.csv"))
    change = next(f for f in facts if f.kind == "change_last")
    assert change.numbers == ["+18 %", "150", "177"]
    assert next(f for f in facts if f.kind == "growth_count").numbers == ["3", "3"]


def test_year_column_is_a_label_not_a_metric():
    years = "Год;Выручка\n2023;90\n2024;120\n2025;177\n".encode()
    facts = find_facts(read_table(years, "y.csv"))
    assert all(f.topic == "Выручка" for f in facts)
    assert any("2024 → 2025" in f.statement for f in facts)


def test_rows_keep_file_line_numbers_with_blank_lines():
    table = read_table("Квартал;Выручка\n\nI кв 2026;120\n\nII кв 2026;135\n".encode(), "b.csv")
    assert table.lines == [3, 5]


def test_xlsx_errors_name_the_sheet():
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = "Обложка"
    book.active.append(["Отчёт за год"])
    buffer = io.BytesIO()
    book.save(buffer)
    with pytest.raises(TableError, match="Лист «Обложка»"):
        read_table(buffer.getvalue(), "book.xlsx")


def test_broken_csv_quote_is_explained_in_russian():
    with pytest.raises(TableError, match=r"Строка \d+: кавычка"):
        read_table(b'a;b\n"1;2\n3;4\n', "q.csv")


def test_rejected_key_falls_back_with_reason():
    def handler(request):
        return httpx.Response(401, json={"Code": "UNAUTHORIZED"})
    table = read_table(REGIONS, "r.csv")
    suggestions, note = suggest(table, find_facts(table), "", "", LlmClient("http://test/v1", "m", transport=httpx.MockTransport(handler)))
    assert "ключ" in note and len(suggestions) == 3


def test_numbers_in_ignores_sign_and_groups():
    assert numbers_in("+18,0 % (1 380 → 1690)") == {"18", "1380", "1690"}


def test_insight_slides_go_after_title_and_agenda():
    table = read_table(QUARTERS, "q.csv")
    suggestions, _ = suggest(table, find_facts(table), "", "", None)
    plan = DeckPlan(title="t", purpose="p", slides=[
        SlideIntent(id="", kind=SlideKind.title, title="Итоги"),
        SlideIntent(id="", kind=SlideKind.agenda, title="План"),
        SlideIntent(id="", kind=SlideKind.thanks, title="Спасибо")])
    insert_insight_slides(plan, suggestions)
    assert [s.kind for s in plan.slides[2:2 + len(suggestions)]] != []
    assert plan.slides[2].title == suggestions[0].headline
    assert plan.slides[2].chart is not None and plan.slides[2].chart.categories[-1] == "IV кв 2026"
    assert [s.id for s in plan.slides] == [f"s{i}" for i in range(1, len(plan.slides) + 1)]
    assert "Источник: столбец" in plan.slides[2].notes


def test_plan_repeats_of_insights_are_dropped():
    """Прогон 17.10: план повторил четыре вывода своими слайдами и подписал столбцы «До конца 2025»."""
    from designer.contracts import ChartSpec, Item, Series
    table = read_table(QUARTERS, "q.csv")
    suggestions, _ = suggest(table, find_facts(table), "", "", None)
    revenue = next(s for s in suggestions if s.headline.startswith("Выручка"))
    plan = DeckPlan(title="t", purpose="p", slides=[
        SlideIntent(id="", kind=SlideKind.title, title="Итоги 2026 года"),
        SlideIntent(id="", kind=SlideKind.chart, title="Выручка выросла за год",
                    chart=ChartSpec(type="column", categories=["До конца 2025", "Конец 2026"],
                                    series=[Series(name="Выручка", values=[120, 177])])),
        SlideIntent(id="", kind=SlideKind.section, title=revenue.headline),
        SlideIntent(id="", kind=SlideKind.big_number, title="Рост за 2026 год",
                    items=[Item(heading="рост", number="2026")]),
        SlideIntent(id="", kind=SlideKind.cards, title="Куда вкладываться в 2027 году"),
        SlideIntent(id="", kind=SlideKind.thanks, title="Спасибо")])
    insert_insight_slides(plan, suggestions)
    titles = [s.title for s in plan.slides]
    assert "Выручка выросла за год" not in titles  # числа вывода на чужой диаграмме
    assert titles.count(revenue.headline) == 1  # раздел с тем же заголовком убран
    assert "Рост за 2026 год" in titles  # год не число вывода
    assert "Куда вкладываться в 2027 году" in titles


def test_insight_slide_keeps_model_reading_out_of_slide_text():
    table = read_table(QUARTERS, "q.csv")
    facts = find_facts(table)
    share = next(f for f in facts if f.kind == "change_last" and f.statement.startswith("Доля"))
    answer = {"suggestions": [{"fact_ids": [share.id], "headline": "Доля онлайна выросла на 3,9 п. п. в IV квартале к III",
                               "number": "+3,9 п. п.", "visual": "big_number", "why": "свидетельствует о росте лояльности"}]}
    suggestions, _ = suggest(table, facts, "", "", _llm(answer))
    plan = DeckPlan(title="t", purpose="p", slides=[SlideIntent(id="", kind=SlideKind.title, title="t")])
    insert_insight_slides(plan, suggestions[:1])
    made = plan.slides[1]
    text = made.title + made.key_message + " ".join(i.heading for i in made.items)
    # Причинное толкование модели не идёт ни на слайд, ни в заметки: причин в таблице нет.
    assert "свидетельствует" not in text and "свидетельствует" not in made.notes
    assert made.items[0].heading == share.statement


def test_api_insights_then_deck_request_finds_them(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))
    app.dependency_overrides[get_llm_client] = lambda: _llm({"suggestions": []})
    try:
        with TestClient(app) as client:
            response = client.post("/insights", files={"file": ("r.csv", REGIONS, "text/csv")},
                                   data={"brief": "итоги", "audience": "директора"})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["rows"] == 6 and body["columns"] == 3 and len(body["suggestions"]) == 3
            assert body["suggestions"][0]["source"].startswith("столб")
            saved = store.load_insights(body["id"])
            assert saved["suggestions"][0]["chart"]["categories"]

            bad = client.post("/insights", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
            assert bad.status_code == 422 and "две строки" in bad.json()["detail"]

            missing = client.post("/decks", json={"design_system_id": "x", "brief": "b",
                                                  "insights_id": "nope", "insight_ids": ["s1"]})
            assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_headline_without_main_number_gives_way_to_code():
    """Ред-тим 17.10: число в строке одно, внутри вывода. Вывод модели без главного числа не показывается."""
    table = read_table(QUARTERS, "q.csv")
    facts = find_facts(table)
    share = next(f for f in facts if f.kind == "change_last" and f.statement.startswith("Доля"))
    answer = {"suggestions": [{"fact_ids": [share.id], "headline": "Доля онлайна в IV квартале выросла до 40,1 %",
                               "number": "40,1 %", "visual": "big_number", "why": ""}]}
    suggestions, _ = suggest(table, facts, "", "", _llm(answer))
    assert not any(s.by_model for s in suggestions)
    for s in suggestions:
        start, end = s.number_at
        assert numbers_in(s.headline[start:end]) & numbers_in(s.number)


@pytest.mark.parametrize("headline,number,marked", [
    ("Выручка выросла на 47,5 % с I по IV квартал 2026 года", "+47,5 %", "47,5 %"),
    ("Отток: снижение на 1,3 п. п., III кв 2026 → IV кв 2026", "−1,3 п. п.", "1,3 п. п."),
    ("Выручка: рост в 3 из 3 сравнений с прошлым периодом", "3 из 3", "3 из 3"),
    ("Выручка: больше всего у «Центр» (95 млн ₽)", "95", "95 млн ₽"),
    ("Отток −1,3 п. п. за квартал", "1,3", "−1,3 п. п."),
], ids=["percent", "points", "count", "unit-after", "sign-before"])
def test_number_span_marks_the_number_in_the_headline(headline, number, marked):
    start, end = number_span(headline, number)
    assert headline[start:end] == marked


def test_model_points_and_repeated_source_are_tidied():
    table = read_table(QUARTERS, "q.csv")
    facts = find_facts(table)
    last = next(f for f in facts if f.kind == "change_last" and f.statement.startswith("Доля"))
    total = next(f for f in facts if f.kind == "change_total" and f.statement.startswith("Доля"))
    answer = {"suggestions": [{"fact_ids": [last.id, total.id], "headline": "Доля онлайна выросла на 3,9 п.п. в IV квартале",
                               "number": "+3,9 п.п.", "visual": "column", "why": ""}]}
    first = suggest(table, facts, "", "", _llm(answer))[0][0]
    assert first.by_model and "п. п." in first.headline and first.number == "+3,9 п. п."
    assert first.source.count("столбец") == 1  # оба кандидата из одного столбца: источник один раз


def test_unrecognized_period_order_gives_no_direction():
    """Ред-тим 17.10: «Весна 2026» не сортируется, рост по порядку строк файла был бы догадкой."""
    seasons = "Сезон;Выручка\nОсень 2026;150\nВесна 2026;120\nЛето 2026;135\n".encode()
    kinds = {f.kind for f in find_facts(read_table(seasons, "s.csv"))}
    assert not kinds & {"change_last", "change_total", "growth_count"}
    assert "leader_gap" in kinds


def test_long_series_uses_the_same_12_periods_everywhere():
    months = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
              "Ноябрь", "Декабрь")
    rows = [f"{m} {year};{100 + i}" for i, (year, m) in enumerate((y, m) for y in (2025, 2026) for m in months)]
    facts = find_facts(read_table(("Месяц;Выручка\n" + "\n".join(rows) + "\n").encode(), "m.csv"))
    total = next(f for f in facts if f.kind == "change_total")
    assert total.periods == ["Январь 2026", "Декабрь 2026"]
    assert next(f for f in facts if f.kind == "growth_count").numbers == ["11", "11"]


def test_xlsx_blank_rows_do_not_eat_the_row_limit():
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(["Регион", "Выручка"])
    for i in range(1500):
        sheet.append([f"Регион {i}", i + 1])
        sheet.append([None, None])
    buffer = io.BytesIO()
    book.save(buffer)
    assert len(read_table(buffer.getvalue(), "big.xlsx").rows) == 1500


def test_api_table_preview_comes_before_the_model(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))
    with TestClient(app) as client:
        ok = client.post("/insights/table", files={"file": ("r.csv", REGIONS, "text/csv")})
        assert ok.status_code == 200 and ok.json() == {"table_name": "r.csv", "sheet": "", "rows": 6, "columns": 3, "from_image": False}
        bad = client.post("/insights/table", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
        assert bad.status_code == 422 and "две строки" in bad.json()["detail"]


def test_code_statements_have_verbs_agreed_with_the_metric():
    """Ред-тим 17.10: запасные выводы без глагола («Выручка: рост на 18 %») читались справкой."""
    statements = [f.statement.replace(" ", " ") for f in find_facts(read_table(QUARTERS, "q.csv")) if f.kind == "change_last"]
    for start in ("Выручка выросла на 18 %", "Клиенты выросли на 22,5 %", "Доля онлайн выросла на 3,9 п. п."):
        assert any(s.startswith(start) for s in statements), start
    profit = "Квартал;Прибыль\nI кв 2026;10\nII кв 2026;8\n".encode()
    assert find_facts(read_table(profit, "p.csv"))[0].statement.replace(" ", " ").startswith("Прибыль: снижение на 20 %")


def test_wide_table_with_newest_column_first_keeps_time_order():
    """Приёмка 17.10: столбцы «2026; 2025» давали «рост» там, где спад."""
    newest_first = "Регион;2026;2025\nСевер;112;80\nЦентр;90;95\nЮг;50;60\nУрал;30;40\n".encode()
    facts = {f.kind: f for f in find_facts(read_table(newest_first, "w.csv"))}
    assert facts["rows_grew"].numbers == ["1", "4"]
    assert facts["rows_grew"].periods == ["2025", "2026"]
    assert facts["fastest_row"].numbers[0].replace(" ", " ") == "+40 %"


def test_model_loading_does_not_lock_the_deck():
    from designer.llm.client import ModelLoading
    from designer.insights.suggest import _reason
    assert not _reason(ModelLoading("грузится")).startswith("Модель недоступна")


def test_xlsx_stops_after_a_long_run_of_empty_rows():
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(["Регион", "Выручка"])
    sheet.append(["Север", 1])
    sheet.append(["Юг", 2])
    sheet.cell(row=5000, column=1, value="подпись внизу листа")
    buffer = io.BytesIO()
    book.save(buffer)
    assert len(read_table(buffer.getvalue(), "tail.xlsx").rows) == 2


def test_insight_notes_carry_source_without_model_reading():
    table = read_table(QUARTERS, "q.csv")
    facts = find_facts(table)
    revenue = next(f for f in facts if f.kind == "change_last" and f.topic.startswith("Выручка"))
    answer = {"suggestions": [{"fact_ids": [revenue.id], "headline": "Выручка выросла на 18 % в IV квартале к III",
                               "number": "+18 %", "visual": "column", "why": "показать масштаб бизнеса совету"}]}
    suggestions, _ = suggest(table, facts, "", "", _llm(answer))
    plan = DeckPlan(title="t", purpose="p", slides=[SlideIntent(id="", kind=SlideKind.title, title="t")])
    insert_insight_slides(plan, suggestions[:1])
    assert plan.slides[1].notes.startswith("Источник:") and "масштаб" not in plan.slides[1].notes


def test_plan_slides_about_insight_metrics_are_dropped():
    """Прогон колоды 17.10: план повторил темы выводов своими толкованиями и крупным числом без данных."""
    from designer.contracts import Item
    table = read_table(QUARTERS, "q.csv")
    suggestions, _ = suggest(table, find_facts(table), "", "", None)
    plan = DeckPlan(title="t", purpose="p", slides=[
        SlideIntent(id="", kind=SlideKind.title, title="Итоги 2026 года"),
        SlideIntent(id="", kind=SlideKind.bullets, title="Цель: решить, куда вкладывать в онлайн"),
        SlideIntent(id="", kind=SlideKind.section, title="Рост выручки подтверждает эффективность"),
        SlideIntent(id="", kind=SlideKind.big_number, title="Выручка демонстрирует устойчивый рост",
                    items=[Item(heading="Динамика продаж", number="Данные из CSV")]),
        SlideIntent(id="", kind=SlideKind.section, title="Клиенты расширяют базу"),
        SlideIntent(id="", kind=SlideKind.bullets, title="Три показателя задают вектор",
                    items=[Item(heading="Рост выручки подтверждает устойчивость модели")]),
        SlideIntent(id="", kind=SlideKind.section, title="Как ускорим рост онлайн-продаж в 2027 году"),
        SlideIntent(id="", kind=SlideKind.cta, title="Решение: масштабировать онлайн-канал")])
    insert_insight_slides(plan, suggestions)
    titles = [s.title for s in plan.slides]
    for dropped in ("Рост выручки подтверждает эффективность", "Выручка демонстрирует устойчивый рост",
                    "Клиенты расширяют базу", "Три показателя задают вектор"):
        assert dropped not in titles, dropped
    for kept in ("Цель: решить, куда вкладывать в онлайн", "Как ускорим рост онлайн-продаж в 2027 году",
                 "Решение: масштабировать онлайн-канал"):
        assert kept in titles, kept


def test_goal_and_step_slides_about_insight_metrics_stay():
    """Приёмка 17.10: фильтр убирал цели и шаги («Расширить онлайн-канал», цель из брифа крупным числом)."""
    from designer.contracts import Item
    table = read_table(QUARTERS, "q.csv")
    suggestions, _ = suggest(table, find_facts(table), "", "", None)
    kept = ["Расширить онлайн-канал в 2027 году", "Обеспечить рост выручки во II полугодии",
            "Ожидания совета по выручке на 2027 год", "Цель на 2027 год: довести долю онлайн до 50 %"]
    plan = DeckPlan(title="t", purpose="p", slides=[
        SlideIntent(id="", kind=SlideKind.title, title="Итоги 2026 года"),
        SlideIntent(id="", kind=SlideKind.section, title=kept[0]),
        SlideIntent(id="", kind=SlideKind.section, title=kept[1]),
        SlideIntent(id="", kind=SlideKind.section, title=kept[2]),
        SlideIntent(id="", kind=SlideKind.big_number, title=kept[3], items=[Item(heading="цель", number="50 %")]),
        SlideIntent(id="", kind=SlideKind.section, title="Уровень клиентов влияет на устойчивость дохода")])
    insert_insight_slides(plan, suggestions, brief="Итоги года. Цель на 2027: доля онлайна 50 %")
    titles = [s.title for s in plan.slides]
    for title in kept:
        assert title in titles, title
    assert "Уровень клиентов влияет на устойчивость дохода" not in titles


def test_years_inside_labels_are_periods():
    """Приёмка 17.10: «2025 год», «2024 г.» не узнавались как периоды, выводы о ходе пропадали."""
    wide = "Регион;2025 год;2026 год\nСевер;80;112\nЮг;60;50\n".encode()
    assert {f.kind for f in find_facts(read_table(wide, "w.csv"))} >= {"rows_grew", "total_change"}
    rows = "Год;Выручка\n2026 г.;177\n2024 г.;120\n2025 г.;150\n".encode()
    change = next(f for f in find_facts(read_table(rows, "y.csv")) if f.kind == "change_last")
    assert change.periods == ["2025 г.", "2026 г."]


def _book(*sheets) -> bytes:
    """Книга xlsx: каждый лист это (имя, строки, объединения)."""
    from openpyxl import Workbook
    book = Workbook()
    book.remove(book.active)
    for title, rows, merges in sheets:
        sheet = book.create_sheet(title)
        for row in rows:
            sheet.append(row)
        for merged in merges:
            sheet.merge_cells(merged)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_table_is_found_under_titles_and_two_row_header():
    """Андрей 17.10: «агент не всеяден?» на листе с заголовком над таблицей. Заголовок, источник и объединённая
    шапка в две строки больше не мешают."""
    data = _book(("Итоги", [
        ["Итоги года по регионам"], [], ["Источник: отчёт продаж"], [],
        ["Регион", "Выручка", None], [None, "2025", "2026"],
        ["Север", 80, 112], ["Центр", 95, 90], ["Юг", 60, 50]], ["A1:C1", "A3:C3", "B5:C5"]))
    table = read_table(data, "итоги.xlsx")
    assert table.headers == ["Регион", "Выручка 2025", "Выручка 2026"]
    assert table.lines == [7, 8, 9]
    assert {f.kind for f in find_facts(table)} >= {"rows_grew", "total_change"}


def test_sheet_without_table_is_skipped():
    from designer.insights import source
    data = _book(("Обложка", [["Отчёт"], ["Подготовил отдел продаж"]], []),
                 ("Данные", [["Квартал", "Выручка"], ["I кв 2026", 120], ["II кв 2026", 135], ["III кв 2026", 150]], []))
    table, facts = source.load(data, "отчёт.xlsx", None)
    assert table.sheet == "Данные" and facts


def test_text_table_gets_count_facts():
    program = ("Время;Зал;Спикер\n14:00;Космос;Иванов\n14:00;МФЗ;Петров\n14:40;Космос;Сидорова\n"
               "14:40;МФЗ;Орлова\n16:00;Космос;Ким\n").encode()
    table = read_table(program, "программа.csv")
    facts = find_facts(table)
    top = next(f for f in facts if f.kind == "count_top" and f.topic == "Зал")
    assert top.numbers[:2] == ["3", "5"] and "Космос" in top.statement
    suggestions, _ = suggest(table, facts, "", "", None)
    assert len(suggestions) >= 3 and all(s.number_at for s in suggestions)


def _picture(width=500, height=1600) -> bytes:
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for y in range(0, height, 40):
        draw.text((10, y + 10), f"строка {y // 40}", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def test_image_table_is_read_in_pieces_and_cached(tmp_path, monkeypatch):
    from designer.insights.image_table import read_image_table
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))
    calls = []

    def handler(request):
        system = json.loads(request.content)["messages"][0]["content"]
        calls.append(system)
        if "Выпиши в labels" in system:
            answer = {"labels": ["Космос", "МФЗ"]}
        elif "Это верх таблицы" in system:
            answer = {"columns": ["Время", "Зал", "Спикер"], "rows": [["14:00", "Космос", "Иванов"]]}
        else:
            answer = {"columns": ["Время", "Зал", "Спикер"], "rows": [["", "МФ3", "Петров"], ["15:00", "Космос", "Ким"], ["16:00", "Обед", ""]]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}]})

    client = LlmClient("http://test/v1", "m", transport=httpx.MockTransport(handler))
    picture = _picture()
    table = read_image_table(picture, "программа.png", client)
    assert len(calls) >= 3 and table.from_image and table.headers == ["Время", "Зал", "Спикер"]
    assert ["14:00", "МФЗ", "Петров"] in table.rows  # зал по подписи шапки, время сверху
    assert ["16:00", "", "Обед"] in table.rows  # обед не зал: уходит из столбца зала  # время сетки подписано один раз на блок
    asked = len(calls)
    again = read_image_table(picture, "программа.png", None)  # из кэша, без модели
    assert again.rows == table.rows and len(calls) == asked


def test_image_only_xlsx_goes_to_the_model(tmp_path, monkeypatch):
    """Файл Андрея 17.10: на листе заголовок, а сетка программы вставлена картинкой."""
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as SheetImage
    from designer.insights import source
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / "data"))
    book = Workbook()
    book.active.title = "Программа"
    book.active.append(["IT Community Day — деловая программа"])
    picture = tmp_path / "grid.png"
    picture.write_bytes(_picture())
    book.active.add_image(SheetImage(str(picture)), "A3")
    buffer = io.BytesIO()
    book.save(buffer)
    assert source.preview(buffer.getvalue(), "program.xlsx") == (None, True)
    with pytest.raises(TableError, match="только модель"):
        source.load(buffer.getvalue(), "program.xlsx", None)
    with TestClient(app) as client:
        shown = client.post("/insights/table", files={"file": ("program.xlsx", buffer.getvalue(), "application/octet-stream")})
        assert shown.status_code == 200 and shown.json()["from_image"] is True


def test_stop_in_browser_closes_the_model_call():
    """Ред-тим 17.10: после «Остановить» сервер дописывал ответ модели и держал её слот до таймаута."""
    import asyncio
    from designer.api.app import _wait_unless_gone

    class Gone:
        async def is_disconnected(self):
            return True

    class Client:
        closed = False

        def close(self):
            Client.closed = True

    async def run():
        task = asyncio.get_running_loop().create_future()
        return await _wait_unless_gone(task, Gone(), Client(), poll_s=0.01)

    assert asyncio.run(run()) is False and Client.closed
