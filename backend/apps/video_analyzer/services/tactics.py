OPEN_DISTANCE = 3  # meters to the nearest opponent


def distance(a, b):
    """Distance in meters between two (x, y) points."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def is_open(player, players):
    """True if no opponent is within OPEN_DISTANCE meters of the player."""
    for other in players:
        if other["team"] != player["team"] and distance(player["pos"], other["pos"]) <= OPEN_DISTANCE:
            return False
    return True


def open_players(players):
    """Returns the players with no opponent close to them."""
    result = []
    for player in players:
        if is_open(player, players):
            result.append(player)
    return result


def closest_to_ball(players, ball):
    """Returns the player closest to the ball."""
    closest = players[0]
    for player in players:
        if distance(player["pos"], ball) < distance(closest["pos"], ball):
            closest = player
    return closest


def suggest(players, ball):
    """Suggests passes from the player with the ball to open teammates."""
    if len(players) == 0 or ball is None:
        return []

    carrier = closest_to_ball(players, ball)
    suggestions = []
    for player in open_players(players):
        if player["team"] == carrier["team"] and player["id"] != carrier["id"]:
            suggestions.append({"text": f"#{carrier['id']} could pass to #{player['id']}, who is open."})
    return suggestions
