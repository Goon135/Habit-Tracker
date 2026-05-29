"""Тесты A/B-разделения. КРИТИЧНО для исследовательской части диплома:
если разделение нестабильное — все статистические выводы летят."""
from collections import Counter

from src.domain.value_objects.coaching_mode import CoachingMode


def test_assignment_is_deterministic():
    """Один и тот же user_id → один и тот же режим всегда."""
    user_id = 123456789
    assignments = {CoachingMode.assign(user_id) for _ in range(100)}
    assert len(assignments) == 1


def test_assignment_distribution_is_roughly_balanced():
    """На 1000 синтетических user_id обе группы получают ~50%.

    Используем chi-square-устойчивый интервал: при 50/50 ожидании и n=1000
    отклонение в 100 (т.е. 40/60) случается крайне редко при случайном бросании.
    """
    counter = Counter(CoachingMode.assign(uid).value for uid in range(1, 1001))
    llm_count = counter[CoachingMode.LLM.value]
    template_count = counter[CoachingMode.TEMPLATE.value]
    assert llm_count + template_count == 1000
    assert 400 <= llm_count <= 600
    assert 400 <= template_count <= 600


def test_salt_changes_assignment():
    """Меняя salt — можем ре-рандомизировать эксперимент."""
    user_id = 42
    v1 = CoachingMode.assign(user_id, salt="v1")
    v1_again = CoachingMode.assign(user_id, salt="v1")
    assert v1 == v1_again
    # Не утверждаем, что v1 != v_new для одного конкретного юзера — это вероятностно,
    # но на 1000 юзерах группы должны заметно разойтись.
    moved = sum(
        1 for uid in range(1, 1001)
        if CoachingMode.assign(uid, salt="v1") != CoachingMode.assign(uid, salt="v2")
    )
    # Ожидание для случайного перераспределения двух 50/50 групп — около 500 «перемещений».
    assert 350 <= moved <= 650
