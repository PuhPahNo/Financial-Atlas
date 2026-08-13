"""SEC companyfacts must stay bounded in the long-lived API process."""
from types import SimpleNamespace

from app.providers import sec_edgar


def test_companyfacts_evicts_before_parsing_next_large_document(monkeypatch):
    observed_sizes = []

    def get_or_set(_namespace, key, **_kwargs):
        observed_sizes.append(len(sec_edgar._FACTS_MEM))
        return SimpleNamespace(value={"key": key, "facts": {}})

    sec_edgar._FACTS_MEM.clear()
    monkeypatch.setattr(sec_edgar.cache, "get_or_set", get_or_set)
    provider = sec_edgar.SecEdgarProvider()
    try:
        provider._companyfacts("1")
        provider._companyfacts("2")
        provider._companyfacts("3")

        assert observed_sizes == [0, 1, 1]
        assert list(sec_edgar._FACTS_MEM) == ["2", "3"]
    finally:
        sec_edgar._FACTS_MEM.clear()
