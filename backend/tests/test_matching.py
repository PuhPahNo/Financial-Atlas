from dataclasses import dataclass

from app.core.matching import best_name_match


@dataclass
class Named:
    name: str


def test_best_name_match_handles_dicts_objects_and_punctuation():
    dictionaries = [{"id": 1, "name": "Quality & Momentum"}, {"id": 2, "name": "Income"}]
    objects = [Named("S&P High Fade"), Named("Cash Compounders")]

    assert best_name_match(dictionaries, "quality momentum")["id"] == 1
    assert best_name_match(objects, "please use the s&p high fade model").name == "S&P High Fade"
    assert best_name_match(objects, "  Cash   Compounders ").name == "Cash Compounders"
    assert best_name_match(objects, "") is None
