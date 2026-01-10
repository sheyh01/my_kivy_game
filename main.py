import random
from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

import pygame

Pos = Tuple[int, int]  # (x, y)


# ---------------------------
# Логика: поле, пути, уровни
# ---------------------------

def in_bounds(x: int, y: int, w: int, h: int) -> bool:
    return 0 <= x < w and 0 <= y < h


def neighbors4(p: Pos) -> List[Pos]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def bfs_prev_map(walls: List[List[str]], start: Pos) -> Dict[Pos, Optional[Pos]]:
    """BFS по проходимым клеткам (не '#'). Возвращает prev-карту для восстановления путей."""
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
    enemy_steps: int  # 1..2


def level_config(level: int) -> LevelConfig:
    # Размеры ограничены, чтобы хорошо умещаться на большинстве экранов
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
    """Генерация уровня: стены + гарантируем достижимость выхода."""
    start = (1, 1)
    goal = (cfg.w - 2, cfg.h - 2)

    attempts = 0
    while True:
        attempts += 1
        if attempts > 300:
            raise RuntimeError("Не удалось сгенерировать уровень. Попробуй уменьшить wall_prob.")

        walls = [["." for _ in range(cfg.w)] for _ in range(cfg.h)]

        # Рамка
        for x in range(cfg.w):
            walls[0][x] = "#"
            walls[cfg.h - 1][x] = "#"
        for y in range(cfg.h):
            walls[y][0] = "#"
            walls[y][cfg.w - 1] = "#"

        # Случайные стены
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
# Pygame: отрисовка и цикл
# ---------------------------

@dataclass
class GameState:
    level: int = 1
    score: int = 0
    lives: int = 3
    max_lives: int = 3

    walls: List[List[str]] = None  # type: ignore[assignment]
    start: Pos = (1, 1)
    goal: Pos = (1, 1)
    player: Pos = (1, 1)
    treasures: Set[Pos] = None  # type: ignore[assignment]
    medkits: Set[Pos] = None  # type: ignore[assignment]
    enemies: List[Pos] = None  # type: ignore[assignment]
    cfg: LevelConfig = None  # type: ignore[assignment]

    message: Optional[str] = None
    message_hint: Optional[str] = None

    def load_level(self) -> None:
        self.cfg = level_config(self.level)
        self.walls, self.start, self.goal, self.treasures, self.medkits, self.enemies = generate_level(self.cfg)
        self.player = self.start
        self.message = None
        self.message_hint = None


@dataclass
class Layout:
    tile: int
    hud_h: int
    grid_x: int
    grid_y: int
    font: pygame.font.Font
    small: pygame.font.Font


# Цвета
COL_BG = (18, 18, 22)
COL_FLOOR = (40, 40, 48)
COL_WALL = (20, 20, 26)

COL_PLAYER = (80, 170, 255)
COL_ENEMY = (235, 70, 70)
COL_TREASURE = (245, 200, 70)
COL_MEDKIT = (90, 220, 120)
COL_GOAL = (180, 110, 255)

COL_TEXT = (235, 235, 245)
COL_DIM = (170, 170, 185)


def compute_layout(screen: pygame.Surface, st: GameState) -> Layout:
    sw, sh = screen.get_size()
    w, h = st.cfg.w, st.cfg.h

    # HUD высота: зависит от экрана, но в разумных пределах
    hud_h = max(76, min(140, sh // 8))

    # Размер клетки так, чтобы поле влезло по ширине и высоте (с учётом HUD)
    avail_h = max(1, sh - hud_h - 10)
    tile = min(sw // w, avail_h // h)
    tile = max(14, tile)  # не даём стать совсем мелким

    grid_w_px = tile * w
    grid_h_px = tile * h

    grid_x = (sw - grid_w_px) // 2
    grid_y = hud_h + (avail_h - grid_h_px) // 2

    # Шрифты масштабируем от tile
    font_size = max(22, int(tile * 0.85))
    small_size = max(16, int(tile * 0.55))
    font = pygame.font.SysFont(None, font_size)
    small = pygame.font.SysFont(None, small_size)

    return Layout(tile=tile, hud_h=hud_h, grid_x=grid_x, grid_y=grid_y, font=font, small=small)


def draw_game(screen: pygame.Surface, st: GameState, lay: Layout) -> None:
    screen.fill(COL_BG)

    h = len(st.walls)
    w = len(st.walls[0]) if h else 0

    # Поле
    for y in range(h):
        for x in range(w):
            r = pygame.Rect(lay.grid_x + x * lay.tile, lay.grid_y + y * lay.tile, lay.tile, lay.tile)
            if st.walls[y][x] == "#":
                pygame.draw.rect(screen, COL_WALL, r)
            else:
                pygame.draw.rect(screen, COL_FLOOR, r)

    def draw_cell(p: Pos, color: Tuple[int, int, int], inset_ratio: float) -> None:
        x, y = p
        inset = max(2, int(lay.tile * inset_ratio))
        r = pygame.Rect(
            lay.grid_x + x * lay.tile + inset,
            lay.grid_y + y * lay.tile + inset,
            lay.tile - 2 * inset,
            lay.tile - 2 * inset,
        )
        pygame.draw.rect(screen, color, r, border_radius=max(4, lay.tile // 6))

    for t in st.treasures:
        draw_cell(t, COL_TREASURE, inset_ratio=0.28)

    for m in st.medkits:
        draw_cell(m, COL_MEDKIT, inset_ratio=0.28)

    draw_cell(st.goal, COL_GOAL, inset_ratio=0.28)

    for e in st.enemies:
        draw_cell(e, COL_ENEMY, inset_ratio=0.20)

    draw_cell(st.player, COL_PLAYER, inset_ratio=0.16)

    # HUD
    left = len(st.treasures)
    hud1 = f"Уровень: {st.level}   Жизни: {st.lives}/{st.max_lives}   Очки: {st.score}   Осталось T: {left}"
    hud2 = "Ход: WASD/стрелки. F11 — окно/полный экран. Esc — выход. Собери все T и иди на G."

    text1 = lay.font.render(hud1, True, COL_TEXT)
    text2 = lay.small.render(hud2, True, COL_DIM)
    screen.blit(text1, (12, 10))
    screen.blit(text2, (12, 10 + text1.get_height() + 6))

    # Сообщения
    if st.message:
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))

        msg = lay.font.render(st.message, True, COL_TEXT)
        hint = lay.small.render(st.message_hint or "Нажми Enter", True, COL_DIM)

        mx = (screen.get_width() - msg.get_width()) // 2
        my = (screen.get_height() - msg.get_height()) // 2 - 10
        hx = (screen.get_width() - hint.get_width()) // 2
        hy = my + msg.get_height() + 12

        screen.blit(msg, (mx, my))
        screen.blit(hint, (hx, hy))


def handle_player_step(st: GameState, dx: int, dy: int) -> None:
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

    # победа на уровне (только если все сокровища собраны)
    if st.player == st.goal and len(st.treasures) == 0:
        st.score += 50 + st.level * 10
        st.message = "Уровень пройден!"
        st.message_hint = "Нажми Enter для следующего уровня"
        return

    st.enemies = enemy_turn(st.walls, st.enemies, st.player, st.cfg.enemy_steps)

    if st.player in set(st.enemies):
        st.lives -= 1
        st.score = max(0, st.score - 15)
        st.player = st.start

        if st.lives <= 0:
            st.message = "Игра окончена"
            st.message_hint = f"Enter — заново (счёт: {st.score}, уровень: {st.level})"


def get_desktop_size() -> Tuple[int, int]:
    # pygame 2.x: самый надёжный способ
    try:
        sizes = pygame.display.get_desktop_sizes()
        if sizes:
            return sizes[0]
    except Exception:
        pass

    # запасной вариант: список поддерживаемых режимов
    try:
        modes = pygame.display.list_modes()
        if modes and modes != -1:
            return modes[0]
    except Exception:
        pass

    # ещё один запасной вариант
    info = pygame.display.Info()
    if getattr(info, "current_w", 0) and getattr(info, "current_h", 0):
        return (info.current_w, info.current_h)

    # совсем запасной вариант
    return (1280, 720)


def create_screen(fullscreen: bool) -> pygame.Surface:
    flags = pygame.DOUBLEBUF
    if fullscreen:
        info = pygame.display.Info()
        size = (info.current_w, info.current_h)
        screen = pygame.display.set_mode(size, flags | pygame.FULLSCREEN)
    else:
        # фиксированное окно (без RESIZABLE, чтобы не зависеть от resize-событий)
        screen = pygame.display.set_mode((1100, 720), flags)
    pygame.event.clear()
    return screen


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Мини-приключение (pygame)")

    random.seed()

    st = GameState()
    st.load_level()

    fullscreen = True
    screen = create_screen(fullscreen)
    pygame.mouse.set_visible(False)

    clock = pygame.time.Clock()

    # нужно, чтобы "нажатие один раз" работало корректно
    pygame.event.pump()
    prev_keys = pygame.key.get_pressed()

    running = True
    while running:
        clock.tick(60)

        # обновляет внутреннее состояние клавиатуры/окна без создания Event-объектов
        pygame.event.pump()
        keys = pygame.key.get_pressed()

        def edge(k: int) -> bool:
            return bool(keys[k] and not prev_keys[k])

        # Выход по Esc (в fullscreen крестика нет, поэтому так удобнее)
        if edge(pygame.K_ESCAPE):
            running = False

        # Переключение экран/окно
        if edge(pygame.K_F11):
            fullscreen = not fullscreen
            screen = create_screen(fullscreen)
            pygame.event.pump()
            keys = pygame.key.get_pressed()  # обновим после смены режима
            prev_keys = keys

        # Управление сообщениями (победа/поражение)
        if st.message:
            if edge(pygame.K_RETURN) or edge(pygame.K_KP_ENTER):
                if st.lives <= 0:
                    st.level = 1
                    st.score = 0
                    st.lives = st.max_lives
                    st.load_level()
                else:
                    st.level += 1
                    st.load_level()

        else:
            # Ход по одному шагу на нажатие
            if edge(pygame.K_w) or edge(pygame.K_UP):
                handle_player_step(st, 0, -1)
            elif edge(pygame.K_s) or edge(pygame.K_DOWN):
                handle_player_step(st, 0, 1)
            elif edge(pygame.K_a) or edge(pygame.K_LEFT):
                handle_player_step(st, -1, 0)
            elif edge(pygame.K_d) or edge(pygame.K_RIGHT):
                handle_player_step(st, 1, 0)

        # рисуем
        lay = compute_layout(screen, st)
        draw_game(screen, st, lay)
        pygame.display.flip()

        prev_keys = keys

    pygame.quit()


if __name__ == "__main__":
    main()