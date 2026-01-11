import math
import random
from dataclasses import dataclass
from typing import List, Set, Optional

from logic import (
    Pos,
    LevelConfig,
    level_config,
    generate_level,
    try_move,
    enemy_turn,
    neighbors4,
    in_bounds,
    bfs_distances,   # <-- добавили
)

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

# ---------------------------
# Базовые цвета
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


# ---------------------------
# Биомы
# ---------------------------

@dataclass
class Biome:
    name: str
    bg: tuple
    floor: tuple
    wall: tuple
    goal: tuple


def get_biome_for_level(level: int) -> Biome:
    idx = (level - 1) // 5  # каждые 5 уровней новый биом

    if idx == 0:
        return Biome(
            name="Гробница",
            bg=(0.03, 0.04, 0.08),
            floor=(0.12, 0.13, 0.22),
            wall=(0.08, 0.09, 0.14),
            goal=(0.80, 0.50, 1.00),
        )
    elif idx == 1:
        return Biome(
            name="Ледяные пещеры",
            bg=(0.02, 0.06, 0.10),
            floor=(0.10, 0.18, 0.28),
            wall=(0.06, 0.12, 0.20),
            goal=(0.55, 0.80, 1.00),
        )
    elif idx == 2:
        return Biome(
            name="Лавовые глубины",
            bg=(0.06, 0.02, 0.05),
            floor=(0.20, 0.08, 0.08),
            wall=(0.25, 0.10, 0.05),
            goal=(1.00, 0.60, 0.20),
        )
    else:
        return Biome(
            name="Руины джунглей",
            bg=(0.02, 0.06, 0.03),
            floor=(0.10, 0.18, 0.10),
            wall=(0.07, 0.13, 0.07),
            goal=(0.60, 0.90, 0.50),
        )


# ---------------------------
# Состояние игры
# ---------------------------

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


# ---------------------------
# Игровое поле (виджет)
# ---------------------------

class GameWidget(Widget):
    def __init__(self, state: GameState, **kwargs):
        super().__init__(**kwargs)
        self.state = state
        self.anim_time = 0.0
        self.explosions: List[tuple[int, int, float]] = []
        self.hit_flashes: List[tuple[int, int, float]] = []
        self.last_enemy_positions: List[Pos] = []
        self.shake_remaining = 0.0
        self.shake_max = 0.001
        self.shake_strength = 0.0
        self._touch_start = None
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw())

        Window.bind(on_key_down=self._on_key_down)

    # ---- управление ----

    def _on_key_down(self, _window, key, _scancode, _codepoint, _modifiers):
        from kivy.app import App
        app = App.get_running_app()
        if getattr(app, "game_over_active", False) or getattr(app, "paused", False):
            return True

        if key in (273,):      # вверх
            self.step(0, 1)
        elif key in (274,):    # вниз
            self.step(0, -1)
        elif key in (276,):    # влево
            self.step(-1, 0)
        elif key in (275,):    # вправо
            self.step(1, 0)
        return True

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        self._touch_start = touch.pos
        return True

    def on_touch_up(self, touch):
        from kivy.app import App
        app = App.get_running_app()
        if getattr(app, "game_over_active", False) or getattr(app, "paused", False):
            return True

        if self._touch_start is None:
            return super().on_touch_up(touch)
        sx, sy = self._touch_start
        dx = touch.x - sx
        dy = touch.y - sy
        self._touch_start = None

        threshold = 30
        if abs(dx) < threshold and abs(dy) < threshold:
            return True

        if abs(dx) > abs(dy):
            if dx > 0:
                self.step(1, 0)
            else:
                self.step(-1, 0)
        else:
            if dy > 0:
                self.step(0, 1)
            else:
                self.step(0, -1)
        return True

    def start_shake(self, strength: float, duration: float) -> None:
        self.shake_remaining = duration
        self.shake_max = max(duration, 0.001)
        self.shake_strength = strength

    # ---- логика хода + Undo ----

    def step(self, dx: int, dy: int) -> None:
        from kivy.app import App
        app: "MyGameApp" = App.get_running_app()
        st = self.state

        if st.message or getattr(app, "game_over_active", False) or getattr(app, "paused", False):
            return

        # Сохраняем состояние для Undo (последний ход)
        app.save_undo_state()

        st.player = try_move(st.walls, st.player, dx, dy)

        # подбор сокровищ
        if st.player in st.treasures:
            st.treasures.remove(st.player)
            st.score += 10
            if getattr(app, "sounds_enabled", True) and getattr(app, "snd_pickup", None):
                app.snd_pickup.play()

        # подбор аптечки
        if st.player in st.medkits:
            st.medkits.remove(st.player)
            st.lives = min(st.max_lives, st.lives + 1)
            st.score += 5
            if getattr(app, "sounds_enabled", True) and getattr(app, "snd_pickup", None):
                app.snd_pickup.play()

        # победа уровня
        if st.player == st.goal and len(st.treasures) == 0:
            reward = 5 + st.level
            app.add_crystals(reward)
            st.score += 50 + st.level * 10
            st.message = "Уровень пройден! (Next)"
            app.save_progress()
            self.redraw()
            return

        # ход врагов
        self.last_enemy_positions = list(st.enemies)
        st.enemies = enemy_turn(st.walls, st.enemies, st.player, st.cfg.enemy_steps)

        # столкновение
        if st.player in set(st.enemies):
            hit_pos = st.player  # где столкнулись
            st.lives -= 1
            st.score = max(0, st.score - 15)
            st.player = st.start  # игрок возвращается на старт

            # ТЕЛЕПОРТИРУЕМ вражеского скелета(ов), стоявших в hit_pos, подальше от нового положения игрока
            app.teleport_enemy_far(st, hit_pos)

            self.hit_flashes.append((hit_pos[0], hit_pos[1], self.anim_time))
            self.start_shake(strength=0.6, duration=0.20)

            if getattr(app, "sounds_enabled", True) and getattr(app, "snd_hit", None):
                app.snd_hit.play()

            if st.lives <= 0:
                app.save_progress()
                if not app.game_over_active:
                    app.game_over_active = True
                    app.show_game_over_dialog()
                return

        app.save_progress()
        self.redraw()

    def use_bomb(self) -> None:
        from kivy.app import App
        app: "MyGameApp" = App.get_running_app()
        st = self.state

        if app.game_over_active or app.paused:
            return

        if st.bombs <= 0:
            app.flash_message("Нет бомб")
            return

        px, py = st.player
        targets: List[Pos] = []
        h = len(st.walls)
        w = len(st.walls[0]) if h else 0

        for nx, ny in neighbors4((px, py)):
            if in_bounds(nx, ny, w, h) and st.walls[ny][nx] == "#":
                targets.append((nx, ny))

        if not targets:
            app.flash_message("Рядом нет стены")
            return

        tx, ty = random.choice(targets)
        st.walls[ty][tx] = "."
        st.bombs -= 1
        self.explosions.append((tx, ty, self.anim_time))
        self.start_shake(strength=1.0, duration=0.25)

        if getattr(app, "sounds_enabled", True) and getattr(app, "snd_explosion", None):
            app.snd_explosion.play()

        app.save_progress()
        app.flash_message("Бум!")
        self.redraw()

    def animate(self, dt: float) -> None:
        self.anim_time += dt
        self.explosions = [
            (x, y, t0) for (x, y, t0) in self.explosions
            if self.anim_time - t0 < 0.5
        ]
        self.hit_flashes = [
            (x, y, t0) for (x, y, t0) in self.hit_flashes
            if self.anim_time - t0 < 0.35
        ]
        if self.shake_remaining > 0:
            self.shake_remaining = max(0.0, self.shake_remaining - dt)
        self.redraw()

    # ---- отрисовка ----

    def redraw(self) -> None:
        st = self.state
        if not st.walls or not st.cfg:
            return

        from kivy.app import App
        app: "MyGameApp" = App.get_running_app()
        player_tex = getattr(app, "player_tex", None)
        skeleton_tex = getattr(app, "skeleton_tex", None)
        explosion_frames: List = getattr(app, "explosion_frames", [])
        biome = getattr(app, "biome", None)
        bg_col = getattr(biome, "bg", COL_BG)
        floor_col = getattr(biome, "floor", COL_FLOOR)
        wall_col = getattr(biome, "wall", COL_WALL)
        goal_col = getattr(biome, "goal", COL_GOAL)

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

        # тряска камеры
        shake_x = shake_y = 0.0
        if self.shake_remaining > 0:
            t = self.shake_remaining / max(self.shake_max, 0.001)
            amp = self.shake_strength * t
            shake_x = (random.random() * 2 - 1) * amp * tile * 0.25
            shake_y = (random.random() * 2 - 1) * amp * tile * 0.25

        ox = self.x + (self.width - grid_w) / 2 + shake_x
        oy = self.y + (self.height - grid_h) / 2 + shake_y

        with self.canvas:
            # ---------------- ФОН: градиент + виньетка ----------------
            # базовая заливка
            Color(*bg_col)
            Rectangle(pos=(self.x, self.y), size=(self.width, self.height))

            # вертикальный "сияющий" градиент (светлее в центре)
            steps = 7
            for i in range(steps):
                t = i / max(steps - 1, 1)
                # ближе к середине экрана — чуть светлее
                k = 0.7 + 0.4 * (1.0 - abs(2 * t - 1.0))
                gcol = (bg_col[0] * k, bg_col[1] * k, bg_col[2] * k, 0.45)
                Color(*gcol)
                y0 = self.y + self.height * t
                Rectangle(
                    pos=(self.x, y0),
                    size=(self.width, self.height / steps),
                )

            # мягкая виньетка по краям
            vignette_alpha = 0.30
            Color(0, 0, 0, vignette_alpha)
            # слева
            Rectangle(pos=(self.x, self.y),
                      size=(self.width * 0.05, self.height))
            # справа
            Rectangle(pos=(self.x + self.width * 0.95, self.y),
                      size=(self.width * 0.05, self.height))
            # снизу
            Rectangle(pos=(self.x, self.y),
                      size=(self.width, self.height * 0.07))
            # сверху
            Rectangle(pos=(self.x, self.y + self.height * 0.93),
                      size=(self.width, self.height * 0.07))

            # подсветка под полем
            Color(0.10, 0.12, 0.22, 1)
            Rectangle(pos=(ox - 8, oy - 8), size=(grid_w + 16, grid_h + 16))

            # ---------------- КЛЕТКИ ----------------
            for yy in range(h):
                row_factor = 0.8 + 0.25 * (yy / max(1, h - 1))
                for xx in range(w):
                    cell = st.walls[yy][xx]
                    if cell == "#":
                        Color(*(wall_col[0] * row_factor,
                                wall_col[1] * row_factor,
                                wall_col[2] * row_factor, 1))
                    else:
                        Color(*(floor_col[0] * row_factor,
                                floor_col[1] * row_factor,
                                floor_col[2] * row_factor, 1))
                    Rectangle(pos=(ox + xx * tile, oy + yy * tile), size=(tile, tile))

            # тонкий внутренний контур сетки
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
                cx0 = ox + x * tile
                cy0 = oy + y * tile
                d = tile * (1.0 - 2 * inset)

                # лёгкое сияние вокруг
                Color(color[0], color[1], color[2], 0.35)
                Ellipse(pos=(cx0 + tile * inset - d * 0.25,
                             cy0 + tile * inset - d * 0.25),
                        size=(d * 1.5, d * 1.5))

                Color(*color)
                Ellipse(pos=(cx0 + tile * inset, cy0 + tile * inset),
                        size=(d, d))

            # --------- Сокровища, аптечки, портал (под врагами) ----------
            for t in st.treasures:
                draw_pulse_dot(t, COL_TREASURE, 0.26, speed=3.0)
            for m in st.medkits:
                draw_pulse_dot(m, COL_MEDKIT, 0.28, speed=2.0)

            # портал + орбиты
            gx, gy = st.goal
            cx_goal = ox + gx * tile + tile * 0.5
            cy_goal = oy + gy * tile + tile * 0.5
            draw_pulse_dot(st.goal, goal_col, 0.24, speed=2.5)
            orbit_r = tile * 0.35
            for i in range(3):
                ang = self.anim_time * 2.0 + i * (2 * math.pi / 3)
                ox2 = cx_goal + orbit_r * math.cos(ang)
                oy2 = cy_goal + orbit_r * math.sin(ang)
                Color(goal_col[0], goal_col[1], goal_col[2], 0.75)
                Ellipse(pos=(ox2 - tile * 0.08, oy2 - tile * 0.08),
                        size=(tile * 0.16, tile * 0.16))

            # прошлые позиции врагов — подсветка хода (под самими врагами)
            Color(1.0, 0.4, 0.4, 0.25)
            for ex, ey in self.last_enemy_positions:
                Ellipse(
                    pos=(ox + ex * tile + tile * 0.12,
                         oy + ey * tile + tile * 0.12),
                    size=(tile * 0.76, tile * 0.76),
                )

            # --------- Фигуры игрока/врагов (если нет спрайтов) ----------
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

            # --- ВРАГИ (аура + спрайт/фигура) ---
            for e in st.enemies:
                ex, ey = e
                cell_x = ox + ex * tile
                cell_y = oy + ey * tile
                cx_e = cell_x + tile * 0.5
                cy_e = cell_y + tile * 0.5
                bob = math.sin(self.anim_time * 4.5 + (ex + ey) * 0.7) * tile * 0.05

                Color(1.0, 0.3, 0.3, 0.35)
                Ellipse(pos=(cx_e - tile * 0.45, cy_e - tile * 0.45),
                        size=(tile * 0.9, tile * 0.9))

                if skeleton_tex:
                    sz = tile * 0.9
                    Color(1, 1, 1, 1)
                    Rectangle(texture=skeleton_tex,
                              pos=(cx_e - sz / 2, cy_e - sz / 2 + bob),
                              size=(sz, sz))
                else:
                    draw_skeleton_shape(e)

            # --- ИГРОК (аура + спрайт/фигура) ---
            px, py = st.player
            cell_x = ox + px * tile
            cell_y = oy + py * tile
            pcx = cell_x + tile * 0.5
            pcy = cell_y + tile * 0.5
            pbob = math.sin(self.anim_time * 5.0 + (px + py) * 0.5) * tile * 0.06

            Color(0.3, 0.6, 1.0, 0.4)
            Ellipse(pos=(pcx - tile * 0.45, pcy - tile * 0.45),
                    size=(tile * 0.9, tile * 0.9))

            if player_tex:
                psz = tile * 0.9
                Color(1, 1, 1, 1)
                Rectangle(texture=player_tex,
                          pos=(pcx - psz / 2, pcy - psz / 2 + pbob),
                          size=(psz, psz))
            else:
                draw_hunter_shape(st.player)

            # --- ВЗРЫВЫ БОМБ ---
            for ex, ey, t0 in self.explosions:
                age = self.anim_time - t0
                if age < 0:
                    continue
                progress = min(1.0, age / 0.5)
                cx_ex = ox + ex * tile + tile * 0.5
                cy_ex = oy + ey * tile + tile * 0.5
                alpha = 1.0 - progress

                if explosion_frames:
                    frame_id = int(progress * (len(explosion_frames) - 1))
                    frame = explosion_frames[frame_id]
                    sz = tile * 1.4
                    Color(1, 1, 1, alpha)
                    Rectangle(texture=frame,
                              pos=(cx_ex - sz / 2, cy_ex - sz / 2),
                              size=(sz, sz))
                else:
                    radius = tile * (0.2 + 0.5 * progress)
                    Color(1.0, 0.5, 0.2, alpha)
                    Ellipse(pos=(cx_ex - radius, cy_ex - radius),
                            size=(2 * radius, 2 * radius))
                    Color(1.0, 0.9, 0.6, alpha)
                    inner = radius * 0.6
                    Ellipse(pos=(cx_ex - inner, cy_ex - inner),
                            size=(2 * inner, 2 * inner))

            # --- ВСПЫШКИ УДАРОВ ---
            for hx, hy, t0 in self.hit_flashes:
                age = self.anim_time - t0
                if age < 0:
                    continue
                progress = min(1.0, age / 0.35)
                radius = tile * (0.3 + 0.4 * progress)
                alpha = 1.0 - progress
                cx_h = ox + hx * tile + tile * 0.5
                cy_h = oy + hy * tile + tile * 0.5
                Color(1.0, 0.2, 0.3, alpha)
                Line(circle=(cx_h, cy_h, radius), width=2.5)
                Color(1.0, 0.4, 0.4, alpha * 0.4)
                Ellipse(pos=(cx_h - radius * 0.6, cy_h - radius * 0.6),
                        size=(radius * 1.2, radius * 1.2))

# ---------------------------
# Приложение
# ---------------------------

class MyGameApp(App):
    def teleport_enemy_far(self, st: GameState, hit_pos: Pos) -> None:
        """Телепортирует врага(ов), стоявших в hit_pos, на далёкую от игрока клетку."""
        if not st.walls or not st.cfg:
            return

        # расстояния от текущей позиции игрока
        dist = bfs_distances(st.walls, st.player)
        if not dist:
            return

        h = len(st.walls)
        w = len(st.walls[0]) if h else 0

        # базовая безопасная дистанция
        min_safe = max(6, (w + h) // 4)

        # уже занятые врагами клетки
        occupied = set(st.enemies)

        # все потенциальные клетки: достаточно далеко, не стена, не игрок
        candidates: List[Pos] = []
        for (x, y), d in dist.items():
            if d < min_safe:
                continue
            if st.walls[y][x] == "#":
                continue
            if (x, y) == st.player:
                continue
            candidates.append((x, y))

        if not candidates:
            return

        random.shuffle(candidates)

        # телепортируем всех врагов, стоявших в hit_pos
        for i, e in enumerate(st.enemies):
            if e == hit_pos:
                # освободим старую клетку
                occupied.discard(e)
                # найдём новую, не занятую
                for c in candidates:
                    if c not in occupied:
                        st.enemies[i] = c
                        occupied.add(c)
                        break

    def build(self):
        random.seed()

        self.st = GameState()
        self.game_over_active = False
        self.paused = False

        self.store = JsonStore("save.json")
        self.music_enabled = True
        self.sounds_enabled = True

        # метапрогрессия
        self.crystals = 0
        self.upgrades = {
            "max_lives": 0,
            "start_bombs": 0,
            "shop_discount": 0,
            "start_medkit_chance": 0.0,
            "start_bomb_chance": 0.0,
        }

        # Undo
        self.undo_state = None
        self.undo_available = True

        # debug overlay
        self.debug_overlay = False
        Window.bind(on_key_down=self._on_key_down_global)

        if self.store.exists("settings"):
            sdata = self.store.get("settings")
            self.music_enabled = bool(sdata.get("music_enabled", True))
            self.sounds_enabled = bool(sdata.get("sounds_enabled", True))

        if self.store.exists("progress"):
            data = self.store.get("progress")
            self.st.score = int(data.get("score", 0))
            self.st.bombs = int(data.get("bombs", 0))
            self.st.level = max(1, int(data.get("level", 1)))

        if self.store.exists("meta"):
            m = self.store.get("meta")
            self.crystals = int(m.get("crystals", 0))
            up = m.get("upgrades", {})
            self.upgrades["max_lives"] = int(up.get("max_lives", 0))
            self.upgrades["start_bombs"] = int(up.get("start_bombs", 0))
            self.upgrades["shop_discount"] = int(up.get("shop_discount", 0))
            self.upgrades["start_medkit_chance"] = float(up.get("start_medkit_chance", 0.0))
            self.upgrades["start_bomb_chance"] = float(up.get("start_bomb_chance", 0.0))

        self.st.load_level()
        self.apply_upgrades_to_state()
        self.apply_start_items(new_level=True)
        self.biome = get_biome_for_level(self.st.level)

        self.player_tex = self._load_texture("assets/player.png")
        self.skeleton_tex = self._load_texture("assets/skeleton.png")
        self.explosion_frames = self._load_explosion_frames("assets/explosion_", 8)

        self.snd_pickup = self._load_sound("assets/snd_pickup.mp3")
        self.snd_hit = self._load_sound("assets/snd_hit.mp3")
        self.snd_explosion = self._load_sound("assets/snd_explosion.wav")

        self.music_sound = self._load_sound("assets/music.mp3")
        self.set_music_enabled(self.music_enabled)

        self.sm = ScreenManager(transition=FadeTransition())
        self._build_screens()

        Clock.schedule_interval(self._update_hud, 0.1)
        Clock.schedule_interval(self.game.animate, 1 / 30.0)

        return self.sm

    # ----- глобальная клавиатура (F2) -----

    def _on_key_down_global(self, window, key, scancode, codepoint, modifiers):
        # F2
        if key == 293:
            self.debug_overlay = not self.debug_overlay
            return True
        return False

    # ----- Undo -----

    def save_undo_state(self) -> None:
        if not self.undo_available:
            return
        st = self.st
        self.undo_state = {
            "score": st.score,
            "lives": st.lives,
            "bombs": st.bombs,
            "player": st.player,
            "treasures": set(st.treasures),
            "medkits": set(st.medkits),
            "enemies": list(st.enemies),
            "walls": [row[:] for row in st.walls],
        }

    def perform_undo(self, game_widget: GameWidget) -> None:
        if not self.undo_state:
            self.flash_message("Отмена недоступна")
            return
        st = self.st
        u = self.undo_state
        st.score = u["score"]
        st.lives = u["lives"]
        st.bombs = u["bombs"]
        st.player = u["player"]
        st.treasures = set(u["treasures"])
        st.medkits = set(u["medkits"])
        st.enemies = list(u["enemies"])
        st.walls = [row[:] for row in u["walls"]]
        st.message = None
        self.undo_state = None
        self.undo_available = False
        game_widget.redraw()

    def reset_undo_for_level(self) -> None:
        self.undo_state = None
        self.undo_available = True

    # --- апгрейды / мета ---

    def apply_upgrades_to_state(self) -> None:
        base_max_lives = 3
        extra = int(self.upgrades.get("max_lives", 0))
        self.st.max_lives = base_max_lives + extra
        if self.st.lives > self.st.max_lives:
            self.st.lives = self.st.max_lives

    def apply_start_items(self, new_level: bool) -> None:
        if new_level:
            start_bombs = int(self.upgrades.get("start_bombs", 0))
            self.st.bombs += start_bombs

        if random.random() < float(self.upgrades.get("start_medkit_chance", 0.0)):
            self.st.lives = min(self.st.max_lives, self.st.lives + 1)
        if random.random() < float(self.upgrades.get("start_bomb_chance", 0.0)):
            self.st.bombs += 1

    def add_crystals(self, amount: int) -> None:
        if amount <= 0:
            return
        self.crystals += amount
        self.save_meta()

    def save_meta(self) -> None:
        if hasattr(self, "store"):
            self.store.put(
                "meta",
                crystals=int(self.crystals),
                upgrades=self.upgrades,
            )

    # --- загрузка ресурсов ---

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

    # --- музыка/звук ---

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

    # --- экраны ---

    def _build_screens(self) -> None:
        # --- SPLASH ---
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

        # --- MENU ---
        menu = Screen(name="menu")
        mbox = BoxLayout(orientation="vertical", padding=20, spacing=15)
        mtitle = Label(text="Искатель сокровищ", font_size="30sp",
                       size_hint_y=None, height=60)
        btn_play = Button(text="Играть", size_hint_y=None, height=60)
        btn_settings = Button(text="Настройки", size_hint_y=None, height=50)
        btn_how = Button(text="Как играть", size_hint_y=None, height=50)
        btn_shop = Button(text="Магазин", size_hint_y=None, height=50)
        btn_upgrades = Button(text="Улучшения", size_hint_y=None, height=50)
        btn_exit = Button(text="Выход", size_hint_y=None, height=50)

        btn_play.bind(on_release=self.go_game)
        btn_settings.bind(on_release=self.go_settings)
        btn_how.bind(on_release=self.go_howto)
        btn_shop.bind(on_release=self.go_shop)
        btn_upgrades.bind(on_release=self.go_upgrades)
        btn_exit.bind(on_release=lambda *_: self.stop())

        mbox.add_widget(mtitle)
        mbox.add_widget(btn_play)
        mbox.add_widget(btn_settings)
        mbox.add_widget(btn_how)
        mbox.add_widget(btn_shop)
        mbox.add_widget(btn_upgrades)
        mbox.add_widget(btn_exit)
        mbox.add_widget(Label())
        menu.add_widget(mbox)
        self.sm.add_widget(menu)

        # --- GAME ---
        game_screen = Screen(name="game")
        game_root, self.hud, self.game = self._create_game_ui()
        game_screen.add_widget(game_root)
        self.sm.add_widget(game_screen)

        # --- SETTINGS ---
        settings = Screen(name="settings")
        sbox = BoxLayout(orientation="vertical", padding=20, spacing=10)

        stitle = Label(text="Настройки", font_size="26sp",
                       size_hint_y=None, height=40)

        music_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                              height=50, spacing=10)
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

        sound_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                              height=50, spacing=10)
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
                 "Позже можно добавить громкость и вибро.",
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

        # --- HOW TO ---
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
                  " Телефон: кнопки ^ v < > или свайпы.\n\n"
                  "Магазин: покупай бомбы за очки.\n"
                  "Улучшения: трать кристаллы на апгрейды."),
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

        # --- SHOP ---
        shop = Screen(name="shop")
        shop_box = BoxLayout(orientation="vertical", padding=20, spacing=10)
        sh_title = Label(text="Магазин", font_size="26sp",
                         size_hint_y=None, height=40)
        self.shop_info = Label(text="", size_hint_y=None, height=40)
        self.shop_msg = Label(text="", font_size="16sp",
                              size_hint_y=None, height=30)

        self.shop_buy_btn = Button(size_hint_y=None, height=50)
        back3 = Button(text="Назад", size_hint_y=None, height=50)

        def on_buy(_btn):
            base_price = 30
            discount = int(self.upgrades.get("shop_discount", 0))
            price = max(1, int(base_price * (100 - discount) / 100))
            if self.st.score >= price:
                self.st.score -= price
                self.st.bombs += 1
                self.shop_msg.text = f"Бомба куплена за {price} очков!"
                self.save_progress()
            else:
                self.shop_msg.text = "Не хватает очков."
            self._update_shop_labels()

        self.shop_buy_btn.bind(on_release=on_buy)
        back3.bind(on_release=self.go_menu)

        shop_box.add_widget(sh_title)
        shop_box.add_widget(self.shop_info)
        shop_box.add_widget(self.shop_msg)
        shop_box.add_widget(self.shop_buy_btn)
        shop_box.add_widget(back3)
        shop_box.add_widget(Label())
        shop.add_widget(shop_box)
        self.sm.add_widget(shop)
        self._update_shop_button_text()

        # --- UPGRADES ---
        upgrades = Screen(name="upgrades")
        ubox = BoxLayout(
            orientation="vertical",
            padding=(20, 20, 20, 20),
            spacing=8,
        )

        utitle = Label(
            text="Улучшения",
            font_size="26sp",
            size_hint_y=None,
            height=40,
        )

        # многострочная инфа об апгрейдах
        self.upgrades_info = Label(
            text="",
            size_hint_y=None,
            halign="left",
            valign="top",
        )

        def _update_info_size(label, size):
            label.text_size = (label.width, None)
            label.height = label.texture_size[1] + 4

        self.upgrades_info.bind(size=_update_info_size)

        # сообщение о покупке/ошибке
        self.upgrades_msg = Label(
            text="",
            font_size="16sp",
            size_hint_y=None,
            halign="center",
            valign="middle",
        )

        def _update_msg_size(label, size):
            label.text_size = (label.width, None)
            label.height = max(30, label.texture_size[1] + 4)

        self.upgrades_msg.bind(size=_update_msg_size)

        btn_max_lives = Button(size_hint_y=None, height=46)
        btn_start_bombs = Button(size_hint_y=None, height=46)
        btn_discount = Button(size_hint_y=None, height=46)
        btn_start_med = Button(size_hint_y=None, height=46)
        btn_start_bomb = Button(size_hint_y=None, height=46)
        back_upg = Button(text="Назад", size_hint_y=None, height=46)

        # --- функции для кнопок/инфо ---
        def refresh_upgrade_buttons():
            u = self.upgrades
            ml = int(u["max_lives"])
            sb = int(u["start_bombs"])
            disc = int(u["shop_discount"])
            med_lvl = int(u["start_medkit_chance"] * 10)
            bomb_lvl = int(u["start_bomb_chance"] * 10)

            btn_max_lives.text = f"+1 к макс. жизням (ур. {ml}/2, цена {20 + 10*ml} кр.)"
            btn_start_bombs.text = f"+1 старт. бомба (ур. {sb}/3, цена {15 + 8*sb} кр.)"
            btn_discount.text = f"+5% скидка (текущая {disc}%, цена {25 + 10*(disc//5)} кр., макс 25%)"
            btn_start_med.text = f"+10% старт. аптечка (ур. {med_lvl}/5, цена {18 + 6*med_lvl} кр.)"
            btn_start_bomb.text = f"+10% старт. бомба (ур. {bomb_lvl}/5, цена {18 + 6*bomb_lvl} кр.)"

        def update_upgrades_info():
            u = self.upgrades
            text = (
                f"Кристаллы: {self.crystals}\n"
                f"+макс. жизней: {u['max_lives']}\n"
                f"+старт. бомб: {u['start_bombs']}\n"
                f"Скидка в магазине: {u['shop_discount']}%\n"
                f"Шанс старт. аптечки: {int(u['start_medkit_chance']*100)}%\n"
                f"Шанс старт. бомбы: {int(u['start_bomb_chance']*100)}%"
            )
            self.upgrades_info.text = text

        self.update_upgrades_info = update_upgrades_info

        refresh_upgrade_buttons()
        update_upgrades_info()

        def buy_max_lives(_btn):
            lvl = int(self.upgrades["max_lives"])
            if lvl >= 2:
                self.upgrades_msg.text = "Макс. жизни уже максимум."
                return
            price = 20 + 10 * lvl
            if self.crystals < price:
                self.upgrades_msg.text = "Недостаточно кристаллов."
                return
            self.crystals -= price
            self.upgrades["max_lives"] = lvl + 1
            self.apply_upgrades_to_state()
            self.save_meta()
            self.upgrades_msg.text = "Макс. жизни увеличены!"
            update_upgrades_info()
            refresh_upgrade_buttons()

        def buy_start_bombs(_btn):
            lvl = int(self.upgrades["start_bombs"])
            if lvl >= 3:
                self.upgrades_msg.text = "Старт. бомб уже максимум."
                return
            price = 15 + 8 * lvl
            if self.crystals < price:
                self.upgrades_msg.text = "Недостаточно кристаллов."
                return
            self.crystals -= price
            self.upgrades["start_bombs"] = lvl + 1
            self.save_meta()
            self.upgrades_msg.text = "Стартовые бомбы улучшены!"
            update_upgrades_info()
            refresh_upgrade_buttons()

        def buy_discount(_btn):
            disc = int(self.upgrades["shop_discount"])
            if disc >= 25:
                self.upgrades_msg.text = "Скидка уже максимум."
                return
            step = 5
            level = disc // step
            price = 25 + 10 * level
            if self.crystals < price:
                self.upgrades_msg.text = "Недостаточно кристаллов."
                return
            self.crystals -= price
            self.upgrades["shop_discount"] = disc + step
            self.save_meta()
            self.upgrades_msg.text = "Скидка увеличена!"
            update_upgrades_info()
            refresh_upgrade_buttons()
            self._update_shop_button_text()

        def buy_start_med(_btn):
            lvl = int(self.upgrades["start_medkit_chance"] * 10)
            if lvl >= 5:
                self.upgrades_msg.text = "Шанс аптечки уже максимум."
                return
            price = 18 + 6 * lvl
            if self.crystals < price:
                self.upgrades_msg.text = "Недостаточно кристаллов."
                return
            self.crystals -= price
            self.upgrades["start_medkit_chance"] = (lvl + 1) / 10.0
            self.save_meta()
            self.upgrades_msg.text = "Шанс старт. аптечки увеличен!"
            update_upgrades_info()
            refresh_upgrade_buttons()

        def buy_start_bomb(_btn):
            lvl = int(self.upgrades["start_bomb_chance"] * 10)
            if lvl >= 5:
                self.upgrades_msg.text = "Шанс старт. бомбы уже максимум."
                return
            price = 18 + 6 * lvl
            if self.crystals < price:
                self.upgrades_msg.text = "Недостаточно кристаллов."
                return
            self.crystals -= price
            self.upgrades["start_bomb_chance"] = (lvl + 1) / 10.0
            self.save_meta()
            self.upgrades_msg.text = "Шанс старт. бомбы увеличен!"
            update_upgrades_info()
            refresh_upgrade_buttons()

        btn_max_lives.bind(on_release=buy_max_lives)
        btn_start_bombs.bind(on_release=buy_start_bombs)
        btn_discount.bind(on_release=buy_discount)
        btn_start_med.bind(on_release=buy_start_med)
        btn_start_bomb.bind(on_release=buy_start_bomb)
        back_upg.bind(on_release=self.go_menu)

        ubox.add_widget(utitle)
        ubox.add_widget(self.upgrades_info)
        ubox.add_widget(self.upgrades_msg)
        ubox.add_widget(btn_max_lives)
        ubox.add_widget(btn_start_bombs)
        ubox.add_widget(btn_discount)
        ubox.add_widget(btn_start_med)
        ubox.add_widget(btn_start_bomb)
        ubox.add_widget(back_upg)
        ubox.add_widget(Label(size_hint_y=1))

        upgrades.add_widget(ubox)
        self.sm.add_widget(upgrades)

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

        with hud.canvas.before:
            Color(0, 0, 0, 0.45)
            self._hud_bg = Rectangle(pos=hud.pos, size=hud.size)

        def _update_hud_bg(*_):
            self._hud_bg.pos = hud.pos
            self._hud_bg.size = hud.size

        hud.bind(pos=_update_hud_bg, size=_update_hud_bg)

        game_widget = GameWidget(self.st)

        controls = BoxLayout(size_hint_y=None, height=120, spacing=6)

        left = Button(text="<")
        right = Button(text=">")
        up = Button(text="^")
        down = Button(text="v")
        bomb_btn = Button(text="Bomb")
        undo_btn = Button(text="Undo")
        pause_btn = Button(text="Pause")

        next_btn = Button(text="Next")
        restart_btn = Button(text="Restart")

        left.bind(on_release=lambda *_: game_widget.step(-1, 0))
        right.bind(on_release=lambda *_: game_widget.step(1, 0))
        up.bind(on_release=lambda *_: game_widget.step(0, 1))
        down.bind(on_release=lambda *_: game_widget.step(0, -1))
        bomb_btn.bind(on_release=lambda *_: game_widget.use_bomb())
        undo_btn.bind(on_release=lambda *_: self.perform_undo(game_widget))
        pause_btn.bind(on_release=lambda *_: self.show_pause_dialog())

        def on_next(_btn):
            if self.st.message and self.st.lives > 0:
                self.st.level += 1
                self.st.load_level()
                self.apply_upgrades_to_state()
                self.apply_start_items(new_level=True)
                self.biome = get_biome_for_level(self.st.level)
                self.reset_undo_for_level()
                self.save_progress()
                game_widget.redraw()

        def on_restart(_btn):
            self.st.restart()
            self.apply_upgrades_to_state()
            self.apply_start_items(new_level=True)
            self.biome = get_biome_for_level(self.st.level)
            self.reset_undo_for_level()
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
        controls.add_widget(undo_btn)
        controls.add_widget(pause_btn)
        controls.add_widget(next_btn)
        controls.add_widget(restart_btn)

        root.add_widget(hud)
        root.add_widget(game_widget)
        root.add_widget(controls)

        game_widget.redraw()
        return root, hud, game_widget

    # --- окна: пауза и game over ---

    def show_pause_dialog(self) -> None:
        if self.paused:
            return
        self.paused = True

        content = BoxLayout(orientation="vertical", padding=20, spacing=15)
        title_lbl = Label(text="Пауза", font_size="22sp",
                          size_hint_y=None, height=40)
        info_lbl = Label(text="Игра на паузе", font_size="16sp",
                         size_hint_y=None, height=30)

        btn_box = BoxLayout(orientation="horizontal", spacing=10,
                            size_hint_y=None, height=50)
        btn_resume = Button(text="Продолжить")
        btn_menu = Button(text="В меню")

        btn_box.add_widget(btn_resume)
        btn_box.add_widget(btn_menu)

        content.add_widget(title_lbl)
        content.add_widget(info_lbl)
        content.add_widget(btn_box)

        popup = Popup(
            title="Пауза",
            content=content,
            size_hint=(0.8, 0.4),
            auto_dismiss=False,
        )

        def do_resume(_btn):
            self.paused = False
            popup.dismiss()

        def do_menu(_btn):
            self.paused = False
            popup.dismiss()
            self.go_menu()

        btn_resume.bind(on_release=do_resume)
        btn_menu.bind(on_release=do_menu)
        popup.open()

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
            self.apply_upgrades_to_state()
            self.apply_start_items(new_level=True)
            self.biome = get_biome_for_level(self.st.level)
            self.reset_undo_for_level()
            self.save_progress()
            self.game.redraw()
            popup.dismiss()
            self.sm.current = "game"

        def do_menu(_btn):
            self.game_over_active = False
            popup.dismiss()
            self.go_menu()

        btn_restart.bind(on_release=do_restart)
        btn_menu.bind(on_release=do_menu)

        popup.open()

    # --- навигация ---

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

    def go_upgrades(self, *_):
        if hasattr(self, "update_upgrades_info"):
            self.update_upgrades_info()
        self.sm.current = "upgrades"

    # --- вспомогательное ---

    def _update_shop_button_text(self):
        base_price = 30
        discount = int(self.upgrades.get("shop_discount", 0))
        eff_price = max(1, int(base_price * (100 - discount) / 100))
        if hasattr(self, "shop_buy_btn"):
            self.shop_buy_btn.text = (
                f"Купить бомбу ({eff_price} очков, скидка {discount}%)"
            )

    # --- сохранение / HUD ---

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
            disc = int(self.upgrades.get("shop_discount", 0))
            self.shop_info.text = (
                f"Бомбы: {self.st.bombs}   Очки: {self.st.score}   "
                f"Скидка: {disc}%"
            )
        self._update_shop_button_text()

    def flash_message(self, text: str, duration: float = 1.2) -> None:
        self.st.message = text

        def clear(_dt):
            if self.st.message == text:
                self.st.message = None

        Clock.schedule_once(clear, duration)

    def save_settings_and_meta(self) -> None:
        self.save_settings()
        self.save_meta()

    def _update_hud(self, _dt):
        from kivy.clock import Clock as KClock
        left = len(self.st.treasures) if self.st.treasures is not None else 0
        msg = self.st.message or ""
        biome_name = getattr(getattr(self, "biome", None), "name", "")
        dx = self.st.goal[0] - self.st.player[0]
        dy = self.st.goal[1] - self.st.player[1]
        if abs(dx) > abs(dy):
            arrow = "→" if dx > 0 else "←"
        else:
            arrow = "↑" if dy > 0 else "↓"

        base = (
            f"Уровень: {self.st.level}   Биом: {biome_name}   "
            f"Направление к порталу: {arrow}   "
            f"Жизни: {self.st.lives}/{self.st.max_lives}   "
            f"Очки: {self.st.score}   Бомбы: {self.st.bombs}   "
            f"Кристаллы: {self.crystals}   Осталось T: {left}   {msg}"
        )

        if self.debug_overlay:
            fps = int(KClock.get_fps())
            dbg = f"  [DBG fps={fps} enemies={len(self.st.enemies)}]"
            text = base + dbg
        else:
            text = base

        if hasattr(self, "hud"):
            self.hud.text = text

        self._update_shop_labels()

    def save_meta(self) -> None:
        if hasattr(self, "store"):
            self.store.put(
                "meta",
                crystals=int(self.crystals),
                upgrades=self.upgrades,
            )


if __name__ == "__main__":
    MyGameApp().run()