from models import CriterionResult


def calculate_total_score(criteria_scores: list) -> int:
    scores = [c.score for c in criteria_scores]

    if 1 in scores:
        return 0

    count_3 = scores.count(3)

    if count_3 >= 2:
        return 0

    if count_3 == 1:
        return 30

    return 100


def get_score_label(score: int) -> str:
    if score == 0:
        return "Критично"
    elif score == 30:
        return "Удовлетворительно"
    elif score == 100:
        return "Отлично"
    return str(score)


def get_score_color(score: int) -> str:
    if score == 0:
        return "#e74c3c"
    elif score == 30:
        return "#f39c12"
    elif score == 100:
        return "#27ae60"
    return "#95a5a6"


def get_criterion_color(score: int) -> str:
    if score == 1:
        return "#e74c3c"
    elif score == 3:
        return "#f39c12"
    elif score == 5:
        return "#27ae60"
    return "#95a5a6"
