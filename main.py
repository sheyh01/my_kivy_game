import math
import random
from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Ellipse, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget

Pos = Tuple[int, int]  # (x, y)


# ---------------------------
# Логика уровня
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

COL_BG = (0.03, 0.04, 0.08)
COL_FLOOR = (0.12, 0.13, 0.22)
COL_WALL = (0.08, 0.09, 0.14)

COL_PLAYER = (0.35, 0.80, 1.0)      # искатель сокровищ (куртка/шляпа)
COL_ENEMY = (0.95, 0.95, 0.98)      # кости скелета
COL_TREASURE = (1.00, 0.87, 0.32)   # золото
COL_MEDKIT = (0.32, 0.93, 0.58)     # зелёный
COL_GOAL = (0.80, 0.50, 1.00)       # фиолетовый портал
COL_GRID = (1.0, 1.0, 1.0, 0.06)    # линии сетки


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
        self.anim_time = 0.0
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw())

        Window.bind(on_key_down=self._on_key_down)

    def _on_key_down(self, _window, key, _scancode, _codepoint, _modifiers):
        # dy=+1 — ВВЕРХ на экране, dy=-1 — ВНИЗ
        if key in (273,):      # стрелка вверх
            self.step(0, 1)
        elif key in (274,):    # стрелка вниз
            self.step(0, -1)
        elif key in (276,):    # влево
            self.step(-1, 0)
        elif key in (275,):    # вправо
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

    def animate(self, dt: float) -> None:
        self.anim_time += dt
        self.redraw()

    def redraw(self) -> None:
        st = self.state
        if not st.walls or not st.cfg:
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
            # фон
            Color(*COL_BG)
            Rectangle(pos=(self.x, self.y), size=(self.width, self.height))

            # подсветка поля
            Color(0.10, 0.12, 0.22, 1)
            Rectangle(pos=(ox - 8, oy - 8), size=(grid_w + 16, grid_h + 16))

            # клетки
            for yy in range(h):
                row_factor = 0.8 + 0.25 * (yy / max(1, h - 1))
                for xx in range(w):
                    cell = st.walls[yy][xx]
                    if cell == "#":
                        Color(*(COL_WALL[0] * row_factor,
                                COL_WALL[1] * row_factor,
                                COL_WALL[2] * row_factor, 1))
                    else:
                        Color(*(COL_FLOOR[0] * row_factor,
                                COL_FLOOR[1] * row_factor,
                                COL_FLOOR[2] * row_factor, 1))
                    Rectangle(pos=(ox + xx * tile, oy + yy * tile), size=(tile, tile))

            # сетка
            Color(*COL_GRID)
            for xx in range(w + 1):
                x = ox + xx * tile
                Line(points=[x, oy, x, oy + grid_h], width=1)
            for yy in range(h + 1):
                y = oy + yy * tile
                Line(points=[ox, y, ox + grid_w, y], width=1)

            # вспомогательные функции отрисовки
            def draw_pulse_dot(p: Pos, color, base_inset: float, speed: float):
                x, y = p
                phase = self.anim_time * speed + (x + y) * 0.4
                inset = base_inset + 0.03 * math.sin(phase)
                cx = ox + x * tile
                cy = oy + y * tile
                d = tile * (1.0 - 2 * inset)
                Color(*color)
                Ellipse(pos=(cx + tile * inset, cy + tile * inset), size=(d, d))

            def draw_hunter(p: Pos):
                # искатель сокровищ
                x, y = p
                cell_x = ox + x * tile
                cell_y = oy + y * tile
                cx = cell_x + tile * 0.5
                cy_base = cell_y + tile * 0.45
                bob = math.sin(self.anim_time * 5.0 + (x + y) * 0.5) * tile * 0.06
                cy = cy_base + bob

                body_w = tile * 0.5
                body_h = tile * 0.4
                head_r = tile * 0.18
                leg_w = tile * 0.16
                leg_h = tile * 0.22
                leg_gap = tile * 0.04

                # ноги
                Color(0.18, 0.40, 0.90, 1)  # синие штаны
                Rectangle(pos=(cx - leg_gap / 2 - leg_w, cy - body_h * 0.8 - leg_h),
                          size=(leg_w, leg_h))
                Rectangle(pos=(cx + leg_gap / 2, cy - body_h * 0.8 - leg_h),
                          size=(leg_w, leg_h))

                # ботинки
                Color(0.05, 0.05, 0.08, 1)
                boot_h = leg_h * 0.35
                Rectangle(pos=(cx - leg_gap / 2 - leg_w, cy - body_h * 0.8 - leg_h),
                          size=(leg_w, boot_h))
                Rectangle(pos=(cx + leg_gap / 2, cy - body_h * 0.8 - leg_h),
                          size=(leg_w, boot_h))

                # туловище (коричневая куртка)
                Color(0.55, 0.35, 0.18, 1)
                Rectangle(pos=(cx - body_w / 2, cy - body_h / 2),
                          size=(body_w, body_h))

                # ремень
                Color(0.10, 0.10, 0.12, 1)
                belt_h = body_h * 0.18
                Rectangle(pos=(cx - body_w / 2, cy - belt_h / 2),
                          size=(body_w, belt_h))

                # пряжка ремня
                Color(0.9, 0.8, 0.3, 1)
                buckle_w = belt_h * 0.7
                Rectangle(pos=(cx - buckle_w / 2, cy - belt_h / 2 + belt_h * 0.1),
                          size=(buckle_w, belt_h * 0.8))

                # голова
                Color(0.96, 0.84, 0.65, 1)
                Ellipse(pos=(cx - head_r, cy + body_h * 0.35),
                        size=(2 * head_r, 2 * head_r))

                # шляпа
                Color(0.30, 0.18, 0.08, 1)
                brim_w = head_r * 3.0
                brim_h = head_r * 0.55
                Rectangle(pos=(cx - brim_w / 2, cy + body_h * 0.35 + head_r * 0.8),
                          size=(brim_w, brim_h))

                Color(0.25, 0.15, 0.07, 1)
                hat_w = head_r * 1.7
                hat_h = head_r * 1.6
                Rectangle(pos=(cx - hat_w / 2, cy + body_h * 0.35 + head_r * 0.9),
                          size=(hat_w, hat_h))

            def draw_skeleton(p: Pos):
                # враг-скелет
                x, y = p
                cell_x = ox + x * tile
                cell_y = oy + y * tile
                cx = cell_x + tile * 0.5
                cy_base = cell_y + tile * 0.50
                bob = math.sin(self.anim_time * 4.5 + (x + y) * 0.7) * tile * 0.05
                cy = cy_base + bob

                skull_r = tile * 0.20
                jaw_h = tile * 0.10
                body_h = tile * 0.35
                body_w = tile * 0.30
                leg_h = tile * 0.22
                leg_w = tile * 0.10
                leg_gap = tile * 0.05

                # ноги (кости)
                Color(*COL_ENEMY)
                Rectangle(pos=(cx - leg_gap / 2 - leg_w, cy - body_h * 0.7 - leg_h),
                          size=(leg_w, leg_h))
                Rectangle(pos=(cx + leg_gap / 2, cy - body_h * 0.7 - leg_h),
                          size=(leg_w, leg_h))

                # стопы
                Color(0.85, 0.85, 0.9, 1)
                foot_h = leg_h * 0.35
                Rectangle(pos=(cx - leg_gap / 2 - leg_w, cy - body_h * 0.7 - leg_h),
                          size=(leg_w, foot_h))
                Rectangle(pos=(cx + leg_gap / 2, cy - body_h * 0.7 - leg_h),
                          size=(leg_w, foot_h))

                # позвоночник
                Color(*COL_ENEMY)
                spine_w = tile * 0.09
                Rectangle(pos=(cx - spine_w / 2, cy - body_h / 2),
                          size=(spine_w, body_h))

                # рёбра
                rib_count = 3
                rib_len = body_w
                for i in range(rib_count):
                    t = (i + 1) / (rib_count + 1)
                    ry = cy - body_h / 2 + body_h * t
                    Color(*COL_ENEMY)
                    Line(points=[cx - rib_len / 2, ry, cx + rib_len / 2, ry], width=1.3)

                # череп
                Color(*COL_ENEMY)
                Ellipse(pos=(cx - skull_r, cy + body_h * 0.4),
                        size=(2 * skull_r, 2 * skull_r))

                # нижняя челюсть
                jaw_w = skull_r * 1.5
                Color(*COL_ENEMY)
                Rectangle(pos=(cx - jaw_w / 2, cy + body_h * 0.4 - jaw_h * 0.2),
                          size=(jaw_w, jaw_h))

                # глаза
                eye_r = skull_r * 0.35
                eye_dx = skull_r * 0.55
                Color(0.08, 0.08, 0.12, 1)
                Ellipse(pos=(cx - eye_dx - eye_r, cy + body_h * 0.4 + skull_r * 0.2),
                        size=(2 * eye_r, 2 * eye_r))
                Ellipse(pos=(cx + eye_dx - eye_r, cy + body_h * 0.4 + skull_r * 0.2),
                        size=(2 * eye_r, 2 * eye_r))

                # маленький “нос”
                nose_w = skull_r * 0.35
                nose_h = skull_r * 0.25
                Rectangle(pos=(cx - nose_w / 2, cy + body_h * 0.4 + skull_r * 0.05),
                          size=(nose_w, nose_h))

            # сокровища, аптечки, выход
            for t in st.treasures:
                draw_pulse_dot(t, COL_TREASURE, 0.26, speed=3.0)

            for m in st.medkits:
                draw_pulse_dot(m, COL_MEDKIT, 0.28, speed=2.0)

            draw_pulse_dot(st.goal, COL_GOAL, 0.24, speed=2.5)

            # враги-скелеты
            for e in st.enemies:
                draw_skeleton(e)

            # игрок-искатель
            draw_hunter(st.player)


class MyGameApp(App):
    def build(self):
        random.seed()

        self.st = GameState()
        self.st.load_level()

        root = BoxLayout(orientation="vertical", spacing=6, padding=6)

        self.hud = Label(
            text="",
            size_hint_y=None,
            height=56,
            halign="left",
            valign="middle",
        )
        self.hud.bind(size=lambda *_: setattr(self.hud, "text_size", self.hud.size))

        self.game = GameWidget(self.st)

        controls = BoxLayout(size_hint_y=None, height=120, spacing=6)

        left = Button(text="<")
        right = Button(text=">")
        up = Button(text="^")
        down = Button(text="v")

        next_btn = Button(text="Next")
        restart_btn = Button(text="Restart")

        left.bind(on_release=lambda *_: self.game.step(-1, 0))
        right.bind(on_release=lambda *_: self.game.step(1, 0))
        # "^" — ВВЕРХ
        up.bind(on_release=lambda *_: self.game.step(0, 1))
        # "v" — ВНИЗ
        down.bind(on_release=lambda *_: self.game.step(0, -1))

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
        Clock.schedule_interval(self.game.animate, 1 / 30.0)

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