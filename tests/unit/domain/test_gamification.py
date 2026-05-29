"""Domain services: очки и достижения."""
import pytest

from src.domain.services.achievements_catalog import (
    find_unlocked_count_achievements,
    find_unlocked_streak_achievements,
)
from src.domain.services.gamification import (
    calculate_points_for_completion,
    get_level_title,
)


class TestGamification:
    def test_base_points_no_streak(self):
        assert calculate_points_for_completion(0) == 10

    def test_weekly_bonus(self):
        # 7 дней = 1 полная неделя = +2 бонусных очка.
        assert calculate_points_for_completion(7) == 12
        assert calculate_points_for_completion(8) == 12
        assert calculate_points_for_completion(14) == 14
        assert calculate_points_for_completion(100) == 10 + (100 // 7) * 2

    def test_negative_streak_rejected(self):
        with pytest.raises(ValueError):
            calculate_points_for_completion(-1)

    def test_level_titles(self):
        assert get_level_title(1) == "Новичок"
        assert get_level_title(2) == "Стажёр"
        assert get_level_title(10) == "Гуру"
        assert get_level_title(99) == "Просветлённый"


class TestAchievements:
    def test_streak_3_unlocked(self):
        unlocked = find_unlocked_streak_achievements(3, set())
        codes = {a.code for a in unlocked}
        assert "streak_3" in codes
        assert "streak_7" not in codes

    def test_streak_30_unlocks_all_below(self):
        unlocked = find_unlocked_streak_achievements(30, set())
        codes = {a.code for a in unlocked}
        assert {"streak_3", "streak_7", "streak_21", "streak_30"} <= codes

    def test_already_earned_filtered(self):
        unlocked = find_unlocked_streak_achievements(7, already_earned_codes={"streak_3"})
        codes = {a.code for a in unlocked}
        assert "streak_3" not in codes
        assert "streak_7" in codes

    def test_habit_count_thresholds(self):
        assert {a.code for a in find_unlocked_count_achievements(1, set())} == {"habits_1"}
        assert {a.code for a in find_unlocked_count_achievements(5, set())} == {
            "habits_1", "habits_3", "habits_5"
        }
