from dataclasses import dataclass
import os
from typing import *
from xml.etree.ElementTree import Element

from etterna_analysis import app, util
from etterna_analysis.savegame_analysis import ReplaysAnalysis as RustReplaysAnalysis
from etterna_analysis.savegame_analysis import FastestComboInfo
from etterna_analysis.util import parsedate


@dataclass
class FastestCombo:
    length: int
    speed: float
    start_second: float
    end_second: float
    score: Any


class ReplaysAnalysis:
    def __init__(self):
        self.scores = []
        self.datetimes = []
        self.manipulations: list[float] = []
        self.wife2_wifescores: list[float] | None = (
            None  # this one doesn't need timingdata
        )
        self.offset_mean: float = 0
        self.notes_per_column = [0, 0, 0, 0]
        self.cbs_per_column = [0, 0, 0, 0]
        self.longest_mcombo: tuple[int, Element | None] = (0, None)
        self.num_near_hits: float | int = 0.0
        self.sub_93_offset_buckets: dict[int, int] = {}
        self.standard_deviation: float = 0
        self.total_notes: int = 0
        self.fastest_combo: FastestCombo | None = None
        self.fastest_jack: FastestCombo | None = None
        self.fastest_acc: FastestCombo | None = None
        # these three do
        self.current_wifescores: list[float] | None = None
        self.new_wifescores: list[float] | None = None
        self.wifescore_scores: list[Any] | None = None


def analyze(xml: Element, replays: str) -> ReplaysAnalysis | None:
    """
    This function is responsible for replay analysis. Every chart that uses replay data has it from
    here.

    It works by:
    1) Collecting all chartkeys into a list.
    2) Passing the list to the `savegame_analysis` library (written in Rust, so it's blazingly fast
        :tm:)
    3) Transfer the data from Rust's `ReplaysAnalysis` object to an instance of the
        `ReplaysAnalysis` class written in Python.
        Note: this involves traversing the xml file once again, to collect score datetimes and
        score xml objects.

    Args:
        xml (Element): The `Etterna.xml` Element object.
        replays (str): Path to the replays folder (I think)

    Returns:
        ReplaysAnalysis | None: Replays analysis object.

    Example:
        # Create the python representation from the rust representation
        r = ReplaysAnalysis()
        chartkeys: list[str] = []
        wifescores: list[float] = []
        packs: list[str] = []
        songs: list[str] = []
        rates: list[float] = []
        all_scores: list[Element] = []
        songs_root: str = ""

        # Populate the list elements
        ...

        rustr = RustReplaysAnalysis(
            prefix, chartkeys, wifescores, packs, songs, rates, songs_root
        )
        r = ReplaysAnalysis()

        r.fastest_combo = convert_combo_info(rustr.fastest_combo)
        r.fastest_jack = convert_combo_info(rustr.fastest_jack)
        r.fastest_acc = convert_combo_info(rustr.fastest_acc)
        r.manipulations = rustr.manipulations
        ...
    """

    r = ReplaysAnalysis()

    chartkeys: list[str] = []
    wifescores: list[float] = []
    packs: list[str] = []
    songs: list[str] = []
    rates: list[float] = []
    all_scores: list[Element] = []
    for chart in xml.iter("Chart"):
        pack = chart.get("Pack")
        song = chart.get("Song")

        if pack is None or song is None:
            continue

        if "Generation Rock" in song and "German Dump Mini Pack" in pack:
            continue  # this file is borked

        for scoresat in chart:
            rate = (
                float(rate_str)
                if (rate_str := scoresat.get("Rate") is not None)
                else 0.0
            )
            for score in scoresat:
                # We exclude failed scores because those exhibit some.. weird behavior in the replay
                # file. not sure what exactly it is, but somehow the wifescore in the xml doesn't
                # match the wifescore we get when recalculating it manually using the replay file
                # We don't want such outliers in our graphs, so - be gone, failed scores
                if score.findtext("Grade") == "Failed":
                    continue

                chartkeys.append(score.get("Key"))
                wifescores.append(float(score.findtext("SSRNormPercent")))
                packs.append(pack)
                songs.append(song)
                rates.append(rate)
                all_scores.append(score)

    prefix = os.path.join(replays, "a")[:-1]  # why?
    print("Starting replays analysis...")
    rustr = RustReplaysAnalysis(
        prefix, chartkeys, wifescores, packs, songs, rates, app.app.prefs.songs_root
    )
    print("Done with replays analysis")

    def convert_combo_info(rust_combo_info: FastestComboInfo):
        return FastestCombo(
            length=rust_combo_info.length,
            speed=rust_combo_info.speed,
            start_second=rust_combo_info.start_second,
            end_second=rust_combo_info.end_second,
            score=None,
        )  # this field is set below, in the score xml iteration

    r.fastest_combo = convert_combo_info(rustr.fastest_combo)
    r.fastest_jack = convert_combo_info(rustr.fastest_jack)
    r.fastest_acc = convert_combo_info(rustr.fastest_acc)

    r.manipulations = rustr.manipulations

    if len(r.manipulations) == 0:
        # When no replay could be parsed correctly. For cases when
        # someone selects a legacy folder with 'correct' file names,
        # but unexcepted (legacy) content. Happened to Providence
        util.logger.warning("No valid replays found at all in the directory")
        return None

    # this is NOT part of replays analysis. this is xml analysis. this is in here anyway because
    # it's easier. this should really be moved into a separate xml analysis module (in case I'll
    # ever get around implementing that...?)
    r.total_notes = 0
    for tap_note_scores in xml.iter("TapNoteScores"):
        judgements = ["Miss", "W1", "W2", "W3", "W4", "W5"]
        r.total_notes += sum(int(tap_note_scores.findtext(x)) for x in judgements)

    r.wife2_wifescores = rustr.wife2_wifescores
    r.offset_mean = rustr.deviation_mean
    r.notes_per_column = rustr.notes_per_column
    r.cbs_per_column = rustr.cbs_per_column
    r.num_near_hits = sum(r.notes_per_column) / sum(r.cbs_per_column)
    r.standard_deviation = rustr.standard_deviation

    for i, num_hits in enumerate(rustr.sub_93_offset_buckets):
        r.sub_93_offset_buckets[i - 180] = num_hits

    r.current_wifescores = rustr.current_wifescores
    r.new_wifescores = rustr.new_wifescores

    r.wifescore_scores = [
        all_scores[i] for i in rustr.timing_info_dependent_score_indices
    ]
    r.scores = [all_scores[score_index] for score_index in rustr.score_indices]
    r.datetimes = [parsedate(score.findtext("DateTime")) for score in r.scores]

    # replace the scorekeys returned from Rust replays analysis with the actual score elements
    for score in r.scores:
        scorekey = score.get("Key")
        if scorekey == rustr.longest_mcombo[1]:
            r.longest_mcombo = (
                rustr.longest_mcombo[0],
                util.find_parent_chart(xml, score),
            )
        if scorekey == rustr.fastest_combo_scorekey:
            r.fastest_combo.score = score
        if scorekey == rustr.fastest_jack_scorekey:
            r.fastest_jack.score = score
        if scorekey == rustr.fastest_acc_scorekey:
            r.fastest_acc.score = score

    # print(r.fastest_acc)
    # print(rustr.fastest_acc_scorekey)

    return r
