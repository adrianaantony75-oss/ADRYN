import pytest

from adryn.reviews import record_review, review_history


def test_reviews_are_append_only_and_survive_new_runs(tmp_path):
    path = tmp_path / "reviews.sqlite"
    record_review(path, "run-1", "C1", "Analyst", "Investigating", "Payment issue needs review")
    record_review(path, "run-2", "C1", "Analyst", "Resolved", "Payment reconciled")
    history = review_history(path, "C1")
    assert history.run_id.tolist() == ["run-2", "run-1"]
    assert review_history(path, "C2").empty
    with pytest.raises(ValueError):
        record_review(path, "run-2", "C1", "", "Resolved", "No reviewer")
