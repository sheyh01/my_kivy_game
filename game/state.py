from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set

from game.logic import Pos, LevelConfig, level_config, generate_level


@dataclass
class Biome:
    name: str
    bg: tuple
    floor: tuple
    wall: tuple
    goal: tuple


def get_biome_for_level(level: int) -> Biome:
    idx = (level - 1) // 5

    if idx == 0:
        return Biome("Гробница",
                     bg=(0.03, 0.04, 0.08),
                     floor=(0.12, 0.13, 0.22),
                     wall=(0.08, 0.09, 0.14),
                     goal=(0.80, 0.50, 1.00))
    elif idx == 1:
        return Biome("Ледяные пещеры",
                     bg=(0.02, 0.06, 0.10),
                     floor=(0.10, 0.18, 0.28),
                     wall=(0.06, 0.12, 0.20),
                     goal=(0.55, 0.80, 1.00))
    elif idx == 2:
        return Biome("Лавовые глубины",
                     bg=(0.06, 0.02, 0.05),
                     floor=(0.20, 0.08, 0.08),
                     wall=(0.25, 0.10, 0.05),
                     goal=(1.00, 0.60, 0.20))
    else:
        return Biome("Руины джунглей",
                     bg=(0.02, 0.06, 0.03),
                     floor=(0.10, 0.18, 0.10),
                     wall=(0.07, 0.13, 0.07),
                     goal=(0.60, 0.90, 0.50))


@dataclass
class GameState:
    level: int = 1
    score: int = 0
    lives: int = 3
    max_lives: int = 3
    bombs: int = 0

    cfg: LevelConfig = None  # type: ignore[assignment]
    walls: List[List[str]] = None  # type: ignore[assignment]
    start: Pos = (1, 1)
    goal: Pos = (1, 1)
    player: Pos = (1, 1)
    treasures: Set[Pos] = None  # type: ignore[assignment]
    medkits: Set[Pos] = None  # type: ignore[assignment]
    enemies: List[Pos] = None  # type: ignore[assignment]

    message: Optional[str] = None

    def load_level(self) -> None:
        self.cfg = level_config(self.level)
        (self.walls,
         self.start,
         self.goal,
         self.treasures,
         self.medkits,
         self.enemies) = generate_level(self.cfg)
        self.player = self.start
        self.message = None

    def restart(self) -> None:
        self.level = 1
        self.score = 0
        self.lives = self.max_lives
        self.bombs = 0
        self.load_level()