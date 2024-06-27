from datetime import datetime, timedelta
import logging
import math
from typing import *
from xml.etree.ElementTree import Element

from etterna_analysis import app


skillsets = [
    "Stream",
    "Jumpstream",
    "Handstream",
    "Stamina",
    "Jacks",
    "Chordjacks",
    "Technical",
]

logger = logging.getLogger()

# Official EO colors
# skillset_colors = ["7d6b91", "8481db", "995fa3", "f2b5fa", "6c969d", "a5f8d3", "b0cec2"]
# Modified (saturated) EO colors
skillset_colors = [
    "#333399",
    "#6666ff",
    "#cc33ff",
    "#ff99cc",
    "#009933",
    "#66ff66",
    "#808080",
]

GRADE_NAMES = "D C B A AA AAA AAAA AAAAA".split(" ")
GRADE_THRESHOLDS = [-math.inf, 0.6, 0.7, 0.8, 0.93, 0.997, 0.99955, 0.99996]
D_THRESHOLD = GRADE_THRESHOLDS[0]
C_THRESHOLD = GRADE_THRESHOLDS[1]
B_THRESHOLD = GRADE_THRESHOLDS[2]
A_THRESHOLD = GRADE_THRESHOLDS[3]
AA_THRESHOLD = GRADE_THRESHOLDS[4]
AAA_THRESHOLD = GRADE_THRESHOLDS[5]
AAAA_THRESHOLD = GRADE_THRESHOLDS[6]
AAAAA_THRESHOLD = GRADE_THRESHOLDS[7]


def bg_color():
    return app.app.prefs.bg_color


def text_color():
    return app.app.prefs.text_color


def border_color():
    return app.app.prefs.border_color


def link_color():
    return app.app.prefs.link_color


_keep_storage = []


def keep(*args):  # an escape hatch of Python's GC
    _keep_storage.extend(args)


def wifescore_to_grade_string(wifescore: float) -> str:
    for grade_name, grade_threshold in list(zip(GRADE_NAMES, GRADE_THRESHOLDS))[::-1]:
        if wifescore >= grade_threshold:
            return grade_name
    logger.exception("this shouldn't happen")
    return "aaaaaaaaaaaaaaaa"


def num_notes(score: Any) -> int:
    return sum([int(e.text) for e in score.find("TapNoteScores")])


def extract_strs(string: str, before: str, after: str) -> Generator[str, None, None]:
    start_index = 0
    while True:
        before_index = string.find(before, start_index)
        if before_index == -1:
            break

        after_index = string.find(after, before_index)
        if after_index == -1:
            start_index = after_index + 1  # the next occurence that's not this one
            continue

        yield string[before_index + len(before) + 1 : after_index]
        start_index = after_index + len(after)


def extract_str(string: str, before: str, after: str) -> Optional[str]:
    return next(extract_strs(string, before, after), None)


# Parses date in Etterna.xml format
def parsedate(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # in this case this datetime is on midnight, in which case Etterna omits the time part
        # of the datetime. Weird behavior, but true. Found by snover
        return datetime.strptime(s, "%Y-%m-%d")


def score_within_n_months(score: Element, months: int | None = None) -> bool:
    if months is None:
        return True

    if (datetime_text := score.findtext("DateTime")) is not None:
        time_delta = datetime.now() - parsedate(datetime_text)
        return time_delta <= timedelta(365 / 12 * months)

    return True


def iter_scores(xml: Element) -> Generator[Element, None, None]:
    for chart in xml.iter("Chart"):
        for score in chart.iter("Score"):
            # is the score rating unreasonably high?
            skillset_ssrs = score.find("SkillsetSSRs")
            if skillset_ssrs is not None:
                overall_ssr = float(skillset_ssrs.findtext("Overall"))
                if overall_ssr > 40:
                    continue

            # is the score invalid (only if invalidated scores aren't shown)
            if score.findtext("EtternaValid") == "0" and app.app.prefs.hide_invalidated:
                continue

            # this score looks legit
            yield score


# Convert a float of hours to a string, e.g. "5h 35min"
def timespan_str(hours):
    minutes_total = round(hours * 60)
    hours = int(minutes_total / 60)
    minutes = minutes_total - 60 * hours
    return f"{hours}h {minutes}min"


cache_data = {}


def cache(key, data=None) -> Any:
    global cache_data

    if data is not None:  # If data was given, update cache
        cache_data[key] = data
    return cache_data.get(key)  # Return cached data


def find_parent_chart(xml: Element, score: Element):
    score_key = score.get("Key")
    return xml.find(f'.//Score[@Key="{score_key}"]/../..')


# Abbreviates a number, e.g. (with default `min_precision`):
#  1367897 -> 1367k
#  47289361 -> 47M
# The min_precision parameter controls how many digits must be visible minimum
def abbreviate(n, min_precision=2):
    num_digits = len(str(n))
    postfix_index = int((num_digits - min_precision) / 3)
    postfix = ["", "k", "M", "B", "T", "Q"][postfix_index]
    return str(round(n / 1000**postfix_index)) + postfix


def groupby(iterator, keyfunc):
    prev_key = None
    group = []
    for value in iterator:
        key = (keyfunc)(value)

        if key == prev_key:
            group.append(value)
        else:
            yield prev_key, group
            prev_key = key
            group = []

    yield prev_key, group
