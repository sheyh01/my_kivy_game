import os
import random
from typing import List

from game.logic import Pos, neighbors4, in_bounds, bfs_distances
from game.state import GameState, get_biome_for_level
from game.widget import GameWidget

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.audio import SoundLoader
from kivy.resources import resource_find
from kivy.storage.jsonstore import JsonStore
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.popup import Popup
from kivy.uix.togglebutton import ToggleButton
from kivy.core.window import Window
from kivy.core.text import LabelBase
from game.ui_style import Theme, style_button, style_panel, apply_screen_bg, attach_icon

class MyGameApp(App):

    def request_save_progress(self) -> None:
        # сохраняем не чаще, чем раз в ~0.6 сек
        if self._save_progress_ev is not None:
            return
        self._save_progress_ev = Clock.schedule_once(lambda _dt: self._flush_save_progress(), 0.6)

    def _flush_save_progress(self) -> None:
        self._save_progress_ev = None
        self.save_progress()

    def _tick(self, dt: float) -> None:
        # не тратим CPU в меню/настройках/магазине
        if self.sm.current != "game":
            return
        if self.paused or self.game_over_active:
            return
        self.game.animate(dt)

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
        self.theme = Theme()
        LabelBase.register(
            name="symbols",
            fn_regular=resource_find(
                "assets/fonts/NotoSansSymbols2-Regular.ttf") or "assets/fonts/NotoSansSymbols2-Regular.ttf",
        )

        self.st = GameState()
        self.game_over_active = False
        self.paused = False

        import os
        self.store = JsonStore(os.path.join(self.user_data_dir, "save.json"))
        self.music_enabled = True
        self.sounds_enabled = True

        # метапрогрессия
        self._save_progress_ev = None
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

        #theme
        self.theme = Theme()

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
        Clock.schedule_interval(self._tick, 1 / 30.0)

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
        apply_screen_bg(menu, self.theme)
        mbox = BoxLayout(orientation="vertical", padding=20, spacing=15)
        style_panel(mbox, self.theme, strong=True)
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
        style_button(btn_play, self.theme, "primary")
        style_button(btn_settings, self.theme, "ghost")
        style_button(btn_how, self.theme, "ghost")
        style_button(btn_shop, self.theme, "ghost")
        style_button(btn_upgrades, self.theme, "ghost")
        style_button(btn_exit, self.theme, "danger")

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
        apply_screen_bg(settings, self.theme)
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
        style_button(back1, self.theme, "ghost", small=True)
        sbox.add_widget(Label())
        settings.add_widget(sbox)
        self.sm.add_widget(settings)

        # --- HOW TO ---
        how = Screen(name="howto")
        apply_screen_bg(how, self.theme)
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
        apply_screen_bg(shop, self.theme)
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
                self.request_save_progress()
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
        apply_screen_bg(upgrades, self.theme)
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
        from kivy.metrics import dp
        from kivy.core.window import Window
        from kivy.uix.widget import Widget as Spacer

        root = BoxLayout(orientation="vertical", spacing=6, padding=6)

        hud = Label(
            text="",
            size_hint_y=None,
            height=self.theme.hud_h,
            halign="left",
            valign="middle",
        )
        hud.bind(size=lambda *_: setattr(hud, "text_size", hud.size))
        style_panel(hud, self.theme, strong=True)

        game_widget = GameWidget(self.st)

        # --- авто-размеры под экран ---
        min_side = min(Window.width, Window.height)
        scale = max(0.9, min(1.2, min_side / 720.0))

        dpad_btn = dp(58) * scale
        action_btn = dp(64) * scale
        big_btn_w = dp(120) * scale
        controls_h = dp(118) * scale
        gap = dp(8) * scale

        controls = BoxLayout(size_hint_y=None, height=controls_h, spacing=gap, padding=(gap, gap))
        style_panel(controls, self.theme, strong=True)

        # --- кнопки ---
        left = Button(text="<")
        right = Button(text=">")
        up = Button(text="^")
        down = Button(text="v")

        bomb_btn = Button(text="")
        undo_btn = Button(text="")
        pause_btn = Button(text="")
        next_btn = Button(text="")

        restart_btn = Button(text="")

        # --- размеры D-pad ---
        for b in (left, right, up, down):
            b.size_hint = (None, None)
            b.size = (dpad_btn, dpad_btn)
            b.font_size = str(dp(22) * scale)
            style_button(b, self.theme, "ghost")

        # --- размеры иконок ---
        for b in (undo_btn, pause_btn, restart_btn):
            b.size_hint = (None, None)
            b.size = (action_btn, action_btn)
            style_button(b, self.theme, "ghost")

        # restart сделаем "danger"
        style_button(restart_btn, self.theme, "danger")

        # bomb/next как крупные кнопки
        bomb_btn.size_hint = (None, None)
        bomb_btn.size = (action_btn, action_btn)  # можно big_btn_w, если хочешь шире
        style_button(bomb_btn, self.theme, "primary")

        next_btn.size_hint = (None, None)
        next_btn.size = (big_btn_w, action_btn)
        next_btn.text = "Next"
        style_button(next_btn, self.theme, "primary")

        # --- иконки PNG ---
        attach_icon(undo_btn, "assets/icons/undo.png", size_ratio=0.62)
        attach_icon(pause_btn, "assets/icons/pause.png", size_ratio=0.62)
        attach_icon(restart_btn, "assets/icons/restart.png", size_ratio=0.62)
        # если есть иконка бомбы:
        attach_icon(bomb_btn, "assets/icons/bomb.png", size_ratio=0.62)

        # --- обработчики ---
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
                self.request_save_progress()
                game_widget.redraw()

        def on_restart(_btn):
            self.st.restart()
            self.apply_upgrades_to_state()
            self.apply_start_items(new_level=True)
            self.biome = get_biome_for_level(self.st.level)
            self.reset_undo_for_level()
            self.request_save_progress()
            game_widget.redraw()

        next_btn.bind(on_release=on_next)
        restart_btn.bind(on_release=on_restart)

        # --- собираем D-pad красиво крестом ---
        up_row = BoxLayout(orientation="horizontal", spacing=gap, size_hint=(None, None))
        up_row.size = (dpad_btn * 3 + gap * 2, dpad_btn)
        up_row.add_widget(Spacer(size_hint=(None, None), size=(dpad_btn, dpad_btn)))
        up_row.add_widget(up)
        up_row.add_widget(Spacer(size_hint=(None, None), size=(dpad_btn, dpad_btn)))

        mid_row = BoxLayout(orientation="horizontal", spacing=gap, size_hint=(None, None))
        mid_row.size = (dpad_btn * 3 + gap * 2, dpad_btn)
        mid_row.add_widget(left)
        mid_row.add_widget(down)
        mid_row.add_widget(right)

        dpad_col = BoxLayout(orientation="vertical", spacing=gap, size_hint=(None, None))
        dpad_col.size = (dpad_btn * 3 + gap * 2, dpad_btn * 2 + gap)
        dpad_col.add_widget(up_row)
        dpad_col.add_widget(mid_row)

        # --- компоновка нижней панели ---
        controls.add_widget(dpad_col)
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

    def on_stop(self) -> None:
        # гарантированно пишем на диск при закрытии
        self.save_progress()
        self.save_settings()
        self.save_meta()


if __name__ == "__main__":
    MyGameApp().run()