"""Unit tests for unified normalization, transliteration, and match key generation."""

import unicodedata
from src.utils.normalization import (
    build_match_key,
    clean_text_for_storage,
    fuzzy_name_match,
    replace_dash_context,
)


class TestNormalization:
    def test_dash_context_replacement(self):
        # 1. Dash context in titles between words / years
        title_with_fffd = "Athletics at the 2008 Summer Olympics \ufffd Men's marathon"
        res = replace_dash_context(title_with_fffd)
        assert " - " in res
        assert "Athletics at the 2008 Summer Olympics - Men's marathon" == res

        # 2. En-dash and em-dash standardized
        en_dash_title = "Canoeing at the 2012 Summer Olympics \u2013 Men's K-2"
        res_en = replace_dash_context(en_dash_title)
        assert " - " in res_en

        # 3. Word-internal U+FFFD must NOT insert a dash
        word_fffd = "K\ufffdk\ufffdny"
        res_word = replace_dash_context(word_fffd)
        assert "-" not in res_word
        assert res_word == "Kkny"

    def test_transliteration_map(self):
        # Turkish dotless i and soft g
        t1 = build_match_key("Taner Sağır")
        assert "taner sagir" == t1

        # Scandinavian ø and æ
        t2 = build_match_key("Kjetil André Aamodt")
        assert "kjetil andre aamodt" == t2

        t3 = build_match_key("Marit Söderström")
        assert "marit soderstrom" == t3

        # German sharp s
        t4 = build_match_key("Emese Szász")
        assert "emese szasz" == t4

    def test_nfc_storage_clean(self):
        name = "Naim Süleymanoğlu\x07"  # with bell control character
        cleaned = clean_text_for_storage(name)
        assert unicodedata.is_normalized("NFC", cleaned)
        assert "\x07" not in cleaned
        assert cleaned == "Naim Süleymanoğlu"

    def test_build_match_key_equivalence(self):
        # Clean vs diacritic vs dash variation should produce identical match keys
        k1 = build_match_key("Athletics at the 2008 Summer Olympics \ufffd Men's marathon")
        k2 = build_match_key("Athletics at the 2008 Summer Olympics – Men's marathon")
        k3 = build_match_key("athletics at the 2008 summer olympics - men's marathon")

        assert k1 == k2
        assert k2 == k3

    def test_fuzzy_name_match(self):
        assert fuzzy_name_match("Rudolf Dombi", "Dombi Rudolf") is True
        assert fuzzy_name_match("Naim Süleymanoğlu", "Naim Suleymanoglu") is True
        assert fuzzy_name_match("Usain Bolt", "Michael Phelps") is False
