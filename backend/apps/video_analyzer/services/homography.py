COURT_LENGTH = 40  # meters
COURT_WIDTH = 20
COURT_CORNERS = [[0, 0], [COURT_LENGTH, 0], [COURT_LENGTH, COURT_WIDTH], [0, COURT_WIDTH]]


def make_matrix(corners):
    """Builds the pixel-to-court matrix from the 4 clicked corners."""
    import cv2
    import numpy as np

    return cv2.getPerspectiveTransform(np.float32(corners), np.float32(COURT_CORNERS))


def to_court(matrix, point):
    """Converts a pixel (x, y) to court meters (x, y)."""
    import cv2
    import numpy as np

    x, y = cv2.perspectiveTransform(np.float32([[point]]), matrix)[0][0]
    return (float(x), float(y))
