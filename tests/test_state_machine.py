import core.state_machine as state_machine


def test_initial_state_is_idle():
    sm = state_machine.JarvisState()
    assert sm.current == state_machine.State.IDLE
    assert sm.is_idle() is True
    assert sm.is_busy() is False


def test_transition_updates_current_state():
    sm = state_machine.JarvisState()
    sm.transition(state_machine.State.TRIGGERED)
    assert sm.current == state_machine.State.TRIGGERED


def test_transition_through_full_lifecycle_back_to_idle():
    sm = state_machine.JarvisState()
    sequence = [
        state_machine.State.TRIGGERED,
        state_machine.State.LISTENING,
        state_machine.State.PLANNING,
        state_machine.State.EXECUTING,
        state_machine.State.SPEAKING,
        state_machine.State.IDLE,
    ]
    for expected in sequence:
        sm.transition(expected)
        assert sm.current == expected


def test_is_busy_true_for_any_non_idle_state():
    sm = state_machine.JarvisState()
    for s in [
        state_machine.State.TRIGGERED,
        state_machine.State.LISTENING,
        state_machine.State.PLANNING,
        state_machine.State.EXECUTING,
        state_machine.State.SPEAKING,
    ]:
        sm.transition(s)
        assert sm.is_busy() is True
        assert sm.is_idle() is False


def test_is_idle_false_after_leaving_idle_and_true_after_returning():
    sm = state_machine.JarvisState()
    sm.transition(state_machine.State.EXECUTING)
    assert sm.is_idle() is False
    sm.transition(state_machine.State.IDLE)
    assert sm.is_idle() is True
