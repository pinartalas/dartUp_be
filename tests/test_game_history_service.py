from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.game import GameStatus, GameType
from app.schemas.game_history import GameHistoryQueryParams, HistoryPeriod
from app.services.game_history_service import GameHistoryService
from tests.conftest import create_active_game, create_finished_game


def test_lists_only_finished_games_for_owner(db_session, owner, other_user):
    finished = create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 18, 12, 0, 0),
    )
    create_active_game(db_session, owner_id=owner.id)
    create_finished_game(
        db_session,
        owner_id=other_user.id,
        player_user_id=other_user.id,
        finished_at=datetime(2026, 5, 17, 12, 0, 0),
    )

    service = GameHistoryService(db_session)
    response = service.get_user_game_history(
        owner.id,
        GameHistoryQueryParams(page=1, limit=20),
    )

    assert response.pagination.total == 1
    assert len(response.data) == 1
    assert response.data[0].date == date(2026, 5, 18)
    assert response.data[0].games[0].game_id == finished.game_uuid
    assert response.data[0].games[0].result == "WIN"


def test_groups_games_by_finished_date(db_session, owner):
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 18, 10, 0, 0),
    )
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 18, 18, 0, 0),
        is_winner=False,
    )
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 17, 12, 0, 0),
    )

    response = GameHistoryService(db_session).get_user_game_history(
        owner.id,
        GameHistoryQueryParams(page=1, limit=20),
    )

    assert response.pagination.total == 3
    assert [group.date for group in response.data] == [
        date(2026, 5, 18),
        date(2026, 5, 17),
    ]
    assert len(response.data[0].games) == 2
    assert response.data[0].games[0].finished_at > response.data[0].games[1].finished_at


def test_pagination(db_session, owner):
    for day in range(5):
        create_finished_game(
            db_session,
            owner_id=owner.id,
            player_user_id=owner.id,
            finished_at=datetime(2026, 5, 10 + day, 12, 0, 0),
        )

    service = GameHistoryService(db_session)
    page_one = service.get_user_game_history(
        owner.id,
        GameHistoryQueryParams(page=1, limit=2),
    )
    page_two = service.get_user_game_history(
        owner.id,
        GameHistoryQueryParams(page=2, limit=2),
    )

    assert page_one.pagination.total == 5
    assert page_one.pagination.total_pages == 3
    assert len(page_one.data) <= 2
    game_ids_page_one = {g.game_id for group in page_one.data for g in group.games}
    game_ids_page_two = {g.game_id for group in page_two.data for g in group.games}
    assert game_ids_page_one.isdisjoint(game_ids_page_two)


def test_period_last_week_filter(db_session, owner):
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime.utcnow() - timedelta(days=2),
    )
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime.utcnow() - timedelta(days=20),
    )

    response = GameHistoryService(db_session).get_user_game_history(
        owner.id,
        GameHistoryQueryParams(period=HistoryPeriod.LAST_WEEK, page=1, limit=20),
    )

    assert response.pagination.total == 1


def test_custom_period_requires_dates():
    with pytest.raises(ValidationError):
        GameHistoryQueryParams(period=HistoryPeriod.CUSTOM, page=1, limit=20)


def test_custom_period_filter(db_session, owner):
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 10, 12, 0, 0),
    )
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 20, 12, 0, 0),
    )

    response = GameHistoryService(db_session).get_user_game_history(
        owner.id,
        GameHistoryQueryParams(
            period=HistoryPeriod.CUSTOM,
            startDate=date(2026, 5, 15),
            endDate=date(2026, 5, 25),
            page=1,
            limit=20,
        ),
    )

    assert response.pagination.total == 1


def test_game_type_filter(db_session, owner):
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 18, 12, 0, 0),
        game_type="x01",
    )
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 17, 12, 0, 0),
        game_type="cricket",
        game_variant=None,
    )

    response = GameHistoryService(db_session).get_user_game_history(
        owner.id,
        GameHistoryQueryParams(
            gameType=GameType.CRICKET,
            page=1,
            limit=20,
        ),
    )

    assert response.pagination.total == 1
    assert response.data[0].games[0].game_type == "cricket"


def test_non_finished_status_filter_returns_empty(db_session, owner):
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 18, 12, 0, 0),
    )

    response = GameHistoryService(db_session).get_user_game_history(
        owner.id,
        GameHistoryQueryParams(status=GameStatus.ACTIVE, page=1, limit=20),
    )

    assert response.pagination.total == 0
    assert response.data == []


def test_statistics_for_owner_player(db_session, owner):
    create_finished_game(
        db_session,
        owner_id=owner.id,
        player_user_id=owner.id,
        finished_at=datetime(2026, 5, 18, 12, 0, 0),
        with_turns=True,
    )

    stats = GameHistoryService(db_session).get_user_game_history(
        owner.id,
        GameHistoryQueryParams(page=1, limit=20),
    ).data[0].games[0].statistics

    assert stats.total_turns == 2
    assert stats.successful_turns == 1
    assert stats.bust_count == 1
    assert stats.accuracy == 50.0
