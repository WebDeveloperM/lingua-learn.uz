"""The key vocabulary of a Part: reading a pasted list of words (the panel's "many words at once" box).

A line reads `word /transcription/ | meaning | example`, the way a card looks. Only the word and its Uzbek meaning are
needed. The transcription may also stand in a column of its own, so that a row copied from a spreadsheet works too
(columns: word, transcription, meaning, example).
"""
import re

from .models import KeyWord

FIELDS = ('word', 'transcription', 'meaning', 'example')
LABELS = {'word': "so'z", 'transcription': 'talaffuz', 'meaning': "ma'no", 'example': 'misol'}
LIMITS = {name: KeyWord._meta.get_field(name).max_length for name in FIELDS}
MAX_WORDS = 300
MAX_PROBLEMS = 5  # of more wrong lines than this only the first ones are listed

# A column ends at a | or at a tab (spaces around it do not count; two tabs in a row leave an empty column between them).
COLUMNS = re.compile(r'[^\S\t]*[|\t][^\S\t]*')
SLASHED = re.compile(r'^/\s*([^/]+?)\s*/$')                    # /ˈpensl/
WORD_AND_SLASHED = re.compile(r'^(.*\S)\s+/\s*([^/]+?)\s*/$')  # pencil /ˈpensl/
FORMAT = "so'z /talaffuz/ | o'zbekcha ma'no | misol"


def _split(line):
    """(word, transcription, meaning, example) of one line as typed, or None when it has too many columns.

    With four columns they are exactly those (a row copied from a spreadsheet, where an empty cell is an empty
    column). With fewer, empty columns are skipped (`water | | suv`), the transcription is the part in slashes, stuck
    to the word or in a column of its own, and what remains is the word, the meaning and the example in that order.
    """
    columns = COLUMNS.split(line.strip('  '))
    if len(columns) > len(FIELDS):
        return None
    if len(columns) == len(FIELDS):
        word, transcription, meaning, example = columns
        slashed = SLASHED.match(transcription)
        return word, slashed.group(1) if slashed else transcription, meaning, example
    word, rest = columns[0], [column for column in columns[1:] if column]
    transcription = ''
    glued = WORD_AND_SLASHED.match(word)
    if glued:
        word, transcription = glued.groups()
    else:
        for index, column in enumerate(rest):
            slashed = SLASHED.match(column)
            if slashed:
                transcription = slashed.group(1)
                del rest[index]
                break
    return word, transcription, rest[0] if rest else '', rest[1] if len(rest) > 1 else ''


def parse_key_words(text):
    """The words of the text as dicts with the keys of FIELDS, and what is wrong with it: (entries, problems)."""
    entries, problems = [], []
    for number, line in enumerate((text or '').splitlines(), start=1):
        if not line.strip():
            continue
        fields = _split(line)
        if fields is None:
            problems.append(f"{number}-qator: ko'pi bilan 4 ta ustun bo'lishi mumkin ({FORMAT}). "
                            f"«|» belgisi so'z, ma'no yoki misolning ichida ishlatilmasin.")
            continue
        entry = {name: ' '.join(value.split()) for name, value in zip(FIELDS, fields)}
        if not entry['word']:
            problems.append(f"{number}-qator: so'z yozilmagan ({FORMAT}).")
        elif not entry['meaning']:
            problems.append(f"{number}-qator: «{entry['word']}» uchun o'zbekcha ma'no yozilmagan ({FORMAT}).")
        else:
            for name in FIELDS:
                if len(entry[name]) > LIMITS[name]:
                    problems.append(f"{number}-qator: {LABELS[name]} {LIMITS[name]} belgidan oshmasligi kerak.")
                    break
            else:
                entries.append(entry)
    if len(entries) > MAX_WORDS:
        problems.append(f"Bitta Part'da {MAX_WORDS} tadan ko'p so'z bo'lmaydi (hozir {len(entries)} ta).")
    if len(problems) > MAX_PROBLEMS:
        problems = problems[:MAX_PROBLEMS] + [f"…va yana {len(problems) - MAX_PROBLEMS} ta xato bor."]
    return entries, problems
