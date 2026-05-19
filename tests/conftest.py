from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.game import Game, GamePlayer, Turn
from app.models.user import User
from app.schemas.game import GameStatus


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def owner(db_session):
    user = User(
        email="owner@test.com",
        full_name="Owner",
        auth_provider="google",
        provider_user_id="owner-1",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_user(db_session):
    user = User(
        email="other@test.com",
        full_name="Other",
        auth_provider="google",
        provider_user_id="other-1",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_finished_game(
    db_session,
    *,
    owner_id: int,
    player_user_id: int | None,
    finished_at: datetime,
    game_type: str = "x01",
    game_variant: int = 501,
    is_winner: bool = True,
    with_turns: bool = True,
) -> Game:
    game = Game(
        owner_id=owner_id,
        game_type=game_type,
        game_variant=game_variant,
        settings={},
        status=GameStatus.FINISHED.value,
        started_at=finished_at - timedelta(minutes=10),
        finished_at=finished_at,
        turn_sequence=2 if with_turns else 0,
    )
    db_session.add(game)
    db_session.flush()

    player = GamePlayer(
        game_id=game.id,
        user_id=player_user_id,
        name="Player One",
        player_order=0,
        current_score=0,
        total_darts_thrown=6,
        total_points_scored=120,
        is_winner=is_winner,
    )
    db_session.add(player)
    db_session.flush()

    game.winner_player_id = player.id if is_winner else None
    if not is_winner:
        opponent = GamePlayer(
            game_id=game.id,
            user_id=None,
            name="Opponent",
            player_order=1,
            current_score=0,
            total_darts_thrown=6,
            total_points_scored=80,
            is_winner=True,
        )
        db_session.add(opponent)
        db_session.flush()
        game.winner_player_id = opponent.id

    if with_turns:
        turn_one = Turn(
            game_id=game.id,
            player_id=player.id,
            turn_number=1,
            turn_score=60,
            is_bust=False,
        )
        turn_two = Turn(
            game_id=game.id,
            player_id=player.id,
            turn_number=2,
            turn_score=0,
            is_bust=True,
        )
        db_session.add_all([turn_one, turn_two])

    db_session.commit()
    db_session.refresh(game)
    return game


def create_active_game(db_session, *, owner_id: int) -> Game:
    game = Game(
        owner_id=owner_id,
        game_type="x01",
        game_variant=501,
        settings={},
        status=GameStatus.ACTIVE.value,
        started_at=datetime.utcnow(),
    )
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)
    return game
