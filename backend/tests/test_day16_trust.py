from app.adaptive_remediation.validation import reject_unsafe_value


def test_poison_nested_session_rejected() -> None:
    class FakeSession:
        pass

    ok, code = reject_unsafe_value({"payload": FakeSession()})
    assert ok is False
    assert code is not None


def test_orm_like_rejected() -> None:
    class FakeModel:
        __module__ = "app.models.learner"

    ok, code = reject_unsafe_value(FakeModel())
    assert ok is False