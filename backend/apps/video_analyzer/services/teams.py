def jersey_color(frame, box):
    """Returns the average shirt color (blue, green, red) inside a player's box."""
    x1, y1, x2, y2 = [int(v) for v in box]
    height, width = y2 - y1, x2 - x1
    shirt = frame[y1 + height // 5 : y1 + height // 2, x1 + width // 4 : x2 - width // 4]
    if shirt.size == 0:
        return (0.0, 0.0, 0.0)
    return tuple(float(c) for c in shirt.reshape(-1, 3).mean(axis=0))


def split_into_teams(player_colors):
    """Splits {player_id: color} into {player_id: "A" or "B"} by jersey color."""
    colors = list(player_colors.values())
    if len(colors) < 2:
        return {player_id: "A" for player_id in player_colors}

    a, b = max(((c1, c2) for c1 in colors for c2 in colors), key=lambda p: distance(*p))
    for _ in range(5):
        team_a = [c for c in colors if is_team_a(c, a, b)]
        team_b = [c for c in colors if not is_team_a(c, a, b)]
        a = average(team_a) if team_a else a
        b = average(team_b) if team_b else b
    return {player_id: "A" if is_team_a(c, a, b) else "B" for player_id, c in player_colors.items()}


def is_team_a(color, a, b):
    return distance(color, a) <= distance(color, b)


def distance(color1, color2):
    return sum((x - y) ** 2 for x, y in zip(color1, color2)) ** 0.5


def average(colors):
    return tuple(sum(channel) / len(colors) for channel in zip(*colors))
