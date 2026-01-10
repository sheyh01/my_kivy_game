import math
import random
from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.image import Image as CoreImage
from kivy.core.audio import SoundLoader
from kivy.resources import resource_find
from kivy.storage.jsonstore import JsonStore
from kivy.graphics import Color, Rectangle, Ellipse, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.popup import Popup
from kivy.uix.togglebutton import ToggleButton

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
    """BFS по проходимым клеткам. prev-карта для восстановления пути."""
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


def generate_level(cfg: LevelConfig) -> Tuple[List[List[str]], Pos, Pos,
                                              Set[Pos], Set[Pos], List[Pos]]:
    """Генерация уровня: гарантируем путь до выхода и безопасную дистанцию до врагов."""
    start = (1, 1)
    goal = (cfg.w - 2, cfg.h - 2)

    attempts = 0
    while True:
        attempts += 1
        if attempts > 300:
            raise RuntimeError("Не удалось сгенерировать уровень. Попробуй уменьшить wall_prob.")

        walls = [["." for _ in range(cfg.w)] for _ in range(cfg.h)]

        # рамка стен
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

        # расстояния от старта
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
        primary_min = max(6, (cfg.w + cfg.h) // 4)  # основная безопасная дистанция
        secondary_min = 3                            # запасная

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

COL_PLAYER = (0.35, 0.80, 1.0)
COL_ENEMY = (0.95, 0.95, 0.98)
COL_TREASURE = (1.00, 0.87, 0.32)
COL_MEDKIT = (0.32, 0.93, 0.58)
COL_GOAL = (0.80, 0.50, 1.00)
COL_GRID = (1.0, 1.0, 1.0, 0.06)


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


class GameWidget(Widget):
    def __init__(self, state: GameState, **kwargs):
        super().__init__(**kwargs)
        self.state = state
        self.anim_time = 0.0
        self.explosions: List[Tuple[int, int, float]] = []
        self.hit_flashes: List[Tuple[int, int, float]] = []
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw())

        Window.bind(on_key_down=self._on_key_down)

    def _on_key_down(self, _window, key, _scancode, _codepoint, _modifiers):
        from kivy.app import App
        app = App.get_running_app()
        # блокируем ввод, если открыт Game Over
        if getattr(app, "game_over_active", False):
            return True

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
        from kivy.app import App
        app = App.get_running_app()
        st = self.state

        # если есть сообщение (flash_message/уровень пройден) или активен Game Over — не двигаемся
        if st.message:
            return
        if getattr(app, "game_over_active", False):
            return

        st.player = try_move(st.walls, st.player, dx, dy)

        # подбор
        if st.player in st.treasures:
            st.treasures.remove(st.player)
            st.score += 10
            if getattr(app, "sounds_enabled", True) and getattr(app, "snd_pickup", None):
                app.snd_pickup.play()

        if st.player in st.medkits:
            st.medkits.remove(st.player)
            st.lives = min(st.max_lives, st.lives + 1)
            st.score += 5
            if getattr(app, "sounds_enabled", True) and getattr(app, "snd_pickup", None):
                app.snd_pickup.play()

        # победа
        if st.player == st.goal and len(st.treasures) == 0:
            st.score += 50 + st.level * 10
            st.message = "Уровень пройден! (Next)"
            if hasattr(app, "save_progress"):
                app.save_progress()
            self.redraw()
            return

        # ход врагов
        st.enemies = enemy_turn(st.walls, st.enemies, st.player, st.cfg.enemy_steps)

        # столкновение
        if st.player in set(st.enemies):
            hit_pos = st.player
            st.lives -= 1
            st.score = max(0, st.score - 15)
            st.player = st.start

            # вспышка удара
            self.hit_flashes.append((hit_pos[0], hit_pos[1], self.anim_time))

            if getattr(app, "sounds_enabled", True) and getattr(app, "snd_hit", None):
                app.snd_hit.play()

            if st.lives <= 0:
                if hasattr(app, "save_progress"):
                    app.save_progress()
                if not getattr(app, "game_over_active", False) and hasattr(app, "show_game_over_dialog"):
                    app.game_over_active = True
                    app.show_game_over_dialog()
                return

        if hasattr(app, "save_progress"):
            app.save_progress()

        self.redraw()

    def use_bomb(self) -> None:
        from kivy.app import App
        app = App.get_running_app()
        st = self.state

        if getattr(app, "game_over_active", False):
            return

        if st.bombs <= 0:
            app.flash_message("Нет бомб")
            return

        px, py = st.player
        targets: List[Pos] = []
        for nx, ny in neighbors4((px, py)):
            if in_bounds(nx, ny, len(st.walls[0]), len(st.walls)) and st.walls[ny][nx] == "#":
                targets.append((nx, ny))

        if not targets:
            app.flash_message("Рядом нет стены")
            return

        tx, ty = random.choice(targets)
        st.walls[ty][tx] = "."
        st.bombs -= 1
        self.explosions.append((tx, ty, self.anim_time))

        if getattr(app, "sounds_enabled", True) and getattr(app, "snd_explosion", None):
            app.snd_explosion.play()

        if hasattr(app, "save_progress"):
            app.save_progress()

        app.flash_message("Бум!")
        self.redraw()

    def animate(self, dt: float) -> None:
        self.anim_time += dt
        # чистим старые эффекты
        self.explosions = [
            (x, y, t0) for (x, y, t0) in self.explosions
            if self.anim_time - t0 < 0.5
        ]
        self.hit_flashes = [
            (x, y, t0) for (x, y, t0) in self.hit_flashes
            if self.anim_time - t0 < 0.35
        ]
        self.redraw()

    def redraw(self) -> None:
        st = self.state
        if not st.walls or not st.cfg:
            return

        from kivy.app import App
        app = App.get_running_app()
        player_tex = getattr(app, "player_tex", None)
        skeleton_tex = getattr(app, "skeleton_tex", None)
        explosion_frames: List = getattr(app, "explosion_frames", [])

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
            Color(0.03, 0.04, 0.08)
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

            def draw_pulse_dot(p: Pos, color, base_inset: float, speed: float):
                x, y = p
                phase = self.anim_time * speed + (x + y) * 0.4
                inset = base_inset + 0.03 * math.sin(phase)
                cx = ox + x * tile
                cy = oy + y * tile
                d = tile * (1.0 - 2 * inset)
                Color(*color)
                Ellipse(pos=(cx + tile * inset, cy + tile * inset), size=(d, d))

            # фигурка игрока (если нет PNG)
            def draw_hunter_shape(p: Pos):
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

                Color(0.18, 0.40, 0.90, 1)
                Rectangle(pos=(cx - leg_gap / 2 - leg_w, cy - body_h * 0.8 - leg_h),
                          size=(leg_w, leg_h))
                Rectangle(pos=(cx + leg_gap / 2, cy - body_h * 0.8 - leg_h),
                          size=(leg_w, leg_h))

                Color(0.05, 0.05, 0.08, 1)
                boot_h = leg_h * 0.35
                Rectangle(pos=(cx - leg_gap / 2 - leg_w, cy - body_h * 0.8 - leg_h),
                          size=(leg_w, boot_h))
                Rectangle(pos=(cx + leg_gap / 2, cy - body_h * 0.8 - leg_h),
                          size=(leg_w, boot_h))

                Color(0.55, 0.35, 0.18, 1)
                Rectangle(pos=(cx - body_w / 2, cy - body_h / 2),
                          size=(body_w, body_h))

                Color(0.10, 0.10, 0.12, 1)
                belt_h = body_h * 0.18
                Rectangle(pos=(cx - body_w / 2, cy - belt_h / 2),
                          size=(body_w, belt_h))

                Color(0.9, 0.8, 0.3, 1)
                buckle_w = belt_h * 0.7
                Rectangle(pos=(cx - buckle_w / 2, cy - belt_h / 2 + belt_h * 0.1),
                          size=(buckle_w, belt_h * 0.8))

                Color(0.96, 0.84, 0.65, 1)
                Ellipse(pos=(cx - head_r, cy + body_h * 0.35),
                        size=(2 * head_r, 2 * head_r))

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

            # фигурка скелета (если нет PNG)
            def draw_skeleton_shape(p: Pos):
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

                Color(*COL_ENEMY)
                Rectangle(pos=(cx - leg_gap / 2 - leg_w, cy - body_h * 0.7 - leg_h),
                          size=(leg_w, leg_h))
                Rectangle(pos=(cx + leg_gap / 2, cy - body_h * 0.7 - leg_h),
                          size=(leg_w, leg_h))

                Color(0.85, 0.85, 0.9, 1)
                foot_h = leg_h * 0.35
                Rectangle(pos=(cx - leg_gap / 2 - leg_w, cy - body_h * 0.7 - leg_h),
                          size=(leg_w, foot_h))
                Rectangle(pos=(cx + leg_gap / 2, cy - body_h * 0.7 - leg_h),
                          size=(leg_w, foot_h))

                Color(*COL_ENEMY)
                spine_w = tile * 0.09
                Rectangle(pos=(cx - spine_w / 2, cy - body_h / 2),
                          size=(spine_w, body_h))

                rib_count = 3
                rib_len = body_w
                for i in range(rib_count):
                    t = (i + 1) / (rib_count + 1)
                    ry = cy - body_h / 2 + body_h * t
                    Color(*COL_ENEMY)
                    Line(points=[cx - rib_len / 2, ry, cx + rib_len / 2, ry], width=1.3)

                Color(*COL_ENEMY)
                Ellipse(pos=(cx - skull_r, cy + body_h * 0.4),
                        size=(2 * skull_r, 2 * skull_r))

                jaw_w = skull_r * 1.5
                Color(*COL_ENEMY)
                Rectangle(pos=(cx - jaw_w / 2, cy + body_h * 0.4 - jaw_h * 0.2),
                          size=(jaw_w, jaw_h))

                eye_r = skull_r * 0.35
                eye_dx = skull_r * 0.55
                Color(0.08, 0.08, 0.12, 1)
                Ellipse(pos=(cx - eye_dx - eye_r, cy + body_h * 0.4 + skull_r * 0.2),
                        size=(2 * eye_r, 2 * eye_r))
                Ellipse(pos=(cx + eye_dx - eye_r, cy + body_h * 0.4 + skull_r * 0.2),
                        size=(2 * eye_r, 2 * eye_r))

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

            # враги
            for e in st.enemies:
                ex, ey = e
                cell_x = ox + ex * tile
                cell_y = oy + ey * tile
                cx = cell_x + tile * 0.5
                cy = cell_y + tile * 0.5
                bob = math.sin(self.anim_time * 4.5 + (ex + ey) * 0.7) * tile * 0.05

                if skeleton_tex:
                    sz = tile * 0.9
                    Color(1, 1, 1, 1)
                    Rectangle(texture=skeleton_tex,
                              pos=(cx - sz / 2, cy - sz / 2 + bob),
                              size=(sz, sz))
                else:
                    draw_skeleton_shape(e)

            # игрок
            px, py = st.player
            cell_x = ox + px * tile
            cell_y = oy + py * tile
            pcx = cell_x + tile * 0.5
            pcy = cell_y + tile * 0.5
            pbob = math.sin(self.anim_time * 5.0 + (px + py) * 0.5) * tile * 0.06

            if player_tex:
                psz = tile * 0.9
                Color(1, 1, 1, 1)
                Rectangle(texture=player_tex,
                          pos=(pcx - psz / 2, pcy - psz / 2 + pbob),
                          size=(psz, psz))
            else:
                draw_hunter_shape(st.player)

            # взрывы (спрайт или кружки)
            for ex, ey, t0 in self.explosions:
                age = self.anim_time - t0
                if age < 0:
                    continue
                progress = min(1.0, age / 0.5)
                cx = ox + ex * tile + tile * 0.5
                cy = oy + ey * tile + tile * 0.5
                alpha = 1.0 - progress

                if explosion_frames:
                    frame_id = int(progress * (len(explosion_frames) - 1))
                    frame = explosion_frames[frame_id]
                    sz = tile * 1.4
                    Color(1, 1, 1, alpha)
                    Rectangle(texture=frame,
                              pos=(cx - sz / 2, cy - sz / 2),
                              size=(sz, sz))
                else:
                    radius = tile * (0.2 + 0.5 * progress)
                    Color(1.0, 0.5, 0.2, alpha)
                    Ellipse(pos=(cx - radius, cy - radius),
                            size=(2 * radius, 2 * radius))
                    Color(1.0, 0.9, 0.6, alpha)
                    inner = radius * 0.6
                    Ellipse(pos=(cx - inner, cy - inner),
                            size=(2 * inner, 2 * inner))

            # вспышки удара
            for hx, hy, t0 in self.hit_flashes:
                age = self.anim_time - t0
                if age < 0:
                    continue
                progress = min(1.0, age / 0.35)
                radius = tile * (0.3 + 0.4 * progress)
                alpha = 1.0 - progress
                cx = ox + hx * tile + tile * 0.5
                cy = oy + hy * tile + tile * 0.5
                Color(1.0, 0.2, 0.3, alpha)
                Line(circle=(cx, cy, radius), width=2.5)
                Color(1.0, 0.4, 0.4, alpha * 0.4)
                Ellipse(pos=(cx - radius * 0.6, cy - radius * 0.6),
                        size=(radius * 1.2, radius * 1.2))


class MyGameApp(App):
    def build(self):
        random.seed()

        self.st = GameState()
        self.game_over_active = False

        # хранилище прогресса и настроек
        self.store = JsonStore("save.json")

        # настройки по умолчанию
        self.music_enabled = True
        self.sounds_enabled = True

        if self.store.exists("settings"):
            sdata = self.store.get("settings")
            self.music_enabled = bool(sdata.get("music_enabled", True))
            self.sounds_enabled = bool(sdata.get("sounds_enabled", True))

        if self.store.exists("progress"):
            data = self.store.get("progress")
            self.st.score = int(data.get("score", 0))
            self.st.bombs = int(data.get("bombs", 0))
            self.st.level = max(1, int(data.get("level", 1)))

        self.st.load_level()

        # текстуры
        self.player_tex = self._load_texture("assets/player.png")
        self.skeleton_tex = self._load_texture("assets/skeleton.png")
        self.explosion_frames = self._load_explosion_frames("assets/explosion_", 8)

        # звуки
        self.snd_pickup = self._load_sound("assets/snd_pickup.mp3")
        self.snd_hit = self._load_sound("assets/snd_hit.mp3")
        self.snd_explosion = self._load_sound("assets/snd_explosion.wav")

        # фон. музыка (путь поменяй под свой файл)
        self.music_sound = self._load_sound("assets/music.mp3")
        self.set_music_enabled(self.music_enabled)

        self.sm = ScreenManager(transition=FadeTransition())
        self._build_screens()

        Clock.schedule_interval(self._update_hud, 0.1)
        Clock.schedule_interval(self.game.animate, 1 / 30.0)

        return self.sm

    # ---------- загрузка ресурсов ----------

    def _load_texture(self, path: str):
        try:
            real = resource_find(path) or path
            img = CoreImage(real)
            return img.texture
        except Exception:
            return None

    def _load_explosion_frames(self, base: str, count: int) -> List:
        frames: List = []
        for i in range(count):
            tex = self._load_texture(f"{base}{i}.png")
            if tex:
                frames.append(tex)
        return frames

    def _load_sound(self, path: str):
        try:
            real = resource_find(path) or path
            snd = SoundLoader.load(real)
            return snd
        except Exception:
            return None

    # ---------- музыка/звук ----------

    def start_music(self) -> None:
        if not self.music_sound:
            return
        try:
            self.music_sound.loop = True
        except Exception:
            pass
        if self.music_sound.state != "play":
            self.music_sound.play()

    def stop_music(self) -> None:
        if self.music_sound and self.music_sound.state == "play":
            self.music_sound.stop()

    def set_music_enabled(self, enabled: bool) -> None:
        self.music_enabled = enabled
        if enabled:
            self.start_music()
        else:
            self.stop_music()
        self.save_settings()

    def set_sounds_enabled(self, enabled: bool) -> None:
        self.sounds_enabled = enabled
        self.save_settings()

    # ---------- экраны ----------

    def _build_screens(self) -> None:
        # SPLASH
        splash = Screen(name="splash")
        box = BoxLayout(orientation="vertical", padding=40, spacing=20)
        title = Label(text="Искатель сокровищ", font_size="32sp")
        subtitle = Label(text="Загрузка...", font_size="18sp")
        box.add_widget(Label())
        box.add_widget(title)
        box.add_widget(subtitle)
        box.add_widget(Label())
        splash.add_widget(box)
        self.sm.add_widget(splash)

        # MENU
        menu = Screen(name="menu")
        mbox = BoxLayout(orientation="vertical", padding=20, spacing=15)
        mtitle = Label(text="Искатель сокровищ", font_size="30sp",
                       size_hint_y=None, height=60)
        btn_play = Button(text="Играть", size_hint_y=None, height=60)
        btn_settings = Button(text="Настройки", size_hint_y=None, height=50)
        btn_how = Button(text="Как играть", size_hint_y=None, height=50)
        btn_shop = Button(text="Магазин", size_hint_y=None, height=50)
        btn_exit = Button(text="Выход", size_hint_y=None, height=50)

        btn_play.bind(on_release=self.go_game)
        btn_settings.bind(on_release=self.go_settings)
        btn_how.bind(on_release=self.go_howto)
        btn_shop.bind(on_release=self.go_shop)
        btn_exit.bind(on_release=lambda *_: self.stop())

        mbox.add_widget(mtitle)
        mbox.add_widget(btn_play)
        mbox.add_widget(btn_settings)
        mbox.add_widget(btn_how)
        mbox.add_widget(btn_shop)
        mbox.add_widget(btn_exit)
        mbox.add_widget(Label())
        menu.add_widget(mbox)
        self.sm.add_widget(menu)

        # GAME
        game_screen = Screen(name="game")
        game_root, self.hud, self.game = self._create_game_ui()
        game_screen.add_widget(game_root)
        self.sm.add_widget(game_screen)

        # SETTINGS
        settings = Screen(name="settings")
        sbox = BoxLayout(orientation="vertical", padding=20, spacing=10)

        stitle = Label(text="Настройки", font_size="26sp",
                       size_hint_y=None, height=40)

        # переключатель музыки
        music_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=10)
        music_lbl = Label(text="Музыка", size_hint_x=0.5)
        self.music_toggle = ToggleButton(
            text="Вкл" if self.music_enabled else "Выкл",
            state="down" if self.music_enabled else "normal",
            size_hint_x=0.5
        )

        def on_music_toggle(btn):
            enabled = (btn.state == "down")
            btn.text = "Вкл" if enabled else "Выкл"
            self.set_music_enabled(enabled)

        self.music_toggle.bind(on_release=on_music_toggle)
        music_row.add_widget(music_lbl)
        music_row.add_widget(self.music_toggle)

        # переключатель звуков
        sound_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=10)
        sound_lbl = Label(text="Звуки", size_hint_x=0.5)
        self.sounds_toggle = ToggleButton(
            text="Вкл" if self.sounds_enabled else "Выкл",
            state="down" if self.sounds_enabled else "normal",
            size_hint_x=0.5
        )

        def on_sounds_toggle(btn):
            enabled = (btn.state == "down")
            btn.text = "Вкл" if enabled else "Выкл"
            self.set_sounds_enabled(enabled)

        self.sounds_toggle.bind(on_release=on_sounds_toggle)
        sound_row.add_widget(sound_lbl)
        sound_row.add_widget(self.sounds_toggle)

        info_lbl = Label(
            text="Здесь можно выключить музыку и звуки.\n"
                 "Позже можно добавить громкость, вибро и др.",
            halign="center", valign="top",
            size_hint_y=None, height=80
        )
        info_lbl.bind(size=lambda *_: setattr(info_lbl, "text_size", info_lbl.size))

        back1 = Button(text="Назад", size_hint_y=None, height=50)
        back1.bind(on_release=self.go_menu)

        sbox.add_widget(stitle)
        sbox.add_widget(music_row)
        sbox.add_widget(sound_row)
        sbox.add_widget(info_lbl)
        sbox.add_widget(back1)
        sbox.add_widget(Label())
        settings.add_widget(sbox)
        self.sm.add_widget(settings)

        # HOW TO
        how = Screen(name="howto")
        hbox = BoxLayout(orientation="vertical", padding=20, spacing=10)
        htitle = Label(text="Как играть", font_size="26sp",
                       size_hint_y=None, height=40)
        htxt = Label(
            text=("Собирай золотые точки, чтобы получать очки.\n"
                  "Скелеты двигаются к тебе по кратчайшему пути.\n"
                  "Не давай им догнать тебя — потеряешь жизнь.\n"
                  "Собери все сокровища, затем зайди в портал.\n\n"
                  "Управление:\n"
                  " ПК: стрелки / WASD.\n"
                  " Телефон: кнопки ^ v < > внизу.\n\n"
                  "Магазин: покупай бомбы за очки.\n"
                  "Бомба взрывает одну стену рядом с тобой."),
            halign="left", valign="top",
        )
        htxt.bind(size=lambda *_: setattr(htxt, "text_size", htxt.size))
        back2 = Button(text="Назад", size_hint_y=None, height=50)
        back2.bind(on_release=self.go_menu)
        hbox.add_widget(htitle)
        hbox.add_widget(htxt)
        hbox.add_widget(back2)
        hbox.add_widget(Label())
        how.add_widget(hbox)
        self.sm.add_widget(how)

        # SHOP
        shop = Screen(name="shop")
        shop_box = BoxLayout(orientation="vertical", padding=20, spacing=10)
        sh_title = Label(text="Магазин", font_size="26sp",
                         size_hint_y=None, height=40)
        self.shop_info = Label(text="", size_hint_y=None, height=40)
        self.shop_msg = Label(text="", font_size="16sp",
                              size_hint_y=None, height=30)

        buy_btn = Button(text="Купить бомбу (30 очков)", size_hint_y=None, height=50)
        back3 = Button(text="Назад", size_hint_y=None, height=50)

        def on_buy(_btn):
            price = 30
            if self.st.score >= price:
                self.st.score -= price
                self.st.bombs += 1
                self.shop_msg.text = "Бомба куплена!"
            else:
                self.shop_msg.text = "Не хватает очков."
            self._update_shop_labels()
            self.save_progress()

        buy_btn.bind(on_release=on_buy)
        back3.bind(on_release=self.go_menu)

        shop_box.add_widget(sh_title)
        shop_box.add_widget(self.shop_info)
        shop_box.add_widget(self.shop_msg)
        shop_box.add_widget(buy_btn)
        shop_box.add_widget(back3)
        shop_box.add_widget(Label())
        shop.add_widget(shop_box)
        self.sm.add_widget(shop)

        # через 1.8 сек после старта — в меню
        Clock.schedule_once(lambda dt: self.go_menu(), 1.8)

    def _create_game_ui(self):
        root = BoxLayout(orientation="vertical", spacing=6, padding=6)

        hud = Label(
            text="",
            size_hint_y=None,
            height=56,
            halign="left",
            valign="middle",
        )
        hud.bind(size=lambda *_: setattr(hud, "text_size", hud.size))

        game_widget = GameWidget(self.st)

        controls = BoxLayout(size_hint_y=None, height=120, spacing=6)

        left = Button(text="<")
        right = Button(text=">")
        up = Button(text="^")
        down = Button(text="v")
        bomb_btn = Button(text="Bomb")

        next_btn = Button(text="Next")
        restart_btn = Button(text="Restart")

        left.bind(on_release=lambda *_: game_widget.step(-1, 0))
        right.bind(on_release=lambda *_: game_widget.step(1, 0))
        up.bind(on_release=lambda *_: game_widget.step(0, 1))
        down.bind(on_release=lambda *_: game_widget.step(0, -1))
        bomb_btn.bind(on_release=lambda *_: game_widget.use_bomb())

        def on_next(_btn):
            if self.st.message and self.st.lives > 0:
                self.st.level += 1
                self.st.load_level()
                self.save_progress()
                game_widget.redraw()

        def on_restart(_btn):
            self.st.restart()
            self.save_progress()
            game_widget.redraw()

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
        controls.add_widget(bomb_btn)
        controls.add_widget(next_btn)
        controls.add_widget(restart_btn)

        root.add_widget(hud)
        root.add_widget(game_widget)
        root.add_widget(controls)

        game_widget.redraw()
        return root, hud, game_widget

    # ---------- навигация ----------

    def go_menu(self, *_):
        self.sm.current = "menu"

    def go_game(self, *_):
        self.sm.current = "game"

    def go_settings(self, *_):
        self.sm.current = "settings"

    def go_howto(self, *_):
        self.sm.current = "howto"

    def go_shop(self, *_):
        self._update_shop_labels()
        self.sm.current = "shop"

    # ---------- Game Over окно ----------

    def show_game_over_dialog(self) -> None:
        self.game_over_active = True

        content = BoxLayout(orientation="vertical", padding=20, spacing=15)

        title_lbl = Label(
            text="Жизни закончились",
            font_size="22sp",
            size_hint_y=None,
            height=40,
        )
        info_lbl = Label(
            text="Что делать дальше?",
            font_size="16sp",
            size_hint_y=None,
            height=30,
        )

        btn_box = BoxLayout(orientation="horizontal", spacing=10,
                            size_hint_y=None, height=50)
        btn_restart = Button(text="Рестарт")
        btn_menu = Button(text="В меню")

        btn_box.add_widget(btn_restart)
        btn_box.add_widget(btn_menu)

        content.add_widget(title_lbl)
        content.add_widget(info_lbl)
        content.add_widget(btn_box)

        popup = Popup(
            title="Игра окончена",
            content=content,
            size_hint=(0.8, 0.4),
            auto_dismiss=False,
        )

        def do_restart(_btn):
            self.game_over_active = False
            self.st.restart()
            self.save_progress()
            self.game.redraw()
            popup.dismiss()
            self.sm.current = "game"

        def do_menu(_btn):
            self.game_over_active = False
            popup.dismiss()
            self.sm.current = "menu"

        btn_restart.bind(on_release=do_restart)
        btn_menu.bind(on_release=do_menu)

        popup.open()

    # ---------- сохранение и служебное ----------

    def save_progress(self) -> None:
        if hasattr(self, "store"):
            self.store.put(
                "progress",
                score=int(self.st.score),
                bombs=int(self.st.bombs),
                level=int(self.st.level),
            )

    def save_settings(self) -> None:
        if hasattr(self, "store"):
            self.store.put(
                "settings",
                music_enabled=bool(self.music_enabled),
                sounds_enabled=bool(self.sounds_enabled),
            )

    def _update_shop_labels(self) -> None:
        if hasattr(self, "shop_info"):
            self.shop_info.text = f"Бомбы: {self.st.bombs}   Очки: {self.st.score}"

    def flash_message(self, text: str, duration: float = 1.2) -> None:
        self.st.message = text

        def clear(_dt):
            if self.st.message == text:
                self.st.message = None

        Clock.schedule_once(clear, duration)

    def _update_hud(self, _dt):
        left = len(self.st.treasures) if self.st.treasures is not None else 0
        msg = self.st.message or ""
        if hasattr(self, "hud"):
            self.hud.text = (
                f"Уровень: {self.st.level}   Жизни: {self.st.lives}/{self.st.max_lives}   "
                f"Очки: {self.st.score}   Бомбы: {self.st.bombs}   Осталось T: {left}   {msg}"
            )
        self._update_shop_labels()


if __name__ == "__main__":
    MyGameApp().run()