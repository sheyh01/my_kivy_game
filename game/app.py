# game/app.py
import os
import math
import random
from typing import List, Optional

from game.logic import Pos, neighbors4, in_bounds, bfs_distances
from game.state import GameState, get_biome_for_level
from game.widget import GameWidget
from game.ui_style import Theme, style_button, style_panel, apply_screen_bg, attach_icon_fancy

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.resources import resource_find
from kivy.storage.jsonstore import JsonStore
from kivy.core.text import LabelBase

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.togglebutton import ToggleButton
from kivy.core.window import Window
from kivy.metrics import dp, sp

def get_scale():
    min_side = min(Window.width, Window.height)
    return max(1.0, min(1.5, min_side / 700.0))
from kivy.utils import platform

def get_safe_bottom_px() -> float:
    """
    Примерная safe-area снизу (в dp), чтобы кнопки не уезжали под жестовую панель Android.
    На iOS без pyobjus точно определить сложно, поэтому даём небольшой запас.
    """
    p = platform  # 'android', 'ios', 'win', ...
    if p == "android":
        return dp(22)   # обычно хватает под жестовую панель
    if p == "ios":
        return dp(28)   # запас под home indicator
    return dp(0)

class MyGameApp(App):

    def on_resume(self):
        print("▶️ App resumed from background")

        # Попробуем пересоздать отрисовку
        if hasattr(self, "game") and self.game:
            try:
                self.game.redraw()
                print("🔁 GameWidget redrawn!")
            except Exception as e:
                print(f"❌ Redraw error: {e}")
    # ----------------------------
    # Enemy teleport helper
    # ----------------------------
    def teleport_enemy_far(self, st: GameState, hit_pos: Pos) -> None:
        """Телепортирует врага(ов), стоявших в hit_pos, на далёкую от игрока клетку."""
        if not st.walls or not st.cfg:
            return

        dist = bfs_distances(st.walls, st.player)
        if not dist:
            return

        h = len(st.walls)
        w = len(st.walls[0]) if h else 0

        min_safe = max(6, (w + h) // 4)
        occupied = set(st.enemies)

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

        for i, e in enumerate(st.enemies):
            if e == hit_pos:
                occupied.discard(e)
                for c in candidates:
                    if c not in occupied:
                        st.enemies[i] = c
                        occupied.add(c)
                        break

    # ----------------------------
    # App lifecycle
    # ----------------------------
    def _restart_game(self, game_widget):
        self.st.restart()
        self.apply_upgrades_to_state()
        self.apply_start_items(new_level=True)
        self.biome = get_biome_for_level(self.st.level)
        self.reset_undo_for_level()
        self.save_progress()
        game_widget.redraw()

    def _next_level(self, game_widget):
        self.st.level += 1
        self.st.load_level()
        self.apply_upgrades_to_state()
        self.apply_start_items(new_level=True)
        self.biome = get_biome_for_level(self.st.level)
        self.reset_undo_for_level()
        self.save_progress()
        game_widget.redraw()

    def build(self):
        random.seed()
        self.theme = Theme()
        LabelBase.register(
            name="ui",
            fn_regular=resource_find("data/fonts/DejaVuSans.ttf"),
        )

        self.st = GameState()
        self.game_over_active = False
        self.paused = False

        # save storage
        self.store = JsonStore(os.path.join(self.user_data_dir, "save.json"))

        # audio settings
        self.music_enabled = True
        self.sounds_enabled = True
        self.music_volume = 0.7  # 0..1
        self.sounds_volume = 0.8  # 0..1

        # meta progression
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

        # debounced save
        self._save_progress_ev = None

        # debug overlay toggle (F2)
        self.debug_overlay = False
        Window.bind(on_key_down=self._on_key_down_global)

        # load settings
        if self.store.exists("settings"):
            sdata = self.store.get("settings")
            self.music_enabled = bool(sdata.get("music_enabled", True))
            self.sounds_enabled = bool(sdata.get("sounds_enabled", True))
            self.music_volume = float(sdata.get("music_volume", self.music_volume))
            self.sounds_volume = float(sdata.get("sounds_volume", self.sounds_volume))

        # load progress
        if self.store.exists("progress"):
            data = self.store.get("progress")
            self.st.score = int(data.get("score", 0))
            self.st.bombs = int(data.get("bombs", 0))
            self.st.level = max(1, int(data.get("level", 1)))

        # load meta
        if self.store.exists("meta"):
            m = self.store.get("meta")
            self.crystals = int(m.get("crystals", 0))
            up = m.get("upgrades", {})
            self.upgrades["max_lives"] = int(up.get("max_lives", 0))
            self.upgrades["start_bombs"] = int(up.get("start_bombs", 0))
            self.upgrades["shop_discount"] = int(up.get("shop_discount", 0))
            self.upgrades["start_medkit_chance"] = float(up.get("start_medkit_chance", 0.0))
            self.upgrades["start_bomb_chance"] = float(up.get("start_bomb_chance", 0.0))

        # build initial level
        self.st.load_level()
        self.apply_upgrades_to_state()
        self.apply_start_items(new_level=True)
        self.biome = get_biome_for_level(self.st.level)

        # textures
        self.player_tex = self._load_texture("assets/player.png")
        self.skeleton_tex = self._load_texture("assets/skeleton.png")
        self.explosion_frames = self._load_explosion_frames("assets/explosion_", 8)

        # sounds
        self.snd_pickup = self._load_sound("assets/snd_pickup.mp3")
        self.snd_hit = self._load_sound("assets/snd_hit.mp3")
        self.snd_explosion = self._load_sound("assets/snd_explosion.wav")

        # music
        self.music_sound = self._load_sound("assets/music.mp3")
        if self.music_sound:
            self.music_sound.volume = float(self.music_volume)

        for s in (self.snd_pickup, self.snd_hit, self.snd_explosion):
            if s:
                s.volume = float(self.sounds_volume)
        self.set_music_enabled(self.music_enabled)

        # screens
        self.sm = ScreenManager(transition=FadeTransition())
        self._build_screens()

        # timers
        Clock.schedule_interval(self._update_hud, 0.10)
        Clock.schedule_interval(self._tick, 1 / 30.0)

        return self.sm

    def on_stop(self) -> None:
        # гарантированно записываем всё при выходе
        self.save_progress()
        self.save_settings()
        self.save_meta()

    # ----------------------------
    # Tick only when in game screen
    # ----------------------------
    def _tick(self, dt: float) -> None:
        if self.sm.current != "game":
            return
        if self.paused or self.game_over_active:
            return
        self.game.animate(dt)

    def _on_key_down_global(self, window, key, scancode, codepoint, modifiers):
        if key == 293:  # F2
            self.debug_overlay = not self.debug_overlay
            return True
        return False

    # ----------------------------
    # Undo
    # ----------------------------
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

    # ----------------------------
    # Upgrades / meta
    # ----------------------------
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

    # ----------------------------
    # Debounced save progress
    # ----------------------------
    def request_save_progress(self) -> None:
        if self._save_progress_ev is not None:
            return
        self._save_progress_ev = Clock.schedule_once(lambda _dt: self._flush_save_progress(), 0.6)

    def _flush_save_progress(self) -> None:
        self._save_progress_ev = None
        self.save_progress()

    # ----------------------------
    # Resource loading
    # ----------------------------
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
            return SoundLoader.load(real)
        except Exception:
            return None

    # ----------------------------
    # Music / sound
    # ----------------------------
    def start_music(self) -> None:
        if not self.music_sound:
            return
        try:
            self.music_sound.loop = True
        except Exception:
            pass
        try:
            self.music_sound.volume = float(self.music_volume)
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

    def set_music_volume(self, value: float) -> None:
        self.music_volume = max(0.0, min(1.0, float(value)))
        if self.music_sound:
            try:
                self.music_sound.volume = self.music_volume
            except Exception:
                pass
        self.save_settings()

    def set_sounds_volume(self, value: float) -> None:
        self.sounds_volume = max(0.0, min(1.0, float(value)))
        # применим к уже загруженным звукам (не обязательно, но полезно)
        for s in (getattr(self, "snd_pickup", None),
                  getattr(self, "snd_hit", None),
                  getattr(self, "snd_explosion", None)):
            if s:
                try:
                    s.volume = self.sounds_volume
                except Exception:
                    pass
        self.save_settings()

    # ----------------------------
    # Screens
    # ----------------------------
    def _build_screens(self) -> None:
        scale = get_scale()
        # --- SPLASH ---
        splash = Screen(name="splash")
        apply_screen_bg(splash, self.theme)

        box = BoxLayout(orientation="vertical", padding=40, spacing=18)
        style_panel(box, self.theme, strong=True)

        title = Label(text="Искатель сокровищ", font_size="32sp")
        subtitle = Label(text="Загрузка...", font_size="18sp", color=self.theme.text_dim)

        box.add_widget(Label())
        box.add_widget(title)
        box.add_widget(subtitle)
        box.add_widget(Label())

        splash.add_widget(box)
        self.sm.add_widget(splash)

        # --- MENU ---
        menu = Screen(name="menu")
        apply_screen_bg(menu, self.theme)

        from kivy.uix.scrollview import ScrollView

        # --- MENU ---
        menu = Screen(name="menu")
        apply_screen_bg(menu, self.theme)

        scale = get_scale()

        root = FloatLayout()

        sv = ScrollView(
            size_hint=(1, 1),
            bar_width=dp(6) * scale,
            do_scroll_x=False
        )

        mbox = BoxLayout(
            orientation="vertical",
            padding=dp(16) * scale,
            spacing=dp(12) * scale,
            size_hint=(1, None)
        )
        mbox.bind(minimum_height=mbox.setter("height"))
        style_panel(mbox, self.theme, strong=True)

        mtitle = Label(
            text="Искатель сокровищ",
            font_size=sp(26) * scale,
            size_hint_y=None,
            height=dp(56) * scale,
            bold=True,
            halign="center",
            valign="middle"
        )
        mtitle.bind(size=lambda l, *_: setattr(l, "text_size", l.size))

        def make_btn(text, callback, kind="ghost"):
            btn = Button(
                text=text,
                size_hint_y=None,
                height=dp(56) * scale,
                font_size=sp(18) * scale
            )
            style_button(btn, self.theme, kind)
            btn.bind(on_release=callback)
            return btn

        mbox.add_widget(mtitle)
        mbox.add_widget(make_btn("Играть", self.go_game, "primary"))
        mbox.add_widget(make_btn("Настройки", self.go_settings))
        mbox.add_widget(make_btn("Как играть", self.go_howto))
        mbox.add_widget(make_btn("Магазин", self.go_shop))
        mbox.add_widget(make_btn("Улучшения", self.go_upgrades))
        mbox.add_widget(make_btn("Выход", lambda *_: self.stop(), "danger"))

        sv.add_widget(mbox)

        # Центрируем панель и даём нормальные поля
        panel_wrap = BoxLayout(
            padding=[dp(18) * scale, dp(18) * scale, dp(18) * scale, dp(18) * scale]
        )
        panel_wrap.add_widget(sv)

        root.add_widget(panel_wrap)
        menu.add_widget(root)
        self.sm.add_widget(menu)

        # --- GAME ---
        game_screen = Screen(name="game")
        # фон не обязателен (поле рисует фон само), но можно добавить лёгкий:
        # apply_screen_bg(game_screen, self.theme, vignette=False, gradient_steps=6)
        game_root, self.hud, self.game = self._create_game_ui()
        game_screen.add_widget(game_root)
        self.sm.add_widget(game_screen)

        from kivy.uix.scrollview import ScrollView
        from kivy.uix.slider import Slider

        # --- SETTINGS ---
        settings = Screen(name="settings")
        apply_screen_bg(settings, self.theme)

        scale = get_scale()

        root = FloatLayout()

        sv = ScrollView(size_hint=(1, 1), bar_width=dp(6) * scale, do_scroll_x=False)

        sbox = BoxLayout(
            orientation="vertical",
            padding=dp(16) * scale,
            spacing=dp(12) * scale,
            size_hint=(1, None)
        )
        sbox.bind(minimum_height=sbox.setter("height"))
        style_panel(sbox, self.theme, strong=True)

        stitle = Label(
            text="Настройки",
            font_size=sp(24) * scale,
            size_hint_y=None,
            height=dp(50) * scale,
            halign="center",
            valign="middle"
        )
        stitle.bind(size=lambda l, *_: setattr(l, "text_size", l.size))

        def make_row_left(text):
            lbl = Label(
                text=text,
                halign="left",
                valign="middle",
                font_size=sp(16) * scale,
                size_hint_x=0.42
            )
            lbl.bind(size=lambda l, *_: setattr(l, "text_size", l.size))
            return lbl

        def sync_toggle(btn, enabled: bool):
            btn.state = "down" if enabled else "normal"
            btn.text = "Вкл" if enabled else "Выкл"

        def make_toggle_row(title_text, initial, on_toggle):
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52) * scale, spacing=dp(10) * scale)
            row.add_widget(make_row_left(title_text))

            btn = ToggleButton(size_hint_x=0.58, font_size=sp(16) * scale)
            style_button(btn, self.theme, "ghost", small=True)
            sync_toggle(btn, initial)
            btn.bind(on_release=lambda _b: on_toggle(btn))
            row.add_widget(btn)
            return row, btn

        def make_slider_row(title_text, initial, on_change):
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52) * scale, spacing=dp(10) * scale)
            row.add_widget(make_row_left(title_text))

            slider = Slider(min=0.0, max=1.0, value=float(initial), size_hint_x=0.44)
            val_lbl = Label(
                text=f"{int(initial * 100)}%",
                size_hint_x=0.14,
                halign="right",
                valign="middle",
                font_size=sp(14) * scale,
                color=self.theme.text_dim
            )
            val_lbl.bind(size=lambda l, *_: setattr(l, "text_size", l.size))

            def _on_val(_sl, val):
                val = float(val)
                val_lbl.text = f"{int(val * 100)}%"
                on_change(val)

            slider.bind(value=_on_val)
            row.add_widget(slider)
            row.add_widget(val_lbl)
            return row

        # Музыка toggle
        music_row, self.music_toggle = make_toggle_row(
            "Музыка",
            self.music_enabled,
            lambda btn: (sync_toggle(btn, btn.state == "down"), self.set_music_enabled(btn.state == "down"))
        )

        # Громкость музыки
        music_vol_row = make_slider_row("Громк. муз.", self.music_volume, self.set_music_volume)

        # Звуки toggle
        sounds_row, self.sounds_toggle = make_toggle_row(
            "Звуки",
            self.sounds_enabled,
            lambda btn: (sync_toggle(btn, btn.state == "down"), self.set_sounds_enabled(btn.state == "down"))
        )

        # Громкость звуков
        sounds_vol_row = make_slider_row("Громк. зв.", self.sounds_volume, self.set_sounds_volume)

        back_btn = Button(
            text="Назад",
            size_hint_y=None,
            height=dp(54) * scale,
            font_size=sp(16) * scale
        )
        style_button(back_btn, self.theme, "ghost")
        back_btn.bind(on_release=self.go_menu)

        sbox.add_widget(stitle)
        sbox.add_widget(music_row)
        sbox.add_widget(music_vol_row)
        sbox.add_widget(sounds_row)
        sbox.add_widget(sounds_vol_row)
        sbox.add_widget(back_btn)

        sv.add_widget(sbox)

        wrap = BoxLayout(padding=[dp(18) * scale, dp(18) * scale, dp(18) * scale, dp(18) * scale])
        wrap.add_widget(sv)

        root.add_widget(wrap)
        settings.add_widget(root)
        self.sm.add_widget(settings)

        # --- HOW TO ---
        how = Screen(name="howto")
        apply_screen_bg(how, self.theme)

        hbox = BoxLayout(orientation="vertical", padding=20, spacing=10,
                         size_hint=(0.88, 0.86), pos_hint={"center_x": 0.5, "center_y": 0.5})
        style_panel(hbox, self.theme, strong=True)

        htitle = Label(text="Как играть", font_size="26sp", size_hint_y=None, height=44)
        htxt = Label(
            text=("Собирай золотые точки, чтобы получать очки.\n"
                  "Скелеты двигаются к тебе по кратчайшему пути.\n"
                  "Не давай им догнать тебя — потеряешь жизнь.\n"
                  "Собери все сокровища, затем зайди в портал.\n\n"
                  "Управление:\n"
                  " ПК: стрелки.\n"
                  " Телефон: свайпы.\n\n"
                  "Магазин: покупай бомбы за очки.\n"
                  "Улучшения: трать кристаллы на апгрейды."),
            halign="left", valign="top"
        )
        htxt.bind(size=lambda *_: setattr(htxt, "text_size", htxt.size))

        back2 = Button(text="Назад")
        style_button(back2, self.theme, "ghost")
        back2.bind(on_release=self.go_menu)

        hbox.add_widget(htitle)
        hbox.add_widget(htxt)
        hbox.add_widget(back2)

        how.add_widget(hbox)
        self.sm.add_widget(how)

        # --- SHOP ---
        shop = Screen(name="shop")
        apply_screen_bg(shop, self.theme)

        shop_box = BoxLayout(orientation="vertical", padding=20, spacing=10,
                             size_hint=(0.88, 0.86), pos_hint={"center_x": 0.5, "center_y": 0.5})
        style_panel(shop_box, self.theme, strong=True)

        sh_title = Label(text="Магазин", font_size="26sp", size_hint_y=None, height=44)
        self.shop_info = Label(text="", size_hint_y=None, height=40)
        self.shop_msg = Label(text="", font_size="16sp", size_hint_y=None, height=30)

        self.shop_buy_btn = Button(text="")
        style_button(self.shop_buy_btn, self.theme, "primary")

        back3 = Button(text="Назад")
        style_button(back3, self.theme, "ghost")

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

        shop.add_widget(shop_box)
        self.sm.add_widget(shop)
        self._update_shop_button_text()

        # --- UPGRADES ---
        upgrades = Screen(name="upgrades")
        apply_screen_bg(upgrades, self.theme)

        ubox = BoxLayout(orientation="vertical", padding=20, spacing=8,
                         size_hint=(0.88, 0.90), pos_hint={"center_x": 0.5, "center_y": 0.5})
        style_panel(ubox, self.theme, strong=True)

        utitle = Label(text="Улучшения", font_size="26sp", size_hint_y=None, height=44)

        self.upgrades_info = Label(text="", size_hint_y=None, halign="left", valign="top")
        self.upgrades_info.bind(size=lambda lbl, *_: setattr(lbl, "text_size", (lbl.width, None)))

        self.upgrades_msg = Label(text="", font_size="16sp", size_hint_y=None, height=34,
                                  halign="center", valign="middle")

        btn_max_lives = Button()
        btn_start_bombs = Button()
        btn_discount = Button()
        btn_start_med = Button()
        btn_start_bomb = Button()
        back_upg = Button(text="Назад")

        for b in (btn_max_lives, btn_start_bombs, btn_discount, btn_start_med, btn_start_bomb):
            style_button(b, self.theme, "ghost", small=True)
        style_button(back_upg, self.theme, "ghost")

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
            self.upgrades_info.text = (
                f"Кристаллы: {self.crystals}\n"
                f"+макс. жизней: {u['max_lives']}\n"
                f"+старт. бомб: {u['start_bombs']}\n"
                f"Скидка в магазине: {u['shop_discount']}%\n"
                f"Шанс старт. аптечки: {int(u['start_medkit_chance']*100)}%\n"
                f"Шанс старт. бомбы: {int(u['start_bomb_chance']*100)}%"
            )
            # высоту под текст
            self.upgrades_info.height = max(80, self.upgrades_info.texture_size[1] + 6)

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

        upgrades.add_widget(ubox)
        self.sm.add_widget(upgrades)

        # go to menu after splash
        Clock.schedule_once(lambda _dt: self.go_menu(), 1.4)

    # ----------------------------
    # GAME ui (NEW DESIGN)
    # ----------------------------
    def _create_game_ui(self):
        from kivy.metrics import dp, sp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.floatlayout import FloatLayout
        from kivy.uix.button import Button
        from kivy.uix.anchorlayout import AnchorLayout
        from kivy.uix.widget import Widget
        from kivy.core.window import Window
        from game.widget import GameWidget

        scale = get_scale()
        safe_bottom = get_safe_bottom_px()
        root = FloatLayout()

        # ---------- HUD ----------
        hud = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(80) * scale,
            padding=[dp(12) * scale, dp(12) * scale],
            spacing=dp(10) * scale
        )
        style_panel(hud, self.theme, strong=True)

        def mk_label(sz, **kwargs):
            lbl = Label(
                font_size=sp(sz) * scale,
                color=self.theme.text,
                halign=kwargs.get("halign", "left"),
                valign="middle"
            )
            lbl.bind(size=lambda _, __: setattr(lbl, "text_size", lbl.size))
            return lbl

        self.lbl_level = mk_label(16)
        self.lbl_hint = mk_label(14, color=self.theme.text_dim)
        left = BoxLayout(orientation="vertical")
        left.add_widget(self.lbl_level)
        left.add_widget(self.lbl_hint)

        self.lbl_lives = mk_label(18, halign="center")
        self.lbl_msg = mk_label(14, halign="center", color=self.theme.accent)
        center = BoxLayout(orientation="vertical")
        center.add_widget(self.lbl_lives)
        center.add_widget(self.lbl_msg)

        self.lbl_score = mk_label(16, halign="right")
        self.lbl_score.bold = True
        self.lbl_items = mk_label(14, halign="right", color=self.theme.text_dim)
        right = BoxLayout(orientation="vertical")
        right.add_widget(self.lbl_score)
        right.add_widget(self.lbl_items)

        hud.add_widget(left)
        hud.add_widget(center)
        hud.add_widget(right)

        # ---------- GameWidget ----------
        game_widget = GameWidget(self.st)
        game_widget.size_hint = (1, 1)

        # ---------- Main layout (hud + game)
        main_layout = BoxLayout(orientation="vertical", size_hint=(1, 1))
        main_layout.add_widget(hud)
        main_layout.add_widget(game_widget)

        # Учитываем высоту нижней панели
        bottom_bar = dp(72) * scale + (dp(14) * scale + safe_bottom)  # кнопка 72 + отступ
        top_hud = dp(80) * scale

        main_layout.height = Window.height - bottom_bar
        Window.bind(size=lambda *_: setattr(main_layout, "height", Window.height - bottom_bar))

        root.add_widget(main_layout)

        # ---------- NEXT кнопка ----------
        self.next_btn = Button(
            text="Далее",
            size_hint=(None, None),
            size=(dp(260) * scale, dp(62) * scale),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            opacity=0.0,
            disabled=True
        )
        style_button(self.next_btn, self.theme, "primary")
        self.next_btn.bind(on_release=lambda *_: self._next_level(game_widget))
        root.add_widget(self.next_btn)

        # ---------- Нижние кнопки (по краям) ----------
        def make_btn(name, cb):
            btn = Button(size_hint=(None, None), size=(dp(72) * scale, dp(72) * scale))
            style_button(btn, self.theme, "ghost")
            attach_icon_fancy(
                btn,
                icon_path=f"assets/icons/{name}.png",
                icon_bg="assets/ui/circle_glow.png",
                size_ratio=0.85
            )
            btn.bind(on_release=cb)
            return btn

        # Левая группа (бомба + undo)
        bomb_btn = make_btn("bomb", lambda *_: game_widget.use_bomb())
        undo_btn = make_btn("undo", lambda *_: self.perform_undo(game_widget))
        left_box = BoxLayout(orientation="horizontal", spacing=dp(12) * scale, size_hint=(None, None),
                             height=dp(72) * scale)
        left_box.add_widget(bomb_btn)
        left_box.add_widget(undo_btn)
        left_box.width = 2 * dp(72) * scale + dp(12) * scale

        safe_bottom = get_safe_bottom_px()

        left_anchor = AnchorLayout(
            anchor_x="left",
            anchor_y="bottom",
            size_hint=(1, 1),
            padding=[dp(16) * scale, dp(14) * scale + safe_bottom]
        )
        left_anchor.add_widget(left_box)
        root.add_widget(left_anchor)

        # Правая группа (пауза + рестарт)
        pause_btn = make_btn("pause", lambda *_: self.show_pause_dialog())
        restart_btn = make_btn("restart", lambda *_: self._restart_game(game_widget))

        right_box = BoxLayout(orientation="horizontal", spacing=dp(12) * scale, size_hint=(None, None),
                              height=dp(72) * scale)
        right_box.add_widget(pause_btn)
        right_box.add_widget(restart_btn)
        right_box.width = 2 * dp(72) * scale + dp(12) * scale

        right_anchor = AnchorLayout(
            anchor_x="right",
            anchor_y="bottom",
            size_hint=(1, 1),
            padding=[dp(16) * scale, dp(14) * scale + safe_bottom]
        )
        right_anchor.add_widget(right_box)
        root.add_widget(right_anchor)

        return root, hud, game_widget

    # ----------------------------
    # Pause / Game over dialogs
    # ----------------------------
    def show_pause_dialog(self) -> None:
        if self.paused:
            return
        self.paused = True

        content = BoxLayout(orientation="vertical", padding=20, spacing=15)
        style_panel(content, self.theme, strong=True)

        title_lbl = Label(text="Пауза", font_size="22sp", size_hint_y=None, height=40)
        info_lbl = Label(text="Игра на паузе", font_size="16sp", size_hint_y=None, height=30)

        btn_box = BoxLayout(orientation="horizontal", spacing=10, size_hint_y=None, height=54)
        btn_resume = Button(text="Продолжить")
        btn_menu = Button(text="В меню")
        style_button(btn_resume, self.theme, "primary", small=True)
        style_button(btn_menu, self.theme, "ghost", small=True)

        btn_box.add_widget(btn_resume)
        btn_box.add_widget(btn_menu)

        content.add_widget(title_lbl)
        content.add_widget(info_lbl)
        content.add_widget(btn_box)

        popup = Popup(
            title="Пауза",
            content=content,
            size_hint=(0.82, 0.40),
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
        style_panel(content, self.theme, strong=True)

        title_lbl = Label(text="Жизни закончились", font_size="22sp", size_hint_y=None, height=40)
        info_lbl = Label(text="Что делать дальше?", font_size="16sp", size_hint_y=None, height=30)

        btn_box = BoxLayout(orientation="horizontal", spacing=10, size_hint_y=None, height=54)
        btn_restart = Button(text="Рестарт")
        btn_menu = Button(text="В меню")
        style_button(btn_restart, self.theme, "danger", small=True)
        style_button(btn_menu, self.theme, "ghost", small=True)

        btn_box.add_widget(btn_restart)
        btn_box.add_widget(btn_menu)

        content.add_widget(title_lbl)
        content.add_widget(info_lbl)
        content.add_widget(btn_box)

        popup = Popup(
            title="Игра окончена",
            content=content,
            size_hint=(0.82, 0.40),
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

    # ----------------------------
    # Navigation
    # ----------------------------
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

    # ----------------------------
    # Shop helper
    # ----------------------------
    def _update_shop_button_text(self):
        base_price = 30
        discount = int(self.upgrades.get("shop_discount", 0))
        eff_price = max(1, int(base_price * (100 - discount) / 100))
        if hasattr(self, "shop_buy_btn"):
            self.shop_buy_btn.text = f"Купить бомбу ({eff_price} очков, скидка {discount}%)"

    # ----------------------------
    # Save
    # ----------------------------
    def save_progress(self) -> None:
        self.store.put(
            "progress",
            score=int(self.st.score),
            bombs=int(self.st.bombs),
            level=int(self.st.level),
        )

    def save_settings(self) -> None:
        self.store.put(
            "settings",
            music_enabled=bool(self.music_enabled),
            sounds_enabled=bool(self.sounds_enabled),
        )

    def save_meta(self) -> None:
        self.store.put(
            "meta",
            crystals=int(self.crystals),
            upgrades=self.upgrades,
        )

    def _update_shop_labels(self) -> None:
        if hasattr(self, "shop_info"):
            disc = int(self.upgrades.get("shop_discount", 0))
            self.shop_info.text = f"Бомбы: {self.st.bombs}   Очки: {self.st.score}   Скидка: {disc}%"
        self._update_shop_button_text()

    # ----------------------------
    # Flash message
    # ----------------------------
    def flash_message(self, text: str, duration: float = 1.2) -> None:
        self.st.message = text

        def clear(_dt):
            if self.st.message == text:
                self.st.message = None

        Clock.schedule_once(clear, duration)

    # ----------------------------
    # HUD update (NEW)
    # ----------------------------
    def _update_hud(self, _dt):
        left = len(self.st.treasures) if self.st.treasures is not None else 0
        msg = self.st.message or ""
        biome_name = getattr(getattr(self, "biome", None), "name", "")

        dx = self.st.goal[0] - self.st.player[0]
        dy = self.st.goal[1] - self.st.player[1]
        arrow = ""
        if dx != 0 or dy != 0:
            if abs(dx) > abs(dy):
                arrow = "R" if dx > 0 else "L"
            else:
                arrow = "U" if dy > 0 else "D"

        if hasattr(self, "lbl_level"):
            self.lbl_level.text = f"Уровень {self.st.level} • {biome_name}"
        if hasattr(self, "lbl_hint"):
            self.lbl_hint.text = f"Портал: {arrow}   Осталось сокровищ: {left}"
        if hasattr(self, "lbl_lives"):
            self.lbl_lives.text = f"Жизни: {self.st.lives}/{self.st.max_lives}"
        if hasattr(self, "lbl_score"):
            self.lbl_score.text = f"Очки: {self.st.score}"
        if hasattr(self, "lbl_items"):
            tail = f"Бомбы: {self.st.bombs}   Кристаллы: {self.crystals}"
            if self.debug_overlay:
                from kivy.clock import Clock as KClock
                tail += f"   FPS: {int(KClock.get_fps())}"
            self.lbl_items.text = tail
        if hasattr(self, "lbl_msg"):
            self.lbl_msg.text = msg

        # Next button only on win
        if hasattr(self, "next_btn"):
            show_next = bool(self.st.message and "Уровень пройден" in self.st.message)
            self.next_btn.opacity = 1.0 if show_next else 0.0
            self.next_btn.disabled = not show_next

        self._update_shop_labels()