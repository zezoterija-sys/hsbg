from game.actions import Action, ActionType
from game.scheduler import RecruitScheduler


def test_scheduler_starts_all_seats_together():
    scheduler = RecruitScheduler(interaction_budget=3)
    scheduler.begin_phase([0, 1, 2])

    assert scheduler.eligible_player_ids() == (0, 1, 2)
    assert scheduler.remaining_budget(0) == 3
    assert scheduler.logical_time(0) == 0


def test_scheduler_advances_only_submitting_seat():
    scheduler = RecruitScheduler(interaction_budget=3)
    scheduler.begin_phase([0, 1])

    scheduler.commit_action(0, Action(ActionType.REFRESH))

    assert scheduler.logical_time(0) == 1
    assert scheduler.logical_time(1) == 0
    assert scheduler.eligible_player_ids() == (1,)

    scheduler.commit_action(1, Action(ActionType.FREEZE))
    assert scheduler.eligible_player_ids() == (0, 1)


def test_zero_cost_choice_remains_resolvable_after_budget_exhaustion():
    scheduler = RecruitScheduler(interaction_budget=1)
    scheduler.begin_phase([0, 1])

    scheduler.commit_action(0, Action(ActionType.PLAY_MINION))

    assert scheduler.is_finished(0)
    assert scheduler.remaining_budget(0) == 0

    choice = Action(ActionType.CHOOSE_OPTION, option_idx=0)
    assert scheduler.can_submit(0, choice, pending_choice=True)
    scheduler.commit_action(0, choice)
    assert scheduler.logical_time(0) == 1


def test_pending_choices_take_priority_over_next_timed_batch():
    scheduler = RecruitScheduler(interaction_budget=3)
    scheduler.begin_phase([0, 1, 2])

    scheduler.commit_action(0, Action(ActionType.BUY_MINION, target_idx=0))
    scheduler.commit_action(1, Action(ActionType.BUY_MINION, target_idx=0))
    scheduler.commit_action(2, Action(ActionType.BUY_MINION, target_idx=0))

    assert scheduler.eligible_player_ids() == (0, 1, 2)
    assert scheduler.eligible_player_ids(
        pending_choice_player_ids=[1]
    ) == (1,)


def test_end_turn_finishes_without_consuming_budget():
    scheduler = RecruitScheduler(interaction_budget=3)
    scheduler.begin_phase([0])

    scheduler.commit_action(0, Action(ActionType.END_TURN))

    assert scheduler.is_finished(0)
    assert scheduler.remaining_budget(0) == 3
    assert scheduler.logical_time(0) == 0


def test_priority_orders_only_resolution_not_eligibility():
    scheduler = RecruitScheduler(interaction_budget=3)
    scheduler.begin_phase([0, 1])

    batch = [
        (0, Action(ActionType.REFRESH)),
        (1, Action(ActionType.REFRESH)),
    ]

    assert scheduler.order_batch(batch, [1, 0]) == [batch[1], batch[0]]
    assert scheduler.eligible_player_ids() == (0, 1)
