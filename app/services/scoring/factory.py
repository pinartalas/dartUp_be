from app.core.exceptions import GameServiceError
from app.services.scoring.base import GameScoringService
from app.services.scoring.cricket_scoring import CricketScoringService
from app.services.scoring.x01_scoring import X01ScoringService

_SCORING_SERVICES: dict[str, GameScoringService] = {
    "x01": X01ScoringService(),
    "cricket": CricketScoringService(),
}


def get_scoring_service(game_type: str) -> GameScoringService:
    service = _SCORING_SERVICES.get(game_type)
    if service is None:
        raise GameServiceError(f"Unsupported game type: {game_type}", status_code=400)
    return service
