from dataclasses import asdict, is_dataclass

from pm_lol.models import Market, QuoteSnapshot


def test_market_and_quote_are_dataclasses():
    assert is_dataclass(Market)
    assert is_dataclass(QuoteSnapshot)


def test_market_keeps_large_token_ids_as_text():
    market = Market(
        market_id="2530922",
        condition_id="0xabc",
        slug="lol-ktc-sgw-2026-06-15-game2",
        title="LoL: KT Rolster Challengers vs Saigon Warriors - Game 2 Winner",
        outcomes=["KT Rolster Challengers", "Saigon Warriors"],
        token_ids=["100172814846746500028191734405612966589475835807067790171955690167538278072521"],
        volume=74955.37,
    )

    assert asdict(market)["token_ids"][0].startswith("100172")
