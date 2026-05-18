"""
Script Editor Module - pygame-texteditor PatchedTextEditor
"""

import copy
import math
import pygame
from pygame_texteditor import TextEditor

SCROLL_LINES = 3
AUTO_SCROLL_MARGIN = 30
AUTO_SCROLL_SPEED = 2
UNDO_MAX = 200


class PatchedTextEditor(TextEditor):
    """pygame-texteditor 全功能适配版"""

    is_running = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.editor_font = pygame.font.SysFont("simsun", self.letter_height)
        except Exception:
            pass
        self.letter_width = self.editor_font.render(" ", 1, (0, 0, 0)).get_width()
        self.line_height_including_margin = self.letter_height + self.line_margin
        self.showable_line_numbers_in_editor = int(
            math.floor(self.editor_height / self.line_height_including_margin)
        )
        self.caret_display_intervals_per_second = 1
        self.FPS = 60
        if self.display_line_numbers:
            self.line_number_width = self.letter_width * 6
            self.line_start_x = self.editor_offset_x + self.line_number_width

        self._undo_stack = []
        self._redo_stack = []
        self._suppress_undo = False

    def _snapshot(self):
        return (
            copy.deepcopy(self.editor_lines),
            self.chosen_line_index,
            self.chosen_letter_index,
            self.first_showable_line_index,
        )

    def _restore_snapshot(self, snap):
        lines, li, ci, fli = snap
        self.editor_lines = copy.deepcopy(lines)
        self.chosen_line_index = max(0, min(li, len(self.editor_lines) - 1))
        self.chosen_letter_index = max(0, min(ci, len(self.editor_lines[self.chosen_line_index])))
        self.first_showable_line_index = max(0, fli)
        self.render_line_numbers_flag = True
        self._update_caret_x()
        self._update_caret_y()

    def _maybe_save_undo(self):
        if self._suppress_undo:
            return
        snap = self._snapshot()
        self._undo_stack.append(snap)
        if len(self._undo_stack) > UNDO_MAX:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        if len(self._undo_stack) > 1:
            self._redo_stack.append(self._snapshot())
            self._undo_stack.pop()
            self._restore_snapshot(self._undo_stack[-1])

    def redo(self):
        if self._redo_stack:
            self._undo_stack.append(self._snapshot())
            self._restore_snapshot(self._redo_stack.pop())

    def _line_pixel_width(self, line_index, upto=None):
        if line_index < 0 or line_index >= len(self.editor_lines):
            return 0
        line = self.editor_lines[line_index]
        if upto is None:
            text = line
        else:
            text = line[:upto]
        if not text:
            return 0
        return self.editor_font.size(text)[0]

    def _update_caret_x(self):
        px = self._line_pixel_width(self.chosen_line_index, self.chosen_letter_index)
        self.caret_x = self.line_start_x + px + 1

    def _update_caret_y(self):
        self.caret_y = self.editor_offset_y + (
            (self.chosen_line_index - self.first_showable_line_index)
            * self.line_height_including_margin
        )

    def update_caret_position(self):
        self._update_caret_x()
        self._update_caret_y()

    def update_caret_position_by_drag_start(self):
        self.caret_x = self.line_start_x + self._line_pixel_width(
            self.drag_chosen_line_index_start, self.drag_chosen_letter_index_start
        )
        self.caret_y = (
            self.editor_offset_y
            + (self.drag_chosen_line_index_start * self.line_height_including_margin)
            - (self.first_showable_line_index * self.letter_height)
        )

    def update_caret_position_by_drag_end(self):
        self.caret_x = self.line_start_x + self._line_pixel_width(
            self.drag_chosen_line_index_end, self.drag_chosen_letter_index_end
        )
        self.caret_y = (
            self.editor_offset_y
            + (self.drag_chosen_line_index_end * self.line_height_including_margin)
            - (self.first_showable_line_index * self.letter_height)
        )

    def get_letter_index(self, mouse_x):
        x = mouse_x - self.line_start_x
        if x <= 0:
            return 0
        line = self.editor_lines[self.chosen_line_index] if self.chosen_line_index < len(self.editor_lines) else ""
        for i in range(len(line)):
            if self.editor_font.size(line[: i + 1])[0] >= x:
                return i
        return len(line)

    def render_highlight(self, mouse_x, mouse_y):
        if not self.dragged_active:
            return
        line_start = self.drag_chosen_line_index_start
        letter_start = self.drag_chosen_letter_index_start

        if self.dragged_finished:
            line_end = self.drag_chosen_line_index_end
            letter_end = self.drag_chosen_letter_index_end
            if letter_end < 0:
                letter_end = 0
            self.highlight_lines(line_start, letter_start, line_end, letter_end)
        else:
            line_end = self.get_line_index(mouse_y)
            if line_end >= self.get_showable_lines():
                line_end = self.get_showable_lines() - 1
            letter_end = self._get_letter_index_for_line(line_end, mouse_x)
            if letter_end < 0:
                letter_end = 0
            elif letter_end > len(self.editor_lines[line_end]):
                letter_end = len(self.editor_lines[line_end])
            self.highlight_lines(line_start, letter_start, line_end, letter_end)

    def get_rect_coord_from_indizes(self, line, letter):
        line_coord = self.editor_offset_y + (
            self.line_height_including_margin * (line - self.first_showable_line_index)
        )
        letter_coord = self.line_start_x + self._line_pixel_width(line, letter)
        return letter_coord, line_coord

    def render_line_contents(self, line_contents):
        y_coordinate = self.line_start_y
        first_line = self.first_showable_line_index
        if self.showable_line_numbers_in_editor < len(self.editor_lines):
            last_line = self.first_showable_line_index + self.showable_line_numbers_in_editor
        else:
            last_line = len(self.editor_lines)

        for line_list in line_contents[first_line:last_line]:
            xcoord = self.line_start_x
            for d in line_list:
                surface = self.editor_font.render(d["chars"], 1, d["color"])
                self.screen.blit(surface, (xcoord, y_coordinate))
                xcoord += surface.get_width()
            y_coordinate += self.line_height_including_margin

    def display_editor(self, pygame_events, pressed_keys, mouse_x, mouse_y, mouse_pressed):
        self.cycleCounter = self.cycleCounter + 1

        snap_before = self._snapshot() if not self._suppress_undo and pygame_events else None

        if self.first_iteration_boolean:
            pygame.draw.rect(
                self.screen, self.color_coding_background,
                (self.editor_offset_x, self.editor_offset_y,
                 self.editor_width, self.editor_height),
            )
            self.first_iteration_boolean = False

        self.render_line_numbers_flag = True
        kb_result = self.handle_keyboard_input(pygame_events, pressed_keys)
        self.handle_mouse_input(pygame_events, mouse_x, mouse_y, mouse_pressed)
        self.update_line_number_display()
        self.render_background_coloring()
        self.render_line_numbers()
        self.render_highlight(mouse_x, mouse_y)
        if self.syntax_highlighting_python:
            line_contents = self.get_syntax_coloring_dicts()
        else:
            line_contents = self.get_single_color_dicts()
        self.render_line_contents(line_contents)
        self.render_caret()
        self.render_scrollbar_vertical()

        if snap_before is not None and self._snapshot() != snap_before:
            self._undo_stack.append(snap_before)
            if len(self._undo_stack) > UNDO_MAX:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

        return kb_result

    def update_line_number_display(self):
        n_lines = len(self.editor_lines)
        if n_lines != self.max_line_number_rendered:
            digit_width = self.letter_width
            self.line_number_width = max(
                self.letter_width * 6,
                digit_width * max(2, len(str(n_lines)))
            )
            self.line_start_x = self.editor_offset_x + self.line_number_width
            self.max_line_number_rendered = n_lines

    def get_code(self):
        return self.get_text_as_string()

    def set_code(self, code):
        self._suppress_undo = True
        self.clear_text()
        self.set_text_from_string(code)
        self._suppress_undo = False
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._maybe_save_undo()

    def _start_shift_selection(self):
        if not self.dragged_active:
            self.drag_chosen_line_index_start = self.chosen_line_index
            self.drag_chosen_letter_index_start = self.chosen_letter_index
            self.dragged_active = True
            self.dragged_finished = True

    def _extend_shift_selection(self):
        self.drag_chosen_line_index_end = self.chosen_line_index
        self.drag_chosen_letter_index_end = self.chosen_letter_index

    def handle_keyboard_input(self, pygame_events, pressed_keys):
        shift = pressed_keys[pygame.K_LSHIFT] or pressed_keys[pygame.K_RSHIFT]
        ctrl = pressed_keys[pygame.K_LCTRL] or pressed_keys[pygame.K_RCTRL]

        for event in pygame_events:
            if event.type == pygame.TEXTINPUT:
                self.insert_unicode(event.text)
                continue

            if event.type != pygame.KEYDOWN:
                continue

            if ctrl and event.key == pygame.K_z:
                if shift:
                    self.redo()
                else:
                    self.undo()
            elif ctrl and event.key == pygame.K_y:
                self.redo()
            elif ctrl and event.key == pygame.K_a:
                self.highlight_all()
            elif ctrl and event.key == pygame.K_s:
                return "save"
            elif ctrl and event.key == pygame.K_o:
                return "load"
            elif ctrl and event.key == pygame.K_v:
                self.handle_highlight_and_paste()
            elif ctrl and event.key == pygame.K_x:
                self.handle_highlight_and_cut()
            elif ctrl and event.key == pygame.K_c:
                self.handle_highlight_and_copy()
            elif self.dragged_finished and self.dragged_active:
                if shift and event.key in (
                    pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT
                ):
                    self._extend_shift_selection()
                    self._move_arrow(event.key)
                    self._extend_shift_selection()
                else:
                    self.handle_input_with_highlight(event)
            else:
                self.reset_text_area_to_caret()
                self.chosen_letter_index = int(self.chosen_letter_index)

                if shift and event.key in (
                    pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT
                ):
                    self._start_shift_selection()
                    self._move_arrow(event.key)
                    self._extend_shift_selection()
                elif (
                    self.dragged_finished and self.dragged_active
                    and event.unicode in ("\x08", "\x7f")
                ):
                    deletion_event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DELETE)
                    self.handle_input_with_highlight(deletion_event)
                elif event.unicode == "\x08":
                    self.handle_keyboard_backspace()
                    self.reset_text_area_to_caret()
                elif event.unicode == "\x7f":
                    self.handle_keyboard_delete()
                    self.reset_text_area_to_caret()
                elif len(pygame.key.name(event.key)) == 1:
                    self.insert_unicode(event.unicode)
                elif event.mod == 4096 and 1073741913 <= event.key <= 1073741922:
                    self.insert_unicode(event.unicode)
                elif event.key in (
                    pygame.K_KP_PERIOD, pygame.K_KP_DIVIDE,
                    pygame.K_KP_MULTIPLY, pygame.K_KP_MINUS,
                    pygame.K_KP_PLUS, pygame.K_KP_EQUALS,
                ):
                    self.insert_unicode(event.unicode)
                elif event.key == pygame.K_TAB:
                    self.handle_keyboard_tab()
                elif event.key == pygame.K_SPACE:
                    self.handle_keyboard_space()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.handle_keyboard_return()
                elif event.key == pygame.K_UP:
                    self._move_arrow(pygame.K_UP)
                elif event.key == pygame.K_DOWN:
                    self._move_arrow(pygame.K_DOWN)
                elif event.key == pygame.K_RIGHT:
                    self._move_arrow(pygame.K_RIGHT)
                elif event.key == pygame.K_LEFT:
                    self._move_arrow(pygame.K_LEFT)

    def _move_arrow(self, key):
        if key == pygame.K_UP:
            self.handle_keyboard_arrow_up()
        elif key == pygame.K_DOWN:
            self.handle_keyboard_arrow_down()
        elif key == pygame.K_LEFT:
            self.handle_keyboard_arrow_left()
        elif key == pygame.K_RIGHT:
            self.handle_keyboard_arrow_right()

    def insert_unicode(self, unicode):
        line = self.editor_lines[self.chosen_line_index]
        self.editor_lines[self.chosen_line_index] = (
            line[: self.chosen_letter_index] + unicode + line[self.chosen_letter_index :]
        )
        self.chosen_letter_index += len(unicode)
        self._update_caret_x()

    def handle_keyboard_space(self):
        self.insert_unicode(" ")

    def handle_keyboard_tab(self):
        self.insert_unicode("    ")

    def handle_keyboard_backspace(self):
        if self.chosen_letter_index == 0 and self.chosen_line_index == 0:
            return
        if self.chosen_letter_index == 0 and self.chosen_line_index > 0:
            self.chosen_line_index -= 1
            self.chosen_letter_index = len(self.editor_lines[self.chosen_line_index])
            self.caret_y -= self.line_height_including_margin
            self._update_caret_x()
            self.editor_lines[self.chosen_line_index] += self.editor_lines.pop(self.chosen_line_index + 1)
            self.render_line_numbers_flag = True
            if self.first_showable_line_index > 0 and (
                self.first_showable_line_index + self.showable_line_numbers_in_editor
            ) > len(self.editor_lines):
                self.first_showable_line_index -= 1
                self.caret_y += self.line_height_including_margin
            if self.chosen_line_index == self.first_showable_line_index - 1:
                self.first_showable_line_index -= 1
                self.caret_y += self.line_height_including_margin
        elif self.chosen_letter_index > 0:
            line = self.editor_lines[self.chosen_line_index]
            self.editor_lines[self.chosen_line_index] = (
                line[: self.chosen_letter_index - 1] + line[self.chosen_letter_index :]
            )
            self.chosen_letter_index -= 1
            self._update_caret_x()

    def handle_keyboard_delete(self):
        line = self.editor_lines[self.chosen_line_index]
        if self.chosen_letter_index < len(line):
            self.editor_lines[self.chosen_line_index] = (
                line[: self.chosen_letter_index] + line[self.chosen_letter_index + 1 :]
            )
        elif self.chosen_line_index != len(self.editor_lines) - 1:
            self.editor_lines[self.chosen_line_index] += self.editor_lines.pop(self.chosen_line_index + 1)
            self.render_line_numbers_flag = True
            if self.first_showable_line_index > 0 and (
                self.first_showable_line_index + self.showable_line_numbers_in_editor
            ) > len(self.editor_lines):
                self.first_showable_line_index -= 1
                self.caret_y += self.line_height_including_margin

    def handle_keyboard_arrow_left(self):
        if self.chosen_letter_index > 0:
            self.chosen_letter_index -= 1
            self._update_caret_x()
        elif self.chosen_letter_index == 0 and self.chosen_line_index > 0:
            self.chosen_line_index -= 1
            self.chosen_letter_index = len(self.editor_lines[self.chosen_line_index])
            self._update_caret_x()
            self.caret_y -= self.line_height_including_margin
            if self.chosen_line_index < self.first_showable_line_index:
                self.first_showable_line_index -= 1
                self.caret_y += self.line_height_including_margin
                self.render_line_numbers_flag = True

    def handle_keyboard_arrow_right(self):
        if self.chosen_letter_index < len(self.editor_lines[self.chosen_line_index]):
            self.chosen_letter_index += 1
            self._update_caret_x()
        elif self.chosen_line_index < len(self.editor_lines) - 1:
            self.chosen_letter_index = 0
            self.chosen_line_index += 1
            self._update_caret_x()
            self.caret_y += self.line_height_including_margin
            if self.chosen_line_index > (
                self.first_showable_line_index + self.showable_line_numbers_in_editor - 1
            ):
                self.first_showable_line_index += 1
                self.caret_y -= self.line_height_including_margin
                self.render_line_numbers_flag = True

    def handle_keyboard_arrow_up(self):
        if self.chosen_line_index == 0:
            self.chosen_letter_index = 0
            self._update_caret_x()
        else:
            self.chosen_line_index -= 1
            self.caret_y -= self.line_height_including_margin
            if len(self.editor_lines[self.chosen_line_index]) < self.chosen_letter_index:
                self.chosen_letter_index = len(self.editor_lines[self.chosen_line_index])
            self._update_caret_x()
            if self.chosen_line_index < self.first_showable_line_index:
                self.scrollbar_up()

    def handle_keyboard_arrow_down(self):
        if self.chosen_line_index < len(self.editor_lines) - 1:
            self.chosen_line_index += 1
            self.caret_y += self.line_height_including_margin
            if len(self.editor_lines[self.chosen_line_index]) < self.chosen_letter_index:
                self.chosen_letter_index = len(self.editor_lines[self.chosen_line_index])
            self._update_caret_x()
            if self.chosen_line_index > (
                self.first_showable_line_index + self.showable_line_numbers_in_editor - 1
            ):
                self.scrollbar_down()
        elif self.chosen_line_index == len(self.editor_lines) - 1:
            self.chosen_letter_index = len(self.editor_lines[self.chosen_line_index])
            self._update_caret_x()

    def handle_mouse_input(self, pygame_events, mouse_x, mouse_y, mouse_pressed):
        for event in pygame_events:
            if event.type == pygame.MOUSEBUTTONDOWN and not self.mouse_within_texteditor(
                mouse_x, mouse_y
            ):
                if self.scrollbar is not None:
                    if self.scrollbar.collidepoint(mouse_x, mouse_y):
                        self.scrollbar_start_y = mouse_y
                        self.scrollbar_is_being_dragged = True

            if event.type == pygame.MOUSEBUTTONDOWN and self.mouse_within_texteditor(
                mouse_x, mouse_y
            ):
                if event.button == 4 and self.first_showable_line_index > 0:
                    for _ in range(SCROLL_LINES):
                        if self.first_showable_line_index > 0:
                            self.scrollbar_up()
                elif event.button == 5 and (
                    self.first_showable_line_index + self.showable_line_numbers_in_editor
                    < len(self.editor_lines)
                ):
                    for _ in range(SCROLL_LINES):
                        if (
                            self.first_showable_line_index
                            + self.showable_line_numbers_in_editor
                            < len(self.editor_lines)
                        ):
                            self.scrollbar_down()
                elif event.button == 1:
                    if not self.click_hold_flag:
                        self.last_clickdown_cycle = self.cycleCounter
                        self.click_hold_flag = True
                        self.dragged_active = True
                        self.dragged_finished = False
                        if self.mouse_within_texteditor(mouse_x, mouse_y):
                            if self.mouse_within_existing_lines(mouse_y):
                                self._set_drag_start_by_mouse(mouse_x, mouse_y)
                            else:
                                self.set_drag_start_after_last_line()
                            self.update_caret_position_by_drag_start()

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.scrollbar_is_being_dragged = False
                if self.click_hold_flag:
                    self.last_clickup_cycle = self.cycleCounter
                    self.click_hold_flag = False
                    if self.mouse_within_texteditor(mouse_x, mouse_y):
                        if self.mouse_within_existing_lines(mouse_y):
                            self._set_drag_end_by_mouse(mouse_x, mouse_y)
                        else:
                            self.set_drag_end_after_last_line()
                        self.update_caret_position_by_drag_end()
                    else:
                        if mouse_y < self.editor_offset_y:
                            self.drag_chosen_line_index_end = self.first_showable_line_index
                        elif mouse_y > (
                            self.editor_offset_y + self.editor_height - self.conclusion_bar_height
                        ):
                            vis = self.showable_line_numbers_in_editor
                            if len(self.editor_lines) >= vis:
                                self.drag_chosen_line_index_end = self.first_showable_line_index + vis - 1
                            else:
                                self.drag_chosen_line_index_end = len(self.editor_lines) - 1
                        else:
                            self.set_drag_end_line_by_mouse(mouse_y)
                        self._set_drag_end_letter_by_mouse(mouse_x)

            if (self.last_clickup_cycle - self.last_clickdown_cycle) >= 0:
                if (
                    self.drag_chosen_line_index_end == self.drag_chosen_line_index_start
                    and self.drag_chosen_letter_index_end == self.drag_chosen_letter_index_start
                ):
                    self.dragged_active = False
                else:
                    self.dragged_active = True
                self.dragged_finished = True
                self.chosen_line_index = self.drag_chosen_line_index_end
                self.chosen_letter_index = self.drag_chosen_letter_index_end
                self.update_caret_position()
                self.last_clickdown_cycle = 0
                self.last_clickup_cycle = -1

        if mouse_pressed[0] == 1 and self.scrollbar_is_being_dragged:
            self._handle_scrollbar_drag(mouse_y)
        elif mouse_pressed[0] == 1 and self.click_hold_flag:
            self._handle_drag_autoscroll(mouse_x, mouse_y)

    def _set_drag_start_by_mouse(self, mouse_x, mouse_y):
        self.drag_chosen_line_index_start = self.get_line_index(mouse_y)
        li = self.drag_chosen_line_index_start
        max_letter = len(self.editor_lines[li]) if li < len(self.editor_lines) else 0
        idx = self._get_letter_index_for_line(li, mouse_x)
        if idx > max_letter:
            self.drag_chosen_letter_index_start = max_letter
        else:
            self.drag_chosen_letter_index_start = idx

    def _set_drag_end_by_mouse(self, mouse_x, mouse_y):
        self.set_drag_end_line_by_mouse(mouse_y)
        self._set_drag_end_letter_by_mouse(mouse_x)

    def _set_drag_end_letter_by_mouse(self, mouse_x):
        li = self.drag_chosen_line_index_end
        max_letter = len(self.editor_lines[li]) if li < len(self.editor_lines) else 0
        idx = self._get_letter_index_for_line(li, mouse_x)
        if idx > max_letter:
            self.drag_chosen_letter_index_end = max_letter
        else:
            self.drag_chosen_letter_index_end = idx

    def _get_letter_index_for_line(self, line_index, mouse_x):
        x = mouse_x - self.line_start_x
        if x <= 0:
            return 0
        if line_index >= len(self.editor_lines):
            return 0
        line = self.editor_lines[line_index]
        for i in range(len(line)):
            if self.editor_font.size(line[: i + 1])[0] >= x:
                return i
        return len(line)

    def _handle_scrollbar_drag(self, mouse_y):
        track_top = self.editor_offset_y + self.scrollbar_width
        track_bottom = self.editor_offset_y + self.editor_height - self.scrollbar_width
        fraction = max(0.0, min(1.0, (mouse_y - track_top) / max(1, track_bottom - track_top)))
        max_line = max(0, len(self.editor_lines) - self.showable_line_numbers_in_editor)
        target = int(fraction * max_line)
        if target != self.first_showable_line_index:
            self.first_showable_line_index = target
            self.render_line_numbers_flag = True

    def _handle_drag_autoscroll(self, mouse_x, mouse_y):
        if mouse_y < self.editor_offset_y + AUTO_SCROLL_MARGIN:
            for _ in range(AUTO_SCROLL_SPEED):
                if self.first_showable_line_index > 0:
                    self.scrollbar_up()
        elif mouse_y > self.editor_offset_y + self.editor_height - AUTO_SCROLL_MARGIN:
            for _ in range(AUTO_SCROLL_SPEED):
                if (
                    self.first_showable_line_index + self.showable_line_numbers_in_editor
                    < len(self.editor_lines)
                ):
                    self.scrollbar_down()