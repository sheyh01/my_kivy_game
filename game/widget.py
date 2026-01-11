import math
import random
from typing import List

from game.logic import Pos, try_move, enemy_turn, neighbors4, in_bounds

from game.theme import (
    COL_BG, COL_FLOOR, COL_WALL,
    COL_PLAYER, COL_ENEMY, COL_TREASURE, COL_MEDKIT, COL_GOAL, COL_GRID
)
from kivy.app import App
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Ellipse, Line
from kivy.uix.widget import Widget

from game.state import GameState


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
        # если игрок шагнул на клетку врага — это должно считаться столкновением сразу
        if st.player in set(st.enemies):
            hit_pos = st.player
            st.lives -= 1
            st.score = max(0, st.score - 15)
            st.player = st.start

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

            app.request_save_progress()
            self.redraw()
            return

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
            app.request_save_progress()
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
                app.request_save_progress()
                if not app.game_over_active:
                    app.game_over_active = True
                    app.show_game_over_dialog()
                return

        app.request_save_progress()
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

        app.request_save_progress()
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
