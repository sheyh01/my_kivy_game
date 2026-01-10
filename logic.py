# logic.py
import random
from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

Pos = Tuple[int, int]  # (x, y)


def in_bounds(x: int, y: int, w: int, h: int) -> bool:
    return 0 <= x < w and 0 <= y < h


def neighbors4(p: Pos) -> List[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def bfs_prev_map(walls: List[List[str]], start: Pos) -> Dict[Pos, Optional[Pos]]:
    """BFS по проходимым клеткам. Карта prev для восстановления пути."""
    h = len(walls)
    w = len(walls[0]) if h else 0

    q: Deque[Pos] = deque([start])
    prev: Dict[Pos, Optional[Pos]] = {start: None}

    while q:
        cur = q.popleft()
        x, y = cur
        for nx, ny in neighbors4(cur):
            if not in_bounds(nx, ny, w, h):
                continue
            if walls[ny][nx] == "#":
                continue
            nxt = (nx, ny)
            if nxt in prev:
                continue
            prev[nxt] = cur
            q.append(nxt)

    return prev


def bfs_distances(walls: List[List[str]], start: Pos) -> Dict[Pos, int]:
    """{клетка: расстояние по шагам от start} по проходимым клеткам."""
    h = len(walls)
    w = len(walls[0]) if h else 0

    q: Deque[Pos] = deque([start])
    dist: Dict[Pos, int] = {start: 0}

    while q:
        x, y = q.popleft()
        d = dist[(x, y)]
        for nx, ny in neighbors4((x, y)):
            if not in_bounds(nx, ny, w, h):
                continue
            if walls[ny][nx] == "#":
                continue
            p = (nx, ny)
            if p in dist:
                continue
            dist[p] = d + 1
            q.append(p)

    return dist


def bfs_next_step(walls: List[List[str]], start: Pos, goal: Pos) -> Optional[Pos]:
    """Следующий шаг из start к goal по кратчайшему пути. None, если пути нет."""
    if start == goal:
        return start
    prev = bfs_prev_map(walls, start)
    if goal not in prev:
        return None
    cur = goal
    while prev[cur] != start:
        cur = prev[cur]  # type: ignore[assignment]
        if cur is None:
            return None
    return cur


@dataclass
class LevelConfig:
    w: int
    h: int
    wall_prob: float
    treasures: int
    enemies: int
    medkits: int
    enemy_steps: int


def level_config(level: int) -> LevelConfig:
    w = min(32, 20 + (level - 1) * 4)
    h = min(18, 12 + (level - 1) * 2)
    wall_prob = min(0.28, 0.20 + (level - 1) * 0.02)

    treasures = min(8, 3 + (level - 1))
    enemies = min(6, 1 + (level - 1))
    medkits = 1 + (level // 2)
    enemy_steps = 1 if level < 4 else 2

    return LevelConfig(w, h, wall_prob, treasures, enemies, medkits, enemy_steps)


def pick_random(reachable: List[Pos], forbidden: Set[Pos]) -> Pos:
    choices = [p for p in reachable if p not in forbidden]
    if not choices:
        raise RuntimeError("Нет доступных клеток для размещения объекта.")
    return random.choice(choices)


def generate_level(cfg: LevelConfig) -> Tuple[
    List[List[str]], Pos, Pos, Set[Pos], Set[Pos], List[Pos]
]:
    """Генерация уровня: гарантируем путь до выхода и безопасную дистанцию до врагов."""
    start = (1, 1)
    goal = (cfg.w - 2, cfg.h - 2)

    attempts = 0
    while True:
        attempts += 1
        if attempts > 300:
            raise RuntimeError("Не удалось сгенерировать уровень. Попробуй уменьшить wall_prob.")

        walls = [["." for _ in range(cfg.w)] for _ in range(cfg.h)]

        # рамка
        for x in range(cfg.w):
            walls[0][x] = "#"
            walls[cfg.h - 1][x] = "#"
        for y in range(cfg.h):
            walls[y][0] = "#"
            walls[y][cfg.w - 1] = "#"

        # случайные стены
        for y in range(1, cfg.h - 1):
            for x in range(1, cfg.w - 1):
                if random.random() < cfg.wall_prob:
                    walls[y][x] = "#"

        walls[start[1]][start[0]] = "."
        walls[goal[1]][goal[0]] = "."

        dist = bfs_distances(walls, start)
        if goal not in dist:
            continue

        reachable = list(dist.keys())
        need = cfg.treasures + cfg.medkits + cfg.enemies + 2
        if len(reachable) < need:
            continue

        forbidden: Set[Pos] = {start, goal}

        # сокровища
        treasures: Set[Pos] = set()
        for _ in range(cfg.treasures):
            t = pick_random(reachable, forbidden)
            treasures.add(t)
            forbidden.add(t)

        # аптечки
        medkits: Set[Pos] = set()
        for _ in range(cfg.medkits):
            m = pick_random(reachable, forbidden)
            medkits.add(m)
            forbidden.add(m)

        # враги — далеко от старта
        enemies: List[Pos] = []
        primary_min = max(6, (cfg.w + cfg.h) // 4)
        secondary_min = 3

        for _ in range(cfg.enemies):
            far = [p for p in reachable
                   if p not in forbidden and dist.get(p, 0) >= primary_min]
            if not far:
                far = [p for p in reachable
                       if p not in forbidden and dist.get(p, 0) >= secondary_min]
            if not far:
                enemies = []
                break
            e = random.choice(far)
            enemies.append(e)
            forbidden.add(e)

        if len(enemies) < cfg.enemies:
            continue

        return walls, start, goal, treasures, medkits, enemies


def try_move(walls: List[List[str]], pos: Pos, dx: int, dy: int) -> Pos:
    x, y = pos
    nx, ny = x + dx, y + dy
    h = len(walls)
    w = len(walls[0]) if h else 0
    if not in_bounds(nx, ny, w, h):
        return pos
    if walls[ny][nx] == "#":
        return pos
    return (nx, ny)


def enemy_turn(walls: List[List[str]], enemies: List[Pos], player: Pos, steps: int) -> List[Pos]:
    new_positions: List[Pos] = []
    occupied = set(enemies)

    for e in enemies:
        occupied.discard(e)
        cur = e
        for _ in range(steps):
            step = bfs_next_step(walls, cur, player)
            if step is None:
                opts = []
                h = len(walls)
                w = len(walls[0]) if h else 0
                for nx, ny in neighbors4(cur):
                    if in_bounds(nx, ny, w, h) and walls[ny][nx] != "#":
                        opts.append((nx, ny))
                step = random.choice(opts) if opts else cur
            if step in occupied:
                break
            cur = step
            if cur == player:
                break
        new_positions.append(cur)
        occupied.add(cur)

    return new_positions