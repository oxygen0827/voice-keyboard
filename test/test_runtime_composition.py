import unittest
from unittest.mock import MagicMock, patch

from agent.ai_intent import IntentFallbackOptions
from agent.runtime_composition import RuntimeBackend, RuntimeOptions, build_runtime_backend, options_from_args


class RuntimeCompositionTests(unittest.TestCase):
    def test_options_from_args_keeps_runtime_flags_only(self):
        class Args:
            no_serial = True
            port = "/dev/cu.test"
            headless = True

        self.assertEqual(
            options_from_args(Args()),
            RuntimeOptions(no_serial=True, port="/dev/cu.test"),
        )

    def test_runtime_backend_stop_stops_components_and_clears_slots(self):
        calls = []

        class Component:
            def __init__(self, name):
                self.name = name

            def stop(self):
                calls.append(self.name)

        backend = RuntimeBackend()
        backend.audio = Component("audio")
        backend.ime_monitor = Component("ime")
        backend.reader = Component("reader")

        backend.stop()

        self.assertEqual(calls, ["audio", "ime", "reader"])
        self.assertIsNone(backend.audio)
        self.assertIsNone(backend.ime_monitor)
        self.assertIsNone(backend.reader)

    def test_runtime_backend_builds_input_environment_without_cursor_monitors(self):
        with (
            patch("agent.runtime_composition.load_config", return_value={
                "stt": {"provider": "openai", "api_key": "sk"},
            }),
            patch("agent.typer.init"),
            patch("agent.runtime_composition.SpeechInterpretationProviderFactory") as factory_cls,
        ):
            factory_cls.return_value.create_provider_set.return_value = None
            backend = build_runtime_backend(RuntimeOptions(no_serial=True), MagicMock(), None, MagicMock())

        self.assertIsNotNone(backend.input_environment)

    def test_runtime_backend_records_active_hotkeys(self):
        with (
            patch("agent.runtime_composition.load_config", return_value={
                "stt": {"provider": "openai", "api_key": "sk"},
                "audio": {"ptt_key": "shift_r", "ai_key": "ctrl_r"},
            }),
            patch("agent.typer.init"),
            patch("agent.runtime_composition.SpeechInterpretationProviderFactory") as factory_cls,
        ):
            factory_cls.return_value.create_provider_set.return_value = None
            backend = build_runtime_backend(RuntimeOptions(no_serial=True), MagicMock(), None, MagicMock())

        self.assertEqual(backend.hotkeys, {"ptt_key": "shift_r", "ai_key": "ctrl_r"})

    def test_build_audio_runtime_passes_intent_fallback_options_to_ai_handler(self):
        from agent.runtime_composition import build_audio_runtime

        providers = MagicMock()
        providers.text_operation_editor = MagicMock()
        providers.instruction_stt = MagicMock()
        providers.utterance_stt = MagicMock()
        with (
            patch("agent.runtime_composition.SpeechInterpretationProviderFactory") as factory_cls,
            patch("agent.ai_handler.AIHandler") as handler_cls,
            patch("agent.memo_store.MemoStore"),
            patch("agent.operation_confirmation.make_operation_confirmation", return_value="confirm") as confirm_factory,
            patch("agent.main.make_utterance_handler", return_value=MagicMock()) as utterance_handler,
            patch("agent.push_to_talk.PushToTalk") as ptt_cls,
        ):
            factory_cls.return_value.create_provider_set.return_value = providers

            build_audio_runtime({
                "audio": {"mode": "ptt"},
                "instruction_mode": {
                    "intent_fallbacks": {
                        "multi_step_guard": False,
                        "memo_fuzzy_recall": False,
                    },
                },
                "correction_memory": {
                    "confirm_threshold": 3,
                },
            }, MagicMock())

        self.assertEqual(
            handler_cls.call_args.kwargs["intent_fallbacks"],
            IntentFallbackOptions(
                multi_step_guard=False,
                selected_edit_override=True,
                memo_fuzzy_recall=False,
            ),
        )
        self.assertNotIn("personal_lexicon", handler_cls.call_args.kwargs)
        self.assertEqual(handler_cls.call_args.kwargs["confirm_operation"], "confirm")
        confirm_factory.assert_called_once()
        self.assertEqual(
            utterance_handler.call_args.kwargs["correction_config"],
            {"confirm_threshold": 3},
        )
        self.assertTrue(utterance_handler.call_args.kwargs["return_mode"])
        ptt_cls.return_value.start.assert_called_once_with()

    def test_build_audio_runtime_wires_correction_key_tracker_to_ptt(self):
        from agent.runtime_composition import build_audio_runtime

        providers = MagicMock()
        providers.text_operation_editor = None
        providers.instruction_stt = None
        providers.utterance_stt = MagicMock()
        tracker = MagicMock()
        scheduler = MagicMock()
        mode = MagicMock()
        mode.handle_utterance = MagicMock()
        mode.correction_tracker = tracker
        mode.correction_scheduler = scheduler
        with (
            patch("agent.runtime_composition.SpeechInterpretationProviderFactory") as factory_cls,
            patch("agent.main.make_utterance_handler", return_value=mode),
            patch("agent.ime_commit_monitor.ImeCommitMonitor") as ime_monitor_cls,
            patch("agent.push_to_talk.PushToTalk") as ptt_cls,
        ):
            factory_cls.return_value.create_provider_set.return_value = providers

            build_audio_runtime({"audio": {"mode": "ptt"}}, MagicMock())

        on_key_press = ptt_cls.call_args.kwargs["on_key_press"]
        key = MagicMock()
        on_key_press(key)
        tracker.record_key_press.assert_called_once_with(key)
        scheduler.schedule_after_edit.assert_called_once_with()

        scheduler.schedule_after_edit.reset_mock()
        on_key_release = ptt_cls.call_args.kwargs["on_key_release"]
        on_key_release(key)
        scheduler.schedule_after_edit.assert_called_once_with()
        on_committed_text = ime_monitor_cls.call_args.args[0]
        on_committed_text("净")
        tracker.record_committed_text.assert_called_once_with("净")
        self.assertEqual(scheduler.schedule_after_edit.call_count, 2)
        ime_monitor_cls.return_value.start.assert_called_once_with()
        self.assertEqual(
            ptt_cls.return_value._correction_ime_monitor,
            ime_monitor_cls.return_value,
        )

    def test_build_audio_runtime_does_not_reschedule_for_uncommitted_ime_keys(self):
        from agent.runtime_composition import build_audio_runtime

        providers = MagicMock()
        providers.text_operation_editor = None
        providers.instruction_stt = None
        providers.utterance_stt = MagicMock()
        tracker = MagicMock()
        tracker.record_committed_text.return_value = False
        scheduler = MagicMock()
        mode = MagicMock()
        mode.handle_utterance = MagicMock()
        mode.correction_tracker = tracker
        mode.correction_scheduler = scheduler
        with (
            patch("agent.runtime_composition.SpeechInterpretationProviderFactory") as factory_cls,
            patch("agent.main.make_utterance_handler", return_value=mode),
            patch("agent.ime_commit_monitor.ImeCommitMonitor") as ime_monitor_cls,
            patch("agent.push_to_talk.PushToTalk") as ptt_cls,
        ):
            factory_cls.return_value.create_provider_set.return_value = providers

            build_audio_runtime({"audio": {"mode": "ptt"}}, MagicMock())

        on_committed_text = ime_monitor_cls.call_args.args[0]
        scheduler.schedule_after_edit.reset_mock()
        on_committed_text("w")

        tracker.record_committed_text.assert_called_once_with("w")
        scheduler.schedule_after_edit.assert_not_called()

    def test_build_audio_runtime_passes_xiao_ble_device_to_ptt(self):
        from agent.runtime_composition import build_audio_runtime

        providers = MagicMock()
        providers.text_operation_editor = None
        providers.instruction_stt = None
        providers.utterance_stt = MagicMock()
        with (
            patch("agent.runtime_composition.SpeechInterpretationProviderFactory") as factory_cls,
            patch("agent.main.make_utterance_handler", return_value=MagicMock()),
            patch("agent.push_to_talk.PushToTalk") as ptt_cls,
        ):
            factory_cls.return_value.create_provider_set.return_value = providers

            build_audio_runtime({"audio": {"mode": "ptt", "device": "xiao_ble"}}, MagicMock())

        self.assertEqual(ptt_cls.call_args.kwargs["device"], "xiao_ble")
        self.assertEqual(ptt_cls.call_args.kwargs["xiao_ble_options"], {})

    def test_build_audio_runtime_passes_xiao_ble_audio_options_to_ptt(self):
        from agent.runtime_composition import build_audio_runtime

        providers = MagicMock()
        providers.text_operation_editor = None
        providers.instruction_stt = None
        providers.utterance_stt = MagicMock()
        xiao_ble_options = {"trim_silence": False, "normalize_gain": False}
        with (
            patch("agent.runtime_composition.SpeechInterpretationProviderFactory") as factory_cls,
            patch("agent.main.make_utterance_handler", return_value=MagicMock()),
            patch("agent.push_to_talk.PushToTalk") as ptt_cls,
        ):
            factory_cls.return_value.create_provider_set.return_value = providers

            build_audio_runtime({
                "audio": {
                    "mode": "ptt",
                    "device": "xiao_ble",
                    "xiao_ble": xiao_ble_options,
                },
            }, MagicMock())

        self.assertEqual(ptt_cls.call_args.kwargs["xiao_ble_options"], xiao_ble_options)


if __name__ == "__main__":
    unittest.main()
