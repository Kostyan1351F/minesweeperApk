import os
import sqlite3
import random
from datetime import datetime

from kivy.config import Config
Config.set('input', 'mouse', 'mouse,disable_multitouch')

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.properties import StringProperty, NumericProperty, BooleanProperty

import sys
import os
import kivy.resources


if getattr(sys, 'frozen', False):
    kivy.resources.resource_add_path(sys._MEIPASS)
    kivy.resources.resource_add_path(os.path.join(sys._MEIPASS, 'pics'))

# ---------------- БД ----------------
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
DB_PATH = os.path.join(DB_DIR, "minesweeper.db")


def db_connect():
    os.makedirs(DB_DIR, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = db_connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            played_at TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            seconds INTEGER NOT NULL,
            result TEXT NOT NULL       -- 'win' или 'lose'
        )
    """)
    conn.commit()
    conn.close()


def save_record(difficulty: str, seconds: int, result: str):
    conn = db_connect()
    conn.execute(
        "INSERT INTO records (played_at, difficulty, seconds, result) "
        "VALUES (?, ?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), difficulty, seconds, result)
    )
    conn.commit()
    conn.close()


def load_best_times():
    conn = db_connect()
    rows = conn.execute("""
        SELECT difficulty, MIN(seconds)
        FROM records
        WHERE result = 'win'
        GROUP BY difficulty
    """).fetchall()
    conn.close()
    return dict(rows)


def load_history(limit: int = 20):
    conn = db_connect()
    rows = conn.execute(
        "SELECT played_at, difficulty, seconds, result FROM records "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def clear_history():
    conn = db_connect()
    conn.execute("DELETE FROM records")
    conn.commit()
    conn.close()


# ---------------- Настройки сложности ----------------
DIFFICULTIES = {
    "Новичок":  {"cols": 9,  "rows": 9,  "mines": 10},
    "Любитель": {"cols": 12, "rows": 12, "mines": 25},
    "Профи":    {"cols": 16, "rows": 16, "mines": 50},
}


# ---------------- Логика поля ----------------
class Cell:
    __slots__ = ("mine", "revealed", "flagged", "neighbors")

    def __init__(self):
        self.mine = False
        self.revealed = False
        self.flagged = False
        self.neighbors = 0


class Board:
    def __init__(self, cols, rows, mines):
        self.cols = cols
        self.rows = rows
        self.mines = mines
        self.grid = [[Cell() for _ in range(cols)] for _ in range(rows)]
        self._place_mines()
        self._count_neighbors()

    def _place_mines(self):
        positions = [(r, c) for r in range(self.rows) for c in range(self.cols)]
        for r, c in random.sample(positions, self.mines):
            self.grid[r][c].mine = True

    def _count_neighbors(self):
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c].mine:
                    continue
                self.grid[r][c].neighbors = sum(
                    1 for nr, nc in self._neighbors(r, c) if self.grid[nr][nc].mine
                )

    def _neighbors(self, r, c):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    yield nr, nc

    def reveal(self, r, c):
        cell = self.grid[r][c]
        if cell.revealed or cell.flagged:
            return None
        if cell.mine:
            cell.revealed = True
            return "mine"
        self._flood_reveal(r, c)
        return "ok"

    def _flood_reveal(self, r, c):
        stack = [(r, c)]
        while stack:
            cr, cc = stack.pop()
            cell = self.grid[cr][cc]
            if cell.revealed or cell.flagged or cell.mine:
                continue
            cell.revealed = True
            if cell.neighbors == 0:
                for nr, nc in self._neighbors(cr, cc):
                    if not self.grid[nr][nc].revealed:
                        stack.append((nr, nc))

    def toggle_flag(self, r, c):
        cell = self.grid[r][c]
        if cell.revealed:
            return
        cell.flagged = not cell.flagged

    def revealed_count(self):
        return sum(1 for row in self.grid for cell in row if cell.revealed)

    def flags_count(self):
        return sum(1 for row in self.grid for cell in row if cell.flagged)

    def is_win(self):
        return all(
            cell.revealed or cell.mine
            for row in self.grid for cell in row
        )


# ---------------- Экраны ----------------
class MenuScreen(Screen):
    difficulty = StringProperty("Новичок")

    def on_kv_post(self, base_widget):
        self.refresh_info()

    def on_pre_enter(self, *args):
        if "best_label" in self.ids:
            self.refresh_info()

    def set_difficulty(self, value):
        self.difficulty = value
        self.refresh_info()

    def refresh_info(self):
        best = load_best_times()
        lines = []
        for diff in DIFFICULTIES:
            sec = best.get(diff)
            lines.append("{}: {}".format(diff, "{} сек".format(sec) if sec else "—"))
        self.ids.best_label.text = "Лучшее время\n" + "\n".join(lines)

        container = self.ids.history_list
        container.clear_widgets()
        rows = load_history(10)
        if not rows:
            container.add_widget(Label(text="История пуста", size_hint_y=None, height=28))
            return
        for played_at, diff, sec, result in rows:
            result_ru = "Победа" if result == "win" else "Проигрыш"
            container.add_widget(Label(
                text="{} | {} | {} сек | {}".format(played_at, diff, sec, result_ru),
                size_hint_y=None, height=26, font_size='13sp'
            ))

    def clear_history(self):
        clear_history()
        self.refresh_info()

    def start_game(self):
        game = self.manager.get_screen("Game")
        game.start_new_game(self.difficulty)
        self.manager.current = "Game"
        self.manager.transition.direction = "left"

    def exit_app(self):
        App.get_running_app().stop()


class GameScreen(Screen):
    difficulty = StringProperty("Новичок")
    status_text = StringProperty("")
    mines_left = NumericProperty(0)
    time_elapsed = NumericProperty(0)

    def start_new_game(self, difficulty):
        self.difficulty = difficulty
        cfg = DIFFICULTIES[difficulty]
        self.board = Board(cfg["cols"], cfg["rows"], cfg["mines"])
        self.mines_left = cfg["mines"]
        self.time_elapsed = 0
        self.finished = False

        self.ids.status_label.text = "ЛКМ — открыть, ПКМ — флажок"
        self._rebuild_grid()
        self._update_counters()

        # таймер
        if hasattr(self, "_timer") and self._timer:
            self._timer.cancel()
        self._timer = Clock.schedule_interval(self._tick, 1)

    def _tick(self, _dt):
        if self.finished:
            return
        self.time_elapsed += 1
        self._update_counters()

    def _update_counters(self):
        self.ids.mines_label.text = "Мин: {}".format(self.mines_left)
        self.ids.time_label.text = "Время: {} сек".format(self.time_elapsed)

    def _rebuild_grid(self):
        grid = self.ids.board_grid
        grid.clear_widgets()
        grid.cols = self.board.cols
        grid.rows = self.board.rows

        for r in range(self.board.rows):
            for c in range(self.board.cols):
                btn = Button(
                    text="",
                    font_size='20sp',
                    background_normal='',
                    background_down='',
                    background_color=(0.6, 0.6, 0.6, 1),
                    on_press=lambda inst, rr=r, cc=c: self.on_cell_left(rr, cc),
                )
                btn.bind(on_touch_down=lambda w, t, rr=r, cc=c: self.on_cell_touch(w, t, rr, cc))
                grid.add_widget(btn)

    def on_cell_touch(self, widget, touch, r, c):
        """Обработка ПКМ (флажок)."""
        if self.finished:
            return False
        if not widget.collide_point(*touch.pos):
            return False
        if touch.button == "right":
            self.on_cell_right(r, c)
            return True
        return False

    def on_cell_left(self, r, c):
        if self.finished:
            return
        result = self.board.reveal(r, c)
        if result == "mine":
            self._lose(r, c)
            return
        self._refresh_cells()
        self._update_counters()
        if self.board.is_win():
            self._win()

    def on_cell_right(self, r, c):
        if self.finished:
            return
        self.board.toggle_flag(r, c)
        self.mines_left = DIFFICULTIES[self.difficulty]["mines"] - self.board.flags_count()
        self._refresh_cells()
        self._update_counters()

    def _refresh_cells(self):
        grid = self.ids.board_grid
        idx = 0
        for r in range(self.board.rows):
            for c in range(self.board.cols):
                cell = self.board.grid[r][c]
                btn = grid.children[grid.children.__len__() - 1 - idx]
                idx += 1

                btn.disabled = False
                btn.color = (1, 1, 1, 1)

                if cell.revealed:
                    btn.background_color = (0.11, 0.11, 0.11, 0.5)
                    if cell.mine:
                        btn.text = "*"
                        btn.background_color = (0.9, 0.3, 0.3, 0.6)
                        btn.color = (1, 1, 1, 1)
                    elif cell.neighbors > 0:
                        btn.text = str(cell.neighbors)
                    else:
                        btn.text = ""
                elif cell.flagged:
                    btn.text = "F"
                    btn.background_color = (1, 0.9, 0.5, 0.7)
                    btn.color = (0, 0, 0, 1)
                else:
                    btn.text = ""
                    btn.background_color = (0.6, 0.6, 0.6, 1)

    def _lose(self, r, c):
        self.finished = True
        self._timer.cancel()
        # показываем все мины
        for rr in range(self.board.rows):
            for cc in range(self.board.cols):
                if self.board.grid[rr][cc].mine:
                    self.board.grid[rr][cc].revealed = True
        self._refresh_cells()
        self.ids.status_label.text = "Проигрыш!"
        save_record(self.difficulty, self.time_elapsed, "lose")

    def _win(self):
        self.finished = True
        self._timer.cancel()
        self.ids.status_label.text = "Победа! Время: {} сек".format(self.time_elapsed)
        save_record(self.difficulty, self.time_elapsed, "win")

    def restart(self):
        self.start_new_game(self.difficulty)

    def back_to_menu(self):
        if hasattr(self, "_timer") and self._timer:
            self._timer.cancel()
        self.manager.current = "Menu"
        self.manager.transition.direction = "right"


class WinMan(ScreenManager):
    pass

class MenuButton(Button):
    pass

class GameControlButton(Button):
    pass

class MinesweeperApp(App):
    def build(self):
        self.title = "Сапёр"
        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "pics", "icon.png"
        )
        if os.path.exists(icon_path):
            self.icon = icon_path
        init_db()
        return WinMan()


if __name__ == '__main__':
    MinesweeperApp().run()