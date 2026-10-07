"""Unit tests for TwoStageJudge Stage 1 deterministic matcher."""

from src.eval.judge import TwoStageJudge


class TestTwoStageJudgeStage1:
    def setup_method(self):
        # We don't need a real gateway for Stage 1 testing
        self.judge = TwoStageJudge(gateway=None)

    def test_exact_scalar_match(self):
        assert self.judge.stage1_deterministic_match("Chen Ding", ["Chen Ding"]) is True
        assert self.judge.stage1_deterministic_match("26", ["26"]) is True

    def test_normalized_diacritics_match(self):
        # Transliteration & accents
        assert self.judge.stage1_deterministic_match("Martina Sablikova", ["Martina Sáblíková"]) is True
        assert self.judge.stage1_deterministic_match("Naim Suleymanoglu", ["Naim Süleymanoğlu"]) is True

    def test_strict_equality_no_substring_pass(self):
        # Substring containment MUST NOT pass Stage 1
        assert self.judge.stage1_deterministic_match("Chen", ["Chen Ding"]) is False
        assert self.judge.stage1_deterministic_match("Ding", ["Chen Ding"]) is False
        assert self.judge.stage1_deterministic_match("2", ["26"]) is False
        assert self.judge.stage1_deterministic_match("26 nations competed", ["26"]) is False

    def test_multi_entity_set_match(self):
        # Comma-separated list matching set of gold answers
        cand = "Laura Trott, Dani King, Joanna Rowsell"
        gold = ["Dani King", "Laura Trott", "Joanna Rowsell"]
        assert self.judge.stage1_deterministic_match(cand, gold) is True

    def test_concatenated_gold_team_names_match(self):
        # Concatenated gold answer split into set
        cand = "Dani King, Laura Trott, Joanna Rowsell"
        gold = ["Dani KingLaura TrottJoanna Rowsell"]
        assert self.judge.stage1_deterministic_match(cand, gold) is True

        cand2 = "Erik Lesser, Daniel Böhm, Arnd Peiffer and Simon Schempp"
        gold2 = ["Erik LesserDaniel BöhmArnd PeifferSimon Schempp"]
        assert self.judge.stage1_deterministic_match(cand2, gold2) is True

    def test_celtic_mac_name_not_split(self):
        cand = "Rosannagh MacLennan"
        gold = ["Rosannagh MacLennan"]
        assert self.judge.stage1_deterministic_match(cand, gold) is True

    def test_empty_or_none(self):
        assert self.judge.stage1_deterministic_match("", ["Chen Ding"]) is False
        assert self.judge.stage1_deterministic_match("Chen Ding", []) is False
