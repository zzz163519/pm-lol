from __future__ import annotations

from typing import Any

from pm_lol.models import DraftSnapshot, Game, GameStateSnapshot, Match


class LoLEsportsClient:
    def __init__(self, language: str = "en-US", api_key: str | None = None) -> None:
        self.language = language
        self.api_key = api_key

    def get_leagues(self) -> dict[str, Any]:
        return self._get_persisted("getLeagues")

    def get_schedule(self) -> dict[str, Any]:
        return self._get_persisted("getSchedule")

    def get_event_details(self, match_id: str) -> dict[str, Any]:
        return self._get_persisted("getEventDetails", {"id": match_id})

    def get_window(self, game_id: str, starting_time: str | None = None) -> dict[str, Any]:
        import requests

        url = f"https://feed.lolesports.com/livestats/v1/window/{game_id}"
        params = {"startingTime": starting_time} if starting_time else None
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def _get_persisted(self, endpoint: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        import requests

        url = f"https://esports-api.lolesports.com/persisted/gw/{endpoint}"
        request_params = {"hl": self.language}
        if params:
            request_params.update(params)
        headers = {"x-api-key": self.api_key} if self.api_key else None
        response = requests.get(url, params=request_params, headers=headers, timeout=20)
        response.raise_for_status()
        return response.json()


def parse_event_details(payload: dict[str, Any]) -> tuple[Match, list[Game]]:
    event = payload["event"]
    match_payload = event["match"]
    teams = match_payload["teams"]
    league = event.get("league") or {}

    match = Match(
        match_id=str(event["id"]),
        league=league.get("name") or league.get("slug"),
        team_a_id=str(teams[0]["id"]),
        team_a_name=teams[0]["name"],
        team_b_id=str(teams[1]["id"]),
        team_b_name=teams[1]["name"],
        state=event.get("state"),
        raw=event,
    )

    games: list[Game] = []
    for game_payload in match_payload.get("games", []):
        side_by_name = {team["side"]: str(team["id"]) for team in game_payload.get("teams", [])}
        games.append(
            Game(
                game_id=str(game_payload["id"]),
                match_id=match.match_id,
                game_number=int(game_payload["number"]),
                blue_team_id=side_by_name["blue"],
                red_team_id=side_by_name["red"],
                state=game_payload.get("state", "unknown"),
                raw=game_payload,
            )
        )

    return match, games


def parse_window(payload: dict[str, Any]) -> tuple[list[DraftSnapshot], GameStateSnapshot]:
    game_id = str(payload["esportsGameId"])
    match_id = str(payload["esportsMatchId"])
    patch = payload.get("patchVersion") or payload.get("gameMetadata", {}).get("patchVersion")
    metadata = payload["gameMetadata"]

    drafts: list[DraftSnapshot] = []
    for side, team_key in (("blue", "blueTeamMetadata"), ("red", "redTeamMetadata")):
        team = metadata[team_key]
        for participant in team.get("participantMetadata", []):
            drafts.append(
                DraftSnapshot(
                    game_id=game_id,
                    match_id=match_id,
                    patch=patch,
                    team_id=str(team["esportsTeamId"]),
                    side=side,
                    participant_id=int(participant["participantId"]),
                    champion_id=participant["championId"],
                    role=participant["role"],
                    summoner_name=participant["summonerName"],
                    raw=participant,
                )
            )

    frame = payload.get("sampleFrame")
    if frame is None:
        frames = payload.get("frames", [])
        if not frames:
            raise ValueError("window payload has no sampleFrame or frames")
        frame = frames[-1]
    blue = frame["blueTeam"]
    red = frame["redTeam"]
    snapshot = GameStateSnapshot(
        game_id=game_id,
        timestamp=frame["rfc460Timestamp"],
        game_state=frame["gameState"],
        blue_gold=int(blue["totalGold"]),
        red_gold=int(red["totalGold"]),
        blue_towers=int(blue["towers"]),
        red_towers=int(red["towers"]),
        blue_dragons=list(blue.get("dragons", [])),
        red_dragons=list(red.get("dragons", [])),
        blue_barons=int(blue.get("barons", 0)),
        red_barons=int(red.get("barons", 0)),
        blue_kills=int(blue["totalKills"]),
        red_kills=int(red["totalKills"]),
        raw=frame,
    )

    return drafts, snapshot
