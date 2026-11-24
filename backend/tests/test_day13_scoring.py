from app.cuet_clat.scoring import score_clat_response, score_cuet_response


def test_cuet_scoring_profile() -> None:
    assert score_cuet_response(selected_key="A", correct_key="A") == 5.0
    assert score_cuet_response(selected_key="B", correct_key="A") == -1.0
    assert score_cuet_response(selected_key=None, correct_key="A") == 0.0


def test_clat_scoring_profile() -> None:
    assert score_clat_response(selected_key="A", correct_key="A") == 1.0
    assert score_clat_response(selected_key="B", correct_key="A") == -0.25
    assert score_clat_response(selected_key=None, correct_key="A") == 0.0