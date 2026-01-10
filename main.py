import random
from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Ellipse
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget

Pos = Tuple[int, int]  # (x, y)


# ---------------------------
# Логика уровня (как в pygame)
# ---------------------------

def in_bounds(x: int, y: int, w: int, h: int) -> bool:
    return 0 <= x < w and 0 <= y < h


def neighbors4(p: Pos) -> List[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def bfs_prev_map(walls: List[List[str]], start: Pos) -> Dict[Pos, Optional[Pos]]:
    h = len(walls)
    w = len(walls[0]) if h else 0

    q: Deque[Pos] = deque([start])
    prev: Dict[Pos, Optional[Pos]] = {start: None}

    while q:
        cur = q.popleft()
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


def bfs_next_step(walls: List[List[str]], start: Pos, goal: Pos) -> Optional[Pos]:
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


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


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


def generate_level(cfg: LevelConfig) -> Tuple[List[List[str]], Pos, Pos, Set[Pos], Set[Pos], List[Pos]]:
    start = (1, 1)
    goal = (cfg.w - 2, cfg.h - 2)

    attempts = 0
    while True:
        attempts += 1
        if attempts > 300:
            raise RuntimeError("Не удалось сгенерировать уровень. Попробуй уменьшить wall_prob.")

        walls = [["." for _ in range(cfg.w)] for _ in range(cfg.h)]

        for x in range(cfg.w):
            walls[0][x] = "#"
            walls[cfg.h - 1][x] = "#"
        for y in range(cfg.h):
            walls[y][0] = "#"
            walls[y][cfg.w - 1] = "#"

        for y in range(1, cfg.h - 1):
            for x in range(1, cfg.w - 1):
                if random.random() < cfg.wall_prob:
                    walls[y][x] = "#"

        walls[start[1]][start[0]] = "."
        walls[goal[1]][goal[0]] = "."

        prev = bfs_prev_map(walls, start)
        if goal not in prev:
            continue

        reachable = list(prev.keys())
        need = cfg.treasures + cfg.medkits + cfg.enemies + 2
        if len(reachable) < need:
            continue

        forbidden: Set[Pos] = {start, goal}

        treasures: Set[Pos] = set()
        for _ in range(cfg.treasures):
            t = pick_random(reachable, forbidden)
            treasures.add(t)
            forbidden.add(t)

        medkits: Set[Pos] = set()
        for _ in range(cfg.medkits):
            m = pick_random(reachable, forbidden)
            medkits.add(m)
            forbidden.add(m)

        enemies: List[Pos] = []
        for _ in range(cfg.enemies):
            far = [p for p in reachable if p not in forbidden and manhattan(p, start) >= 6]
            if not far:
                far = [p for p in reachable if p not in forbidden]
            e = random.choice(far)
            enemies.append(e)
            forbidden.add(e)

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
                for nx, ny in neighbors4(cur):
                    if in_bounds(nx, ny, len(walls[0]), len(walls)) and walls[ny][nx] != "#":
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


# ---------------------------
# Kivy: отрисовка и управление
# ---------------------------

COL_BG = (0.07, 0.07, 0.09)
COL_FLOOR = (0.16, 0.16, 0.19)
COL_WALL = (0.09, 0.09, 0.11)

COL_PLAYER = (0.31, 0.67, 1.0)
COL_ENEMY = (0.92, 0.27, 0.27)
COL_TREASURE = (0.96, 0.78, 0.27)
COL_MEDKIT = (0.35, 0.86, 0.47)
COL_GOAL = (0.70, 0.43, 1.0)


@dataclass
class GameState:
    level: int = 1
    score: int = 0
    lives: int = 3
    max_lives: int = 3

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
        self.walls, self.start, self.goal, self.treasures, self.medkits, self.enemies = generate_level(self.cfg)
        self.player = self.start
        self.message = None

    def restart(self) -> None:
        self.level = 1
        self.score = 0
        self.lives = self.max_lives
        self.load_level()


class GameWidget(Widget):
    def __init__(self, state: GameState, **kwargs):
        super().__init__(**kwargs)
        self.state = state
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw())

        # Чтобы на ПК можно было играть стрелками
        Window.bind(on_key_down=self._on_key_down)

    def _on_key_down(self, _window, key, _scancode, _codepoint, _modifiers):
        if key in (273,):  # up
            self.step(0, -1)
        elif key in (274,):  # down
            self.step(0, 1)
        elif key in (276,):  # left
            self.step(-1, 0)
        elif key in (275,):  # right
            self.step(1, 0)
        return True

    def step(self, dx: int, dy: int) -> None:
        st = self.state
        if st.message:
            return

        st.player = try_move(st.walls, st.player, dx, dy)

        if st.player in st.treasures:
            st.treasures.remove(st.player)
            st.score += 10

        if st.player in st.medkits:
            st.medkits.remove(st.player)
            st.lives = min(st.max_lives, st.lives + 1)
            st.score += 5

        if st.player == st.goal and len(st.treasures) == 0:
            st.score += 50 + st.level * 10
            st.message = "Уровень пройден! (Next)"
            self.redraw()
            return

        st.enemies = enemy_turn(st.walls, st.enemies, st.player, st.cfg.enemy_steps)

        if st.player in set(st.enemies):
            st.lives -= 1
            st.score = max(0, st.score - 15)
            st.player = st.start
            if st.lives <= 0:
                st.message = "Игра окончена (Restart)"

        self.redraw()

    def redraw(self) -> None:
        st = self.state
        if not st.walls:
            return

        self.canvas.clear()

        w = st.cfg.w
        h = st.cfg.h

        pad = 10
        avail_w = max(1.0, self.width - 2 * pad)
        avail_h = max(1.0, self.height - 2 * pad)

        tile = int(min(avail_w / w, avail_h / h))
        tile = max(10, tile)

        grid_w = tile * w
        grid_h = tile * h

        ox = self.x + (self.width - grid_w) / 2
        oy = self.y + (self.height - grid_h) / 2

        with self.canvas:
            Color(*COL_BG)
            Rectangle(pos=(self.x, self.y), size=(self.width, self.height))

            for yy in range(h):
                for xx in range(w):
                    cell = st.walls[yy][xx]
                    Color(*(COL_WALL if cell == "#" else COL_FLOOR))
                    Rectangle(pos=(ox + xx * tile, oy + yy * tile), size=(tile, tile))

            def draw_dot(p: Pos, color, inset: float):
                x, y = p
                Color(*color)
                d = tile * (1.0 - 2 * inset)
                Ellipse(pos=(ox + x * tile + tile * inset, oy + y * tile + tile * inset), size=(d, d))

            for t in st.treasures:
                draw_dot(t, COL_TREASURE, 0.28)

            for m in st.medkits:
                draw_dot(m, COL_MEDKIT, 0.28)

            draw_dot(st.goal, COL_GOAL, 0.28)

            for e in st.enemies:
                draw_dot(e, COL_ENEMY, 0.20)

            draw_dot(st.player, COL_PLAYER, 0.16)


class MyGameApp(App):
    def build(self):
        random.seed()

        self.st = GameState()
        self.st.load_level()

        root = BoxLayout(orientation="vertical", spacing=6, padding=6)

        self.hud = Label(
            text="",
            size_hint_y=None,
            height=48,
            halign="left",
            valign="middle",
        )
        self.hud.bind(size=lambda *_: setattr(self.hud, "text_size", self.hud.size))

        self.game = GameWidget(self.st)

        controls = BoxLayout(size_hint_y=None, height=120, spacing=6)

        left = Button(text="◀")
        right = Button(text="▶")
        up = Button(text="▲")
        down = Button(text="▼")

        next_btn = Button(text="Next")
        restart_btn = Button(text="Restart")

        left.bind(on_release=lambda *_: self.game.step(-1, 0))
        right.bind(on_release=lambda *_: self.game.step(1, 0))
        up.bind(on_release=lambda *_: self.game.step(0, -1))
        down.bind(on_release=lambda *_: self.game.step(0, 1))

        def on_next(_btn):
            if self.st.message and self.st.lives > 0:
                self.st.level += 1
                self.st.load_level()
                self.game.redraw()

        def on_restart(_btn):
            self.st.restart()
            self.game.redraw()

        next_btn.bind(on_release=on_next)
        restart_btn.bind(on_release=on_restart)

        col1 = BoxLayout(orientation="vertical", spacing=6)
        col1.add_widget(up)
        mid = BoxLayout(spacing=6)
        mid.add_widget(left)
        mid.add_widget(down)
        mid.add_widget(right)
        col1.add_widget(mid)

        controls.add_widget(col1)
        controls.add_widget(next_btn)
        controls.add_widget(restart_btn)

        root.add_widget(self.hud)
        root.add_widget(self.game)
        root.add_widget(controls)

        Clock.schedule_interval(self._update_hud, 0.1)
        self.game.redraw()
        return root

    def _update_hud(self, _dt):
        left = len(self.st.treasures) if self.st.treasures is not None else 0
        msg = self.st.message or ""
        self.hud.text = (
            f"Уровень: {self.st.level}   Жизни: {self.st.lives}/{self.st.max_lives}   "
            f"Очки: {self.st.score}   Осталось T: {left}   {msg}"
        )


if __name__ == "__main__":
    MyGameApp().run()