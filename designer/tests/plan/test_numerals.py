from designer.plan.numerals import digits_from_speech


def test_times_and_cardinals_from_live_fragment():
    assert digits_from_speech("Отчёт теперь готов к половине девятого утра, а не к одиннадцати.") == (
        "Отчёт теперь готов к 8:30 утра, а не к 11.")
    assert digits_from_speech("Пилот мы запустили на двух витринах, на это ушло шесть недель.") == (
        "Пилот мы запустили на 2 витринах, на это ушло 6 недель.")
    assert digits_from_speech("Затраты выросли на двенадцать процентов, опозданий два в месяц вместо девяти.") == (
        "Затраты выросли на 12 процентов, опозданий 2 в месяц вместо 9.")


def test_clock_idioms():
    assert digits_from_speech("к восьми тридцати") == "к 8:30"
    assert digits_from_speech("без четверти девять") == "8:45"
    assert digits_from_speech("четверть десятого") == "9:15"
    assert digits_from_speech("в полдевятого") == "в 8:30"
    assert digits_from_speech("к половине первого") == "к 12:30"


def test_compound_numbers_and_fractions():
    assert digits_from_speech("сто двадцать пять человек и двадцать один день") == "125 человек и 21 день"
    assert digits_from_speech("полторы тысячи часов") == "1500 часов"
    assert digits_from_speech("два с половиной миллиона рублей") == "2,5 миллиона рублей"
    assert digits_from_speech("в две тысячи двадцать шестом году") == "в 2026 году"
    assert digits_from_speech("пятьсот сорок семь витрин, ноль ошибок") == "547 витрин, 0 ошибок"


def test_words_that_are_not_numbers_stay():
    assert digits_from_speech("одна из задач") == "одна из задач"
    assert digits_from_speech("тысячи людей") == "тысячи людей"
    assert digits_from_speech("семью мы не трогаем") == "семью мы не трогаем"
    assert digits_from_speech("во втором квартале") == "во втором квартале"
    assert digits_from_speech("три первых слайда") == "3 первых слайда"


def test_millions_keep_the_scale_word():
    assert digits_from_speech("затраты полтора миллиона рублей в квартал") == "затраты 1,5 миллиона рублей в квартал"
    assert digits_from_speech("два миллиарда") == "2 миллиарда"
    assert digits_from_speech("четыре с половиной из пяти") == "4,5 из 5"
    assert digits_from_speech("с четырёх минут до полутора") == "с 4 минут до 1,5"
