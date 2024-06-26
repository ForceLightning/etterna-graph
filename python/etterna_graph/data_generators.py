from collections import Counter
from datetime import datetime, timedelta
import math
from typing import *
from xml.etree.ElementTree import Element

from etterna_graph import app, util
from etterna_graph.replays_analysis import ReplaysAnalysis
from etterna_graph.replays_analysis import FastestCombo
from etterna_graph.util import cache, iter_scores, parsedate


"""
This file holds all the so-called data generators. Those take save data
and generate data points out of them. There are multiple data generator
functions here, one for each plot
"""


def gen_manip(xml, analysis):
    x = analysis.datetimes
    y = [math.log(max(m * 100, 0.01)) / math.log(10) for m in analysis.manipulations]
    ids = analysis.scores
    return ((x, y), ids)


def score_to_wifescore(score):
    overall = score.findtext(".//Overall")
    overall = float(overall) if overall else 0.0
    return overall


def score_to_accuracy(score):
    percent = float(score.findtext("SSRNormPercent")) * 100
    if percent <= -400:
        return None  # Those are weird
    if percent > 100:
        return None
    return -(math.log(100 - percent) / math.log(10))


def score_to_ma(score):
    tap_note_scores = score.find("TapNoteScores")
    marvelouses = float(tap_note_scores.findtext("W1"))
    perfects = float(tap_note_scores.findtext("W2"))

    ma = marvelouses / perfects
    return math.log(ma) / math.log(10)  # For log scale support


def map_scores(
    xml, mapper, *mapper_args, discard_errors=True, brush_color_over_10_notes=None
) -> tuple:
    x, y = [], []
    ids = []
    brushes = []
    for score in iter_scores(xml):
        if discard_errors:
            try:
                value = (mapper)(score, *mapper_args)
            except Exception:
                continue
        else:
            value = (mapper)(score, *mapper_args)
        if value is None:
            continue

        x.append(parsedate(score.findtext("DateTime")))
        y.append(value)
        ids.append(score)
        if brush_color_over_10_notes:
            tap_note_scores = score.find("TapNoteScores")
            if tap_note_scores:
                judgements = ["Miss", "W1", "W2", "W3", "W4", "W5"]
                total_notes = sum(int(tap_note_scores.findtext(x)) for x in judgements)
            else:
                total_notes = 500  # just assume 100 as a default yolo

            brushes.append(brush_color_over_10_notes if total_notes > 10 else "#AAAAAA")

    if brush_color_over_10_notes:
        return (((x, y), ids), brushes)
    else:
        return ((x, y), ids)


def gen_wifescore(xml):
    return map_scores(xml, score_to_wifescore)


def gen_accuracy(xml, color):
    return map_scores(xml, score_to_accuracy, brush_color_over_10_notes=color)


def gen_ma(xml):
    return map_scores(xml, score_to_ma)


# Returns list of sessions where a session is [(Score, datetime)]
# A session is defined to end when there's no play in 60 minutes or more
def divide_into_sessions(xml: Element) -> list[list[tuple[Element, datetime]]]:
    if sessions := cache("sessions_division_cache"):
        return sessions

    session_end_threshold = timedelta(hours=1)

    scores = list(iter_scores(xml))
    datetimes = [parsedate(s.find("DateTime").text) for s in scores]
    zipped = zip(scores, datetimes)
    zipped = sorted(zipped, key=lambda pair: pair[1])

    # zipped is a list of chronologically sorted (score object, datetime) tuples

    prev_score_datetime = zipped[0][1]  # first datetime
    current_session = [
        zipped[0]
    ]  # list of (score object, datetime) tuples in current session
    sessions: list[list[tuple[Element, datetime]]] = (
        []
    )  # list of sessions where every session is like `current_session`
    for score, score_datetime in zipped[1:]:
        score_interval = score_datetime - prev_score_datetime
        # check if timedelta between two scores is too high
        if score_interval > session_end_threshold:
            sessions.append(current_session)
            current_session = []
        current_session.append((score, score_datetime))
        prev_score_datetime = score_datetime
    sessions.append(current_session)
    _ = cache("sessions_division_cache", sessions)

    return sessions


def gen_wifescore_frequencies(xml: Element) -> tuple[list[int], list[int]]:
    # e.g. the 0.70 bucket corresponds to all scores between 0.70 and 0.71 (not 0.695 and 0.705!)
    frequencies = {percent: 0 for percent in range(70, 100)}

    for score in iter_scores(xml):
        if ssr_norm_percent := score.findtext("SSRNormPercent"):
            wifescore = float(ssr_norm_percent)
            percent = round(wifescore * 100)
            if percent in frequencies:
                frequencies[percent] += 1
    return list(frequencies.keys()), list(frequencies.values())


# Return format: [[a,a...],[b,b...],[c,c...],[d,d...],[e,e...],[f,f...],[g,g...]]
def gen_week_skillsets(xml: Element) -> tuple[list[datetime], list[List[float]]]:
    # returns an integer week from 0-51
    def week_from_score(score: Element) -> int:
        datetime = parsedate(score.findtext("DateTime"))
        week = datetime.isocalendar()[1]
        return week

    chronological_scores = sorted(
        iter_scores(xml), key=lambda s: s.findtext("DateTime")
    )

    week_start_datetimes: List[datetime] = []
    diffsets: List[List[float]] = []

    for week, scores_in_week in util.groupby(chronological_scores, week_from_score):
        diffset = [0, 0, 0, 0, 0, 0, 0]
        for score in scores_in_week:
            skillset_ssrs = score.find("SkillsetSSRs")
            if skillset_ssrs is None:
                continue
            diffs = [float(diff.text) for diff in skillset_ssrs[1:]]
            main_diff = diffs.index(max(diffs))
            diffset[main_diff] += 1

        total = sum(diffset)
        if total == 0:
            continue
        diffset = [diff / total * 100 for diff in diffset]

        year = scores_in_week[0].findtext("DateTime")[:4]
        week_start_datetime = datetime.strptime(f"{year} {week} {0}", "%Y %W %w")

        diffsets.append(diffset)
        week_start_datetimes.append(week_start_datetime)

    return (week_start_datetimes, diffsets)


def gen_plays_by_hour(xml: Element) -> tuple[list[int], list[int]]:
    num_plays = [0] * 24
    for score in iter_scores(xml):
        datetime = parsedate(score.find("DateTime").text)
        num_plays[datetime.hour] += 1

    # I tried to use a datetime as key (would be nicer to display), but
    # it doesn't play nicely with matplotlib, so we need to use an
    # integer to represent the hour of the day.
    # return {time(hour=i): num_plays[i] for i in range(24)}
    return list(range(24)), num_plays


def gen_most_played_charts(xml: Element, num_charts: int) -> list[tuple[Element, int]]:
    charts_num_plays: list[tuple[Element, int]] = []
    for chart in xml.iter("Chart"):
        score_filter = lambda s: float(s.findtext("SSRNormPercent")) > 0.5
        num_plays = len([s for s in iter_scores(chart) if score_filter(s)])
        if num_plays > 0:
            charts_num_plays.append((chart, num_plays))

    charts_num_plays.sort(key=lambda pair: pair[1], reverse=True)
    return charts_num_plays[:num_charts]


def gen_hours_per_skillset(xml: Element):
    hours = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    for score in iter_scores(xml):
        skillset_ssrs = score.find("SkillsetSSRs")
        if skillset_ssrs is None:
            continue
        diffs = [float(diff.text) for diff in skillset_ssrs[1:]]
        main_diff = diffs.index(max(diffs))

        length_hours = float(score.findtext("PlayedSeconds")) / 3600
        hours[main_diff] += length_hours

    return hours


def gen_hours_per_week(xml: Element) -> tuple[list[datetime], list[int | float]]:
    scores = iter_scores(xml)
    pairs = [(s, parsedate(s.findtext("DateTime"))) for s in scores]  # (score, date)
    pairs.sort(key=lambda pair: pair[1])  # Sort by datetime

    weeks: dict[datetime, int | float] = {}
    week_end = pairs[0][1]  # First (earliest) datetime
    week_start = week_end - timedelta(weeks=1)
    i = 0
    while i < len(pairs):
        score, dt = pairs[i][0], pairs[i][1]
        if dt < week_end:
            score_seconds = float(score.findtext("PlayedSeconds")) or 0
            weeks[week_start] += score_seconds / 3600
            i += 1
        else:
            week_start += timedelta(weeks=1)
            week_end += timedelta(weeks=1)
            weeks[week_start] = 0

    return (list(weeks.keys()), list(weeks.values()))


def calc_average_hours_per_day(xml: Element, timespan: timedelta | None = None):
    timespan = timespan if timespan else timedelta(days=365 / 2)
    scores: Element = sorted(iter_scores(xml), key=lambda s: s.findtext("DateTime"))

    total_hours = 0
    for score in scores:
        total_hours += float(score.findtext("PlayedSeconds")) / 3600

    return total_hours / timespan.days


# OPTIONAL PLOTS BEGINNING


def gen_hit_distribution_sub_93(xml: Element, analysis):
    buckets = analysis.sub_93_offset_buckets
    return (list(buckets.keys()), list(buckets.values()))


def gen_idle_time_buckets(xml: Element) -> tuple[range, list[int]]:
    # Each bucket is 5 seconds. Total 10 minutes is tracked
    buckets = [0] * 600

    a, b = 0, 0

    scores: list[tuple[Element, float]] = []
    for scoresat in xml.iter("ScoresAt"):
        rate = (
            float(rate_str) if (rate_str := scoresat.get("Rate")) is not None else 0.0
        )
        score_tuples: list[tuple[Element, float]] = []
        for score in scoresat.iter("Score"):
            if (skillset_ssrs := score.find("SkillsetSSRs")) is not None:
                overall_ssr = float(skillset_ssrs.findtext("Overall"))
                if overall_ssr > 40:
                    continue
            if score.findtext("EtternaValid") == "0" and app.app.prefs.hide_invalidated:
                continue
            score_tuples.append((score, rate))

        scores.extend(score_tuples)

    # Sort scores by datetime, oldest first
    scores.sort(key=lambda pair: pair[0].findtext("DateTime"))

    last_play_end = None
    for score, rate in scores:
        a += 1
        datetime = util.parsedate(score.findtext("DateTime"))
        survive_seconds = float(score.findtext("PlayedSeconds"))
        # print(survive_seconds, rate)
        length = timedelta(seconds=survive_seconds * rate)

        # print("Datetime:", datetime)
        # print("Play length:", str(length)[:-7], "(according to PlayedSeconds)")
        if last_play_end is not None:
            idle_time = datetime - last_play_end
            if idle_time >= timedelta():
                bucket_index = int(idle_time.total_seconds() // 5)
                if bucket_index < len(buckets):
                    buckets[bucket_index] += 1
            else:
                # print("Negative idle time!")
                b += 1

        last_play_end = datetime + length
        # print("Finished", last_play_end)
        # print()

    # ~ keys = [i * 5 for i in range(len(buckets))]
    keys = range(len(buckets))
    return (keys, buckets)


def gen_session_length(xml):
    sessions = divide_into_sessions(xml)
    x, y = [], []
    for s in sessions:
        x.append(s[0][1])  # Datetime [1] of first play [0] in session
        y.append((s[-1][1] - s[0][1]).total_seconds() / 60)  # Length in minutes

    return (x, y)


def gen_session_plays(xml):
    sessions = divide_into_sessions(xml)
    nums_plays = [len(session) for session in sessions]
    nums_sessions_with_x_plays = Counter(nums_plays)
    return (
        list(nums_sessions_with_x_plays.keys()),
        list(nums_sessions_with_x_plays.values()),
    )


# Currently broken
"""def gen_cb_probability(xml, analysis):
	# {combo length: (base number, cb number)
	base, cbs = analysis.combo_occurences, analysis.cbs_on_combo_len
	
	# Find first combo that was never reached (0), starting with combo 1
	max_combo = base.index(0, 1)
	result = {i: int(cbs[i]/base[i]) for i in range(max_combo)[:10] if base[i] >= 0}
	x_list = range(max_combo)
	return (x_list, [cbs[i]/base[i] for i in x_list])"""


def gen_plays_per_week(xml: Element):
    datetimes = [parsedate(s.findtext("DateTime")) for s in iter_scores(xml)]
    datetimes.sort()

    weeks: dict[datetime, int] = {}
    week_end = datetimes[0]
    week_start = week_end - timedelta(weeks=1)
    i = 0
    while i < len(datetimes):
        if datetimes[i] < week_end:
            weeks[week_start] += 1
            i += 1
        else:
            week_start += timedelta(weeks=1)
            week_end += timedelta(weeks=1)
            weeks[week_start] = 0

    return (list(weeks.keys()), list(weeks.values()))


# OPTIONAL PLOTS END


def gen_scores_per_hour(xml):
    hours_of_day = []
    overalls = []
    ids = []
    for score in xml.iter("Score"):
        skillset_ssrs = score.find("SkillsetSSRs")
        if not skillset_ssrs:
            continue
        overalls.append(float(skillset_ssrs.findtext("Overall")))

        dt = parsedate(score.findtext("DateTime"))
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        hour_of_day = (dt - midnight).total_seconds() / 3600
        hours_of_day.append(hour_of_day)

        ids.append(score)

    return (hours_of_day, overalls), ids


def gen_avg_score_per_hour(xml):
    nums_scores = [0.0] * 24
    score_sums = [0.0] * 24
    for score in xml.iter("Score"):
        skillset_ssrs = score.find("SkillsetSSRs")
        if not skillset_ssrs:
            continue

        hour = parsedate(score.findtext("DateTime")).hour
        nums_scores[hour] += 1

        score_sums[hour] += float(skillset_ssrs.findtext("Overall"))

    x, y = [], []
    for i, (num_scores, score_sum) in enumerate(zip(nums_scores, score_sums)):
        x.append(i)
        try:
            y.append(score_sum / num_scores)
        except ZeroDivisionError:
            y.append(0)
    return x, y


# the Python wrapping adds about +30% execution time
def calc_ratings_for_sessions(
    xml: Element,
) -> list[tuple[list[tuple[Element, datetime]], list[float], list[float]]]:
    if ratings_for_sessions := cache("calc_ratings_for_sessions"):
        return ratings_for_sessions

    from etterna_graph.savegame_analysis import SkillTimeline

    sessions: list[list[tuple[Element, datetime]]] = []
    session_ids: list[int] = []
    # Each row is a session, column being a SSR category.
    ssr_lists: list[list[float]] = [[], [], [], [], [], [], []]
    for session_i, session in enumerate(divide_into_sessions(xml)):
        session_has_been_added = False

        for score, _ in session:
            player_skillsets = score.find("SkillsetSSRs")
            if player_skillsets is None:
                continue

            if not session_has_been_added:
                session_has_been_added = True
                sessions.append(session)

            session_ids.append(session_i)

            for i in range(7):
                if (value_str := player_skillsets[i + 1].text) is not None:
                    value = float(value_str)
                    ssr_lists[i].append(value)

    timeline = SkillTimeline(ssr_lists, session_ids)

    # TODO: Move overall ratings calculation to rust
    def ratings_list(
        i: int, rating_vectors: list[list[float]], overall_ratings: list[float]
    ) -> list[float]:
        ratings = [rating_vector[i] for rating_vector in rating_vectors]
        overall = overall_ratings[i]
        ratings.insert(0, overall)
        return ratings

    agg_session_rating_pairs = [
        (
            session,
            ratings_list(i, timeline.agg_rating_vectors, timeline.agg_overall_ratings),
        )
        for (i, session) in enumerate(sessions)
    ]

    indiv_session_rating_pairs = [
        (
            session,
            ratings_list(
                i, timeline.session_rating_vectors, timeline.session_overall_ratings
            ),
        )
        for (i, session) in enumerate(sessions)
    ]

    # session_rating_pairs format:
    # [
    #   (<session>, [25, 17, 41, 23, 25, 26, 12]),
    #   (<session>, [25, 25, 26, 12, 17, 41, 23]),
    # ]
    _ = cache("calc_agg_ratings_for_sessions", agg_session_rating_pairs)
    _ = cache("calc_indiv_ratings_for_sessions", indiv_session_rating_pairs)

    session_ratings = [
        (a[0], a[1], b[1])
        for (a, b) in zip(agg_session_rating_pairs, indiv_session_rating_pairs)
    ]

    return session_ratings


def gen_session_rating_improvement(xml: Element):
    datetimes, lengths, sizes, ids = [], [], [], []

    previous_overall = 0
    for session, ratings, _ in calc_ratings_for_sessions(xml):
        # Overall-rating delta
        overall_delta = ratings[0] - previous_overall

        # Add bubble size, clamping to [4;100] pixels
        size = math.sqrt(max(0, overall_delta)) * 40
        sizes.append(min(150, max(4, size)))

        # Append session datetime and length
        datetimes.append(session[0][1])
        length = (session[-1][1] - session[0][1]).total_seconds() / 60
        lengths.append(length)

        ids.append((previous_overall, ratings[0], len(session), length))

        previous_overall = ratings[0]

    return ((datetimes, lengths, sizes), ids)


# Returns tuple of `(max_combo_chart_element, max_combo_int)`
def find_longest_combo(xml: Element) -> tuple[Element | None, int]:
    max_combo_chart = None
    max_combo = 0
    for chart in xml.iter("Chart"):
        for score in iter_scores(chart):
            if (max_combo_str := score.findtext("MaxCombo")) is not None:
                combo = int(max_combo_str)
                if combo > max_combo:
                    max_combo = combo
                    max_combo_chart = chart
    return max_combo_chart, max_combo


# Returns dict with pack names as keys and the respective "pack liking"
# as value. The liking value is currently simply the amount of plays in the pack
def generate_pack_likings(xml: Element, months: int | None) -> dict[str, int]:
    likings: dict[str, int] = {}
    for chart in xml.iter("Chart"):
        num_relevant_plays = 0
        for score in iter_scores(chart):
            if util.score_within_n_months(score, months):
                num_relevant_plays += 1
        pack = chart.get("Pack")

        if pack not in likings and pack:
            likings[pack] = 0
        elif pack in likings:
            likings[pack] += num_relevant_plays

    return likings


def calculate_total_wifescore(xml: Element, months: int = 6) -> float:
    weighted_sum = 0
    num_notes_sum = 0
    for score in iter_scores(xml):
        if not util.score_within_n_months(score, months):
            continue

        num_notes = util.num_notes(score)
        num_notes_sum += util.num_notes(score)

        if (ssr_norm_percent := score.findtext("SSRNormPercent")) is not None:
            wifescore = float(ssr_norm_percent)
            weighted_sum += wifescore * num_notes

    try:
        return weighted_sum / num_notes_sum
    except ZeroDivisionError:
        return 0


def gen_skillset_development(
    xml: Element, aggregated: bool = True
) -> tuple[list[datetime], list[float]]:
    datetimes, all_ratings = [], []
    for (
        agg_session,
        agg_ratings,
        indiv_ratings,
    ) in calc_ratings_for_sessions(xml):
        datetimes.append(agg_session[0][1])
        all_ratings.append(agg_ratings if aggregated else indiv_ratings)
    return (datetimes, all_ratings)


def gen_cmod_over_time(xml: Element):
    # These values were gathered through a quick-and-dirty screen recording based test
    perspective_mod_multipliers = {
        "Incoming": 1 / 1.2931,
        "Space": 1 / 1.2414,
        "Hallway": 1 / 1.2931,
        "Distant": 1 / 1.2759,
    }

    datetime_cmod_map = {}
    for score in xml.iter("Score"):
        modifiers = score.findtext("Modifiers").split(", ")
        cmod = None
        receptor_size = None
        perspective_mod_multiplier = 1
        for modifier in modifiers:
            if cmod is None and modifier.startswith("C") and modifier[1:].isdecimal():
                try:
                    cmod = float(modifier[1:])
                except ValueError:
                    print("huh a weird cmod:", modifier)
                    continue
            elif receptor_size is None and modifier.endswith("Mini"):
                mini_percentage_string = modifier[:-4]
                if mini_percentage_string == "":
                    receptor_size = 0.5
                else:
                    if not mini_percentage_string.endswith("% "):
                        continue  # false positive
                    mini = float(mini_percentage_string[:-2]) / 100
                    receptor_size = 1 - mini / 2
            elif any(
                persp_mod in modifier
                for persp_mod in perspective_mod_multipliers.keys()
            ):
                # modifier can either be something like "Distant" or "50% Distant"
                tokens = modifier.split(" ")
                if len(tokens) == 1:
                    perspective_mod_multiplier = perspective_mod_multipliers[tokens[0]]
                elif len(tokens) == 2:
                    perspective_mod_multiplier = perspective_mod_multipliers[tokens[1]]

                    # factor in the "50%" (or whichever number it is)
                    perspective_strength = float(tokens[0][:-1]) / 100
                    perspective_mod_multiplier **= perspective_strength
                else:
                    print(f"uhh this shouldn't happen? '{modifier}'")
        if receptor_size is None:
            receptor_size = 1

        # TODO: decide if MMod should be counted as CMod in this function

        if cmod is None:
            continue  # player's using xmod or something

        effective_cmod = cmod * receptor_size * perspective_mod_multiplier

        dt = parsedate(score.findtext("DateTime"))
        datetime_cmod_map[dt] = effective_cmod

    datetimes = list(sorted(datetime_cmod_map.keys()))
    cmods = [datetime_cmod_map[dt] for dt in datetimes]
    return datetimes, cmods


def count_nums_grades(xml):
    grades = []
    for score in util.iter_scores(xml):
        percent = float(score.findtext("SSRNormPercent"))
        grade = sum(percent >= t for t in util.GRADE_THRESHOLDS) - 1
        grades.append(util.GRADE_NAMES[grade])
    return Counter(grades)


def gen_text_most_played_charts(xml: Element, limit: int = 5):
    text = ["Most played charts:"]
    charts = gen_most_played_charts(xml, num_charts=limit)
    i = 1
    for chart, num_plays in charts:
        if num_plays < app.app.prefs.msgbox_num_scores_threshold:
            num_remaining = len(charts) - i
            text.append(
                f"[{num_remaining} charts with less than {app.app.prefs.msgbox_num_scores_threshold} scores not shown]"
            )
            break

        pack, song = chart.get("Pack"), chart.get("Song")
        text.append(f'{i}) "{pack}" -> "{song}" with {num_plays} scores')
        i += 1

    if limit is not None:
        text.append(
            f'<a href="#read_more" style="color: {util.link_color()}">Show all</a>'
        )

    return "<br>".join(text)


def gen_text_longest_sessions(xml, limit=5):
    sessions = divide_into_sessions(xml)
    new_sessions = []  # like `sessions`, but with total gameplay seconds annotated
    for session in sessions:
        total_gameplay_seconds = sum(
            float(score[0].findtext("PlayedSeconds")) for score in session
        )
        new_sessions.append((session, total_gameplay_seconds))
    sessions = new_sessions
    sessions.sort(key=lambda pair: pair[1], reverse=True)  # Sort by length

    num_not_shown = 0
    num_shown = 0
    text = ["Longest sessions:"]
    i = 1
    for session, gameplay_seconds in sessions:
        num_plays = len(session)

        if num_plays < app.app.prefs.msgbox_num_scores_threshold:
            num_not_shown += 1
            continue

        total_seconds = (session[-1][1] - session[0][1]).total_seconds()

        datetime = str(session[0][1])[:-3]  # Cut off seconds
        text.append(
            f"{i}) {datetime}, {gameplay_seconds/60:.0f} min gameplay, "
            f"{total_seconds/60:.0f} min total, {num_plays} scores"
        )
        i += 1

        num_shown += 1
        if limit and num_shown >= limit:
            break

    if limit is None:  # this is a msgbox
        text.append(
            f"[{num_not_shown} sessions with less than {app.app.prefs.msgbox_num_scores_threshold} scores not shown]"
        )
    else:  # this is an inline text box
        text.append(
            f'<a href="#read_more" style="color: {util.link_color()}">Show all</a>'
        )

    return "<br>".join(text)


def gen_text_skillset_hours(xml):
    hours = gen_hours_per_skillset(xml)

    text = ["Hours spent training each skillset:"]
    for i in range(7):
        skillset = util.skillsets[i]
        text.append(f"- {skillset}: {util.timespan_str(hours[i])}")

    return "<br>".join(text)


# Parameter r is the ReplaysAnalysis
def gen_text_general_info(xml, r):
    from dateutil.relativedelta import relativedelta

    total_notes = 0
    for tap_note_scores in xml.iter("TapNoteScores"):
        total_notes += sum(int(e.text) for e in tap_note_scores)
    total_notes_string = util.abbreviate(total_notes, min_precision=3)

    scores = list(iter_scores(xml))
    num_charts = len(list(xml.iter("Chart")))
    hours = sum(float(s.findtext("PlayedSeconds")) / 3600 for s in scores)
    first_play_date = min([parsedate(s.findtext("DateTime")) for s in scores])
    duration = relativedelta(datetime.now(), first_play_date)

    grades = count_nums_grades(xml)
    # ~ grades_string_1 = ", ".join(f"{name}: {grades[name]}" for name in ("AAAA", "AAA", "AA"))
    # ~ grades_string_2 = ", ".join(f"{name}: {grades[name]}" for name in ("A", "B", "C", "D"))
    grades_string = ", ".join(
        f"{name}: {grades[name]}" for name in "AAAA AAA AA A B C D".split()
    )
    grade_names = list(reversed(util.GRADE_NAMES))

    best_aaa = (None, 0)
    best_aaaa = (None, 0)
    for score in iter_scores(xml):
        wifescore = float(score.findtext("SSRNormPercent"))
        skillset_ssrs = score.find("SkillsetSSRs")
        if skillset_ssrs is None:
            continue
        overall = float(skillset_ssrs.findtext("Overall"))

        if wifescore < util.AAA_THRESHOLD:
            pass  # we don't care about sub-AAA scores
        elif wifescore < util.AAAA_THRESHOLD:
            if overall > best_aaa[1]:
                best_aaa = (score, overall)
        else:
            if overall > best_aaaa[1]:
                best_aaaa = (score, overall)

    def get_score_desc(score, overall) -> str:
        if score is None:
            return "[none]"
        chart = util.find_parent_chart(xml, score)
        dt = score.findtext("DateTime")
        wifescore = float(score.findtext("SSRNormPercent"))
        pack = chart.get("Pack")
        song = chart.get("Song")
        return f'{overall:.2f}, {wifescore*100:.2f}% - "{song}" ({pack}) - {dt[:10]}'

    return "<br>".join(
        [
            f"You started playing {duration.years} years {duration.months} months ago",
            f"Total hours spent playing: {round(hours)} hours",
            f"Number of scores: {len(scores)}",
            f"Number of unique files played: {num_charts}",
            f"Grades: {grades_string}",
            # ~ f"Grades: {grades_string_1}",
            # ~ f"{util.gen_padding_from('Grades: ')}{grades_string_2}",
            f"Total arrows hit: {total_notes_string}",
            f"Best AAA: {get_score_desc(best_aaa[0], best_aaa[1])}",
            f"Best AAAA: {get_score_desc(best_aaaa[0], best_aaaa[1])}",
        ]
    )


# a stands for ReplaysAnalysis
def gen_text_general_analysis_info(xml: Element, a: ReplaysAnalysis | None) -> str:
    long_mcombo_str = "[please load replay data]"
    if a:  # If ReplaysAnalysis is avilable
        if chart := a.longest_mcombo[1]:
            long_mcombo_chart = f'"{chart.get("Song")}" ({chart.get("Pack")})'
            long_mcombo_str = f"{a.longest_mcombo[0]} on {long_mcombo_chart}"

    chart, combo = find_longest_combo(xml)
    long_combo_chart = f'"{chart.get("Song")}" ({chart.get("Pack")})'
    long_combo_str = f"{combo} on {long_combo_chart}"

    if a:
        cb_ratio_per_column = [
            cbs / total for (cbs, total) in zip(a.cbs_per_column, a.notes_per_column)
        ]
        cbs_string = ", ".join([f"{round(100 * r, 2)}%" for r in cb_ratio_per_column])

        mean_string = f"{round(a.offset_mean * 1000, 1)}ms"

        sd_string = f"{a.standard_deviation:.2f} ms"

        worst_cb_rush_weight_so_far = 0
        worst_cb_rush_index = None
        for i, (old_wifescore, new_wifescore, score) in enumerate(
            zip(a.current_wifescores, a.new_wifescores, a.wifescore_scores)
        ):
            if abs(new_wifescore - 0.9808) < 0.001:
                continue  # REMEMBER
            # weight = (1 - old_wifescore) / (1 - new_wifescore) # REMEMBER
            weight = new_wifescore - old_wifescore

            # prevent tiny files dominating the cb rush intensity leaderboard
            if util.num_notes(score) < 500:
                continue

            # this is not technically needed, but it's not particularly pleasant if we have smth
            # like "this score is only 55% but without cb rushes it would be 75%!! wooo!!!!" cuz
            # even 75% is utterly laughable. We prefer scores that are _mostly clean_ except for
            # the unfair cb rushes
            if new_wifescore < 0.93:
                continue

            if weight > worst_cb_rush_weight_so_far:
                worst_cb_rush_weight_so_far = weight
                worst_cb_rush_index = i

        def make_worst_cb_rush_string(index):
            score = a.wifescore_scores[index]
            chart = util.find_parent_chart(xml, score)
            pack = chart.get("Pack")
            song = chart.get("Song")
            old = a.current_wifescores[index]
            new = a.new_wifescores[index]
            dt = score.findtext("DateTime")[:10]
            return f"{old*100:.2f}%, {new*100:.2f}% without unfair cb rush - {song} ({pack}) {dt}"

        worst_cb_rush_string = (
            make_worst_cb_rush_string(worst_cb_rush_index)
            if worst_cb_rush_index
            else ""
        )
    else:
        cbs_string = "[please load replay data]"
        mean_string = "[please load replay data]"
        sd_string = "[please load replay data]"
        worst_cb_rush_string = "[please load replay data]"

    session_secs = int(xml.find("GeneralData").findtext("TotalSessionSeconds"))
    play_secs = int(xml.find("GeneralData").findtext("TotalGameplaySeconds"))
    if session_secs == 0:  # Happened for BanglesOtter, for whatever reason
        play_percentage = 0
    else:
        play_percentage = round(100 * play_secs / session_secs)

    median_score_increase = round(calc_median_score_increase(xml), 1)

    average_hours = calc_average_hours_per_day(xml)
    average_hours_str = util.timespan_str(average_hours)

    session_date_threshold = datetime.now() - timedelta(days=7)
    sessions = divide_into_sessions(xml)
    num_sessions = len([s for s in sessions if s[0][1] > session_date_threshold])

    total_wifescore = calculate_total_wifescore(xml, months=6)
    total_wifescore_str = f"{round(total_wifescore * 100, 2)}%"

    def gen_fastest_combo_string(cmb: None | FastestCombo) -> str:
        if cmb is None:
            return "[please load replay data]"
        elif cmb.score is None:
            return "[couldn't access cache.db]"
        chart = util.find_parent_chart(xml, cmb.score)
        pack = chart.get("Pack")
        song = chart.get("Song")
        wifescore = float(cmb.score.findtext("SSRNormPercent"))
        dt = cmb.score.findtext("DateTime")

        return (
            f"NPS={cmb.speed:.2f} ({cmb.length} notes, from "
            f'{cmb.start_second:.1f}s to {cmb.end_second:.1f}s) on "{song}" '
            f"({pack}), {wifescore*100:.2f}%"
        )

    return "<br>".join(
        [
            f"You spend {play_percentage}% of your sessions in gameplay",
            f"Total CB percentage per column (left to right): {cbs_string}",
            f"Median score increase when immediately replaying a chart: {median_score_increase}%",
            f"Mean hit offset: {mean_string}",
            f"Overall standard deviation: {sd_string}",
            f"Average hours per day (last 6 months): {average_hours_str}",
            f"Number of sessions, last 7 days: {num_sessions}",
            f"Average wifescore last 6 months is {total_wifescore_str}",
            f"Longest combo: {long_combo_str}",
            f"Longest marvelous combo: {long_mcombo_str}",
            f"Fastest combo 100+ notes: {gen_fastest_combo_string(a and a.fastest_combo)}",
            f"Fastest jack 30 notes: {gen_fastest_combo_string(a and a.fastest_jack)}",
            f"Fastest accurate combo 100+ notes: {gen_fastest_combo_string(a and a.fastest_acc)}",
            f"Worst unfair cb rush ever: {worst_cb_rush_string}",
        ]
    )


def gen_text_most_played_packs(xml, limit=10, months: int | None = None) -> str:
    likings = generate_pack_likings(xml, months)

    sorted_packs = sorted(likings, key=likings.get, reverse=True)
    best_packs = sorted_packs[:limit]

    first_line = "Most played packs (" + (
        f"last {months} months" if months else "all time"
    )
    if limit:
        first_line += (
            f' - <a href="toggle" style="color: {util.link_color()}">toggle</a>'
        )
    first_line += ")"

    text = [first_line]
    for i, pack in enumerate(best_packs):
        if pack == "":
            pack_str = '<span style="color: #777777">[no name]</span>'
        else:
            pack_str = pack
        text.append(f"{i+1}) {pack_str} with {likings[pack]} plays")

    if limit is not None:
        text.append(
            f'<a href="#read_more" style="color: {util.link_color()}">Show all</a>'
        )

    return "<br>".join(text)


# Calculate the median score increase, when playing a chart twice
# in direct succession
def calc_median_score_increase(xml):
    from statistics import median

    score_increases = []

    for chart in xml.iter("ScoresAt"):
        # Chronologically sorted scores
        scores = sorted(iter_scores(chart), key=lambda s: s.findtext("DateTime"))

        for i in range(0, len(scores) - 1):
            datetime_1 = parsedate(scores[i].findtext("DateTime"))
            datetime_2 = parsedate(scores[i + 1].findtext("DateTime"))
            time_delta = datetime_2 - datetime_1
            play_time = float(scores[i].findtext("PlayedSeconds"))
            idle_time = time_delta.total_seconds() - play_time

            # If the same chart is played twice within 60 seconds
            if idle_time < 60:
                score_1 = float(scores[i].findtext("SSRNormPercent"))
                score_2 = float(scores[i + 1].findtext("SSRNormPercent"))
                score_increase = 100 * (score_2 - score_1)
                score_increases.append(score_increase)

    if len(score_increases) == 0:
        return 0
    else:
        return median(score_increases)
