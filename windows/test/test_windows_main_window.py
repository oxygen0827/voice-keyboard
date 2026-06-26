import unittest
from unittest.mock import MagicMock, patch

from agent.correction_memory import CorrectionEntry
from agent.history import History
from agent.windows.main_window import WindowsMainWindow


class WindowsMainWindowTests(unittest.TestCase):
    def test_build_includes_dictionary_tab_between_intent_and_memo(self):
        window = WindowsMainWindow(
            history=History(),
            insert_text=MagicMock(),
            reload_config=MagicMock(),
            notify=MagicMock(),
        )
        calls = []

        def tab(zh, en):
            calls.append((zh, en))
            return MagicMock()

        with (
            patch("agent.windows.main_window.ttk.Frame", return_value=MagicMock()),
            patch("agent.windows.main_window.ttk.Notebook", return_value=MagicMock()),
            patch.object(window, "_tab", side_effect=tab),
            patch.object(window, "_build_overview_tab"),
            patch.object(window, "_build_history_tab"),
            patch.object(window, "_build_intent_diagnostics_tab"),
            patch.object(window, "_build_dictionary_tab") as dictionary_tab,
            patch.object(window, "_build_memo_tab"),
            patch.object(window, "_build_hotkeys_tab"),
            patch.object(window, "_build_config_tab"),
            patch.object(window, "_build_check_tab"),
            patch.object(window, "refresh_all"),
        ):
            window._root = MagicMock()
            window._build()

        dictionary_tab.assert_called_once_with()

    def test_dictionary_refresh_loads_added_and_candidate_corrections(self):
        window = WindowsMainWindow(
            history=History(),
            insert_text=MagicMock(),
            reload_config=MagicMock(),
            notify=MagicMock(),
        )
        memory = MagicMock()
        memory.entries = (
            CorrectionEntry("林之昂", "林知昂", 3, updated_at=2.0),
        )
        memory.candidates = (
            CorrectionEntry("王之行", "王知行", 1, updated_at=1.0),
        )
        added_tree = MagicMock()
        candidate_tree = MagicMock()
        window._dictionary_entries_tree = added_tree
        window._dictionary_candidates_tree = candidate_tree

        with patch.object(window, "_new_correction_memory", return_value=memory):
            window._refresh_dictionary()

        self.assertEqual(
            [(entry.wrong, entry.correct, entry.count) for entry in window._dictionary_entries],
            [("林之昂", "林知昂", 3)],
        )
        self.assertEqual(
            [(entry.wrong, entry.correct, entry.count) for entry in window._dictionary_candidates],
            [("王之行", "王知行", 1)],
        )
        added_tree.insert.assert_called_once()
        candidate_tree.insert.assert_called_once()

    def test_delete_checked_dictionary_items_removes_entries_and_candidates(self):
        window = WindowsMainWindow(
            history=History(),
            insert_text=MagicMock(),
            reload_config=MagicMock(),
            notify=MagicMock(),
        )
        memory = MagicMock()
        memory.delete_entry.return_value = True
        memory.delete_candidate.return_value = True
        window._checked_dictionary_entries = {"林之昂"}
        window._checked_dictionary_candidates = {("王之行", "王知行")}
        window._dictionary_entries_tree = MagicMock()
        window._dictionary_candidates_tree = MagicMock()

        with (
            patch.object(window, "_new_correction_memory", return_value=memory),
            patch.object(window, "_refresh_dictionary"),
            patch("agent.windows.main_window.messagebox.askyesno", return_value=True),
        ):
            window._delete_checked_dictionary_items()

        memory.delete_entry.assert_called_once_with("林之昂")
        memory.delete_candidate.assert_called_once_with("王之行", "王知行")
        self.assertEqual(window._checked_dictionary_entries, set())
        self.assertEqual(window._checked_dictionary_candidates, set())

    def test_dictionary_header_checkbox_toggles_added_entries(self):
        window = WindowsMainWindow(
            history=History(),
            insert_text=MagicMock(),
            reload_config=MagicMock(),
            notify=MagicMock(),
        )
        tree = MagicMock()
        window._dictionary_entries_tree = tree
        window._dictionary_candidates_tree = MagicMock()
        window._dictionary_entries = [
            CorrectionEntry("林之昂", "林知昂", 3, updated_at=2.0),
            CorrectionEntry("王之行", "王知行", 3, updated_at=1.0),
        ]

        with patch.object(window, "_populate_correction_tree") as populate:
            window._toggle_dictionary_tree_header(tree)
            self.assertEqual(window._checked_dictionary_entries, {"林之昂", "王之行"})
            populate.assert_called_with(tree, window._dictionary_entries, "entry")

            window._toggle_dictionary_tree_header(tree)
            self.assertEqual(window._checked_dictionary_entries, set())

    def test_dictionary_header_checkbox_toggles_candidates(self):
        window = WindowsMainWindow(
            history=History(),
            insert_text=MagicMock(),
            reload_config=MagicMock(),
            notify=MagicMock(),
        )
        tree = MagicMock()
        window._dictionary_entries_tree = MagicMock()
        window._dictionary_candidates_tree = tree
        window._dictionary_candidates = [
            CorrectionEntry("林之昂", "林知昂", 1, updated_at=2.0),
            CorrectionEntry("王之行", "王知行", 1, updated_at=1.0),
        ]

        with patch.object(window, "_populate_correction_tree") as populate:
            window._toggle_dictionary_tree_header(tree)
            self.assertEqual(
                window._checked_dictionary_candidates,
                {("林之昂", "林知昂"), ("王之行", "王知行")},
            )
            populate.assert_called_with(tree, window._dictionary_candidates, "candidate")

            window._toggle_dictionary_tree_header(tree)
            self.assertEqual(window._checked_dictionary_candidates, set())

    def test_dictionary_header_click_breaks_row_toggle(self):
        window = WindowsMainWindow(
            history=History(),
            insert_text=MagicMock(),
            reload_config=MagicMock(),
            notify=MagicMock(),
        )
        tree = MagicMock()
        tree.identify_region.return_value = "heading"
        tree.identify_column.return_value = "#1"
        window._dictionary_entries_tree = tree
        window._dictionary_candidates_tree = MagicMock()
        event = MagicMock(x=10, y=2)

        with patch.object(window, "_toggle_dictionary_tree_header") as toggle:
            result = window._toggle_dictionary_tree_check(event, "entry")

        self.assertEqual(result, "break")
        toggle.assert_called_once_with(tree)


if __name__ == "__main__":
    unittest.main()
