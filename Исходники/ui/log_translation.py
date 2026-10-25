"""Переводит технические сообщения журнала, сохраняя обозначения переменных."""

import re

PHRASES={
    'Traceback (most recent call last):':'Стек вызовов (последний вызов в конце):',
    'FileNotFoundError':'Файл не найден', 'PermissionError':'Нет доступа',
    'RuntimeError':'Ошибка выполнения', 'ValueError':'Недопустимое значение',
    'AssertionError':'Ошибка внутренней проверки', 'TimeoutError':'Превышено время ожидания',
    'No such file or directory':'Файл или папка отсутствует',
    'dense-statevector':'полный вектор амплитуд', 'dense+exact-symmetric':'полная и точная симметричная модели',
    'exact-symmetric':'точная симметричная модель',
    'без реального квантового ускорения.':'', 'Quantum Algorithm 2':'Квантовый алгоритм 2',
    'perfect matching':'полное паросочетание', 'state-vector':'вектор амплитуд',
    'Blackburn layer process ended':'Процесс классического построения завершён',
    'Invalid Blackburn reply':'Некорректный ответ классического вычислителя',
    'Blackburn session not ready':'Классический вычислитель не готов',
    'Missing Blackburn counters':'Отсутствуют счётчики классического вычислителя',
    'Incomplete Blackburn result':'Неполный результат классического вычислителя',
    'Blackburn DROP failed':'Не удалось освободить уровень классического вычислителя',
    'Blackburn shutdown failed':'Не удалось завершить классический вычислитель',
    'Blackburn exit':'Код завершения классического вычислителя',
    'Invalid Blackburn collision vertices':'Недопустимые вершины коллизии',
    'C++ Blackburn edge failed independent hash/Sigma validation':'Ребро C++ не прошло независимую проверку хэш-кода и контрольной суммы',
    'sigma constraint':'условие контрольной суммы', 'Linking-блок':'Связывающий блок',
    'linking-блок':'связывающий блок', 'Grover':'Гровера', 'Blackburn':'Классический алгоритм',
    'Quantum':'Квантовый алгоритм', 'Algorithm':'Алгоритм', 'matching':'совпадений',
    'Backend':'Вычислитель', 'backend':'вычислитель', 'success':'успешно',
    'failed':'ошибка', 'timeout':'время ожидания истекло', 'cancelled':'отменено',
}


def translate_log(message):
    text=str(message)
    for source,target in PHRASES.items():
        text=re.sub(r'(?<![\w])'+re.escape(source)+r'(?![\w])',lambda _:target,text)
    text=re.sub(r'File ("[^"\n]+"), line (\d+), in ([^\n]+)',r'Файл \1, строка \2, функция \3',text)
    return text.replace('—','–')
