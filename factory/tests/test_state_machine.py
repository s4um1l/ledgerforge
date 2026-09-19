from factory.schemas import HAPPY_PATH, State


def test_happy_path_ends_accepted():
    assert HAPPY_PATH[0] is State.CREATED
    assert HAPPY_PATH[-1] is State.ACCEPTED


def test_every_failure_state_is_terminal():
    failures = [s for s in State if s.is_failure]
    assert len(failures) == 7
    assert all(s.is_terminal for s in failures)


def test_progress_states_are_not_terminal():
    for state in HAPPY_PATH[:-1]:
        assert not state.is_terminal
        assert not state.is_failure


def test_accepted_is_terminal_but_not_a_failure():
    assert State.ACCEPTED.is_terminal
    assert not State.ACCEPTED.is_failure
