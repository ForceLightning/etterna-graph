class SkillTimeline:
    def __init__(
        self, ssr_vectors: list[list[float]], session_ids: list[int]
    ) -> None: ...
    agg_rating_vectors: list[list[float]]
    agg_overall_ratings: list[float]
    session_rating_vectors: list[list[float]]
    session_overall_ratings: list[float]

class FastestComboInfo:
    start_second: float
    end_second: float
    length: int
    speed: float

class ReplaysAnalysis:
    score_indices: list[int]
    manipulations: list[float]
    deviation_mean: float
    notes_per_column: list[int]
    cbs_per_column: list[int]
    longest_mcombo: tuple[int, str]
    offset_buckets: list[int]
    sub_93_offset_buckets: list[int]
    standard_deviation: float
    fastest_combo: FastestComboInfo
    fastest_combo_scorekey: str
    fastest_jack: FastestComboInfo
    fastest_jack_scorekey: str
    fastest_acc: FastestComboInfo
    fastest_acc_scorekey: str
    wife2_wifescores: list[float]
    timing_info_dependent_score_indices: list[int]
    current_wifescores: list[float]
    new_wifescores: list[float]

    def __init__(
        self,
        prefix: str,
        scorekeys: list[str],
        wifescores: list[float],
        packs: list[str],
        songs: list[str],
        rates: list[float],
        songs_root: str,
    ) -> None: ...
