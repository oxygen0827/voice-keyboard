import unittest
from unittest.mock import MagicMock, patch

from agent.audio_monitor import FRAME_BYTES
from agent.capture_path import UtteranceEvent
from agent.capture_path_runtime import CapturePathRuntime, CaptureStart, PolishToggle
from agent.push_to_talk import PushToTalk
from agent.xiao_ble_audio import (
    analyze_pcm_16k,
    normalize_pcm_16k_for_stt,
    trim_pcm_16k_silence,
    upsample_pcm_8k_to_16k,
)


def _pcm16(value: int, samples: int) -> bytes:
    return value.to_bytes(2, "little", signed=True) * samples


class CapturePathTests(unittest.TestCase):
    def test_utterance_event_constructors_name_capture_mode(self):
        self.assertEqual(
            UtteranceEvent.dictation(b"pcm", polish=True),
            UtteranceEvent(pcm=b"pcm", mode="dictation", polish=True),
        )
        self.assertEqual(
            UtteranceEvent.instruction_edit(b"edit"),
            UtteranceEvent(pcm=b"edit", mode="instruction_edit"),
        )
        self.assertEqual(
            UtteranceEvent.instruction(b"ai"),
            UtteranceEvent(pcm=b"ai", mode="instruction"),
        )

    def test_push_to_talk_dispatch_maps_capture_events_to_existing_callbacks(self):
        on_dictation = MagicMock()
        on_edit = MagicMock()
        on_instruction = MagicMock()
        ptt = PushToTalk(
            on_dictation,
            on_edit_utterance=on_edit,
            on_ai_utterance=on_instruction,
        )

        with patch("agent.push_to_talk.threading.Thread") as thread:
            ptt._dispatch_utterance(UtteranceEvent.dictation(b"one", polish=True), "dict")
            ptt._dispatch_utterance(UtteranceEvent.instruction_edit(b"two"), "edit")
            ptt._dispatch_utterance(UtteranceEvent.instruction(b"three"), "inst")

        calls = thread.call_args_list
        self.assertEqual(calls[0].kwargs["target"], on_dictation)
        self.assertEqual(calls[0].kwargs["args"], (b"one", True))
        self.assertEqual(calls[1].kwargs["target"], on_edit)
        self.assertEqual(calls[1].kwargs["args"], (b"two",))
        self.assertEqual(calls[2].kwargs["target"], on_instruction)
        self.assertEqual(calls[2].kwargs["args"], (b"three",))

    def test_toggle_key_disables_and_reenables_recording(self):
        on_dictation = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", toggle_key="b")

        with patch.object(ptt, "_start_recording") as start_recording:
            ptt._on_press(ptt._toggle_keys[0])
            ptt._on_press(ptt._ptt_keys[0])
            ptt._on_press(ptt._toggle_keys[0])
            ptt._on_press(ptt._ptt_keys[0])

        start_recording.assert_called_once_with()

    def test_push_to_talk_forwards_non_hotkey_presses_to_correction_tracker(self):
        on_dictation = MagicMock()
        on_key_press = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", toggle_key="b", on_key_press=on_key_press)
        ordinary_key = MagicMock()

        ptt._on_press(ordinary_key)

        on_key_press.assert_called_once_with(ordinary_key)

    def test_push_to_talk_uses_quartz_listener_on_macos(self):
        on_dictation = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a")

        with (
            patch("agent.push_to_talk.sys.platform", "darwin"),
            patch("agent.macos_keyboard_listener.MacOSKeyboardListener") as quartz_listener,
            patch("agent.push_to_talk.kb.Listener") as pynput_listener,
            patch.object(ptt, "_xiao_source", None),
        ):
            quartz_listener.return_value.start.return_value = None
            ptt.start()

        quartz_listener.assert_called_once_with(
            on_press=ptt._on_press,
            on_release=ptt._on_release,
        )
        quartz_listener.return_value.start.assert_called_once_with()
        pynput_listener.assert_not_called()

    def test_push_to_talk_forwards_non_hotkey_releases_to_correction_tracker(self):
        on_dictation = MagicMock()
        on_key_release = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", on_key_release=on_key_release)
        ordinary_key = MagicMock()

        ptt._on_release(ordinary_key)

        on_key_release.assert_called_once_with(ordinary_key)

    def test_push_to_talk_does_not_forward_keys_while_capturing(self):
        on_dictation = MagicMock()
        on_key_press = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", on_key_press=on_key_press)
        ptt._capture_runtime.press_dictation(ptt._ptt_keys[0], now=10.0)

        ptt._on_press(MagicMock())

        on_key_press.assert_not_called()

    def test_capture_path_runtime_blocks_capture_when_disabled(self):
        runtime = CapturePathRuntime()

        self.assertFalse(runtime.toggle_enabled())
        self.assertIsNone(runtime.press_dictation("ptt", now=10.0))

        self.assertTrue(runtime.toggle_enabled())
        self.assertEqual(
            runtime.press_dictation("ptt", now=11.0),
            CaptureStart(mode="dictate", polish=False),
        )

    def test_capture_path_runtime_keeps_one_active_capture(self):
        runtime = CapturePathRuntime()

        self.assertEqual(runtime.press_instruction_edit("edit"), CaptureStart(mode="edit"))
        self.assertIsNone(runtime.press_instruction("ai"))
        self.assertIsNone(runtime.release("other"))

        self.assertEqual(runtime.release("edit"), "edit")
        self.assertEqual(runtime.press_instruction("ai"), CaptureStart(mode="ai"))

    def test_capture_path_runtime_toggles_polish_on_double_tap_without_capture(self):
        runtime = CapturePathRuntime()

        self.assertEqual(
            runtime.press_dictation("ptt", now=10.0),
            CaptureStart(mode="dictate", polish=False),
        )
        self.assertEqual(runtime.release("ptt"), "dictate")

        self.assertEqual(runtime.press_dictation("ptt", now=10.2), PolishToggle(polish=True))
        self.assertFalse(runtime.is_capturing)

        self.assertEqual(
            runtime.press_dictation("ptt", now=11.0),
            CaptureStart(mode="dictate", polish=True),
        )

    def test_push_to_talk_shows_status_when_double_tap_toggles_polish_mode(self):
        on_dictation = MagicMock()
        status = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", status_window=status)

        with (
            patch("agent.push_to_talk.time.monotonic", side_effect=[10.0, 10.2]),
            patch.object(ptt, "_start_recording"),
        ):
            ptt._on_press(ptt._ptt_keys[0])
            ptt._on_release(ptt._ptt_keys[0])
            ptt._on_press(ptt._ptt_keys[0])

        self.assertEqual(status.set_state.call_args_list[-1].args, ("polish_mode",))
        self.assertNotIn(("recording",), [call.args for call in status.set_state.call_args_list])

    def test_push_to_talk_shows_status_when_double_tap_toggles_back_to_dictation_mode(self):
        on_dictation = MagicMock()
        status = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", status_window=status)
        ptt._capture_runtime.polish_mode = True

        with (
            patch("agent.push_to_talk.time.monotonic", side_effect=[10.0, 10.2]),
            patch.object(ptt, "_start_recording"),
        ):
            ptt._on_press(ptt._ptt_keys[0])
            ptt._on_release(ptt._ptt_keys[0])
            ptt._on_press(ptt._ptt_keys[0])

        self.assertEqual(status.set_state.call_args_list[-1].args, ("dictation_mode",))
        self.assertNotIn(("recording",), [call.args for call in status.set_state.call_args_list])

    def test_push_to_talk_shows_dictation_recording_status_immediately(self):
        on_dictation = MagicMock()
        status = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", status_window=status)

        ptt._capture_runtime.press_dictation(ptt._ptt_keys[0], now=10.0)
        with patch("agent.push_to_talk.sd.RawInputStream") as stream_cls:
            stream_cls.return_value.start.return_value = None
            ptt._start_recording()

        status.set_state.assert_called_once_with("recording")
        self.assertIsNone(ptt._recording_status_timer)

    def test_push_to_talk_uses_xiao_ble_source_instead_of_sounddevice_stream(self):
        on_dictation = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", device="xiao_ble")
        ptt._capture_runtime.press_dictation(ptt._ptt_keys[0], now=10.0)
        xiao = MagicMock()
        xiao.connected = True
        ptt._xiao_source = xiao

        with patch("agent.push_to_talk.sd.RawInputStream") as stream_cls:
            ptt._start_recording()

        stream_cls.assert_not_called()
        xiao.start_recording.assert_called_once_with(ptt._record_audio_bytes)

    def test_push_to_talk_skips_stt_when_xiao_ble_audio_is_nearly_silent(self):
        on_dictation = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", device="xiao_ble")
        ptt._xiao_source = MagicMock()
        ptt._buf = [b"\x00\x00" * 16000]

        ptt._stop_recording("dictate")

        on_dictation.assert_not_called()

    def test_push_to_talk_normalizes_quiet_xiao_ble_audio_before_stt(self):
        on_dictation = MagicMock()
        ptt = PushToTalk(
            on_dictation,
            ptt_key="a",
            device="xiao_ble",
            xiao_ble_options={"normalize_gain": True},
        )
        ptt._xiao_source = MagicMock()
        quiet_pcm = _pcm16(500, 16000)
        ptt._buf = [quiet_pcm]

        with patch("agent.push_to_talk.threading.Thread") as thread:
            ptt._stop_recording("dictate")

        thread.assert_called_once()
        sent_pcm, polish = thread.call_args.kwargs["args"]
        self.assertFalse(polish)
        self.assertGreater(
            analyze_pcm_16k(sent_pcm).rms,
            analyze_pcm_16k(quiet_pcm).rms,
        )

    def test_push_to_talk_trims_xiao_ble_edge_silence_before_stt(self):
        on_dictation = MagicMock()
        ptt = PushToTalk(
            on_dictation,
            ptt_key="a",
            device="xiao_ble",
            xiao_ble_options={"trim_silence": True},
        )
        ptt._xiao_source = MagicMock()
        edge_silence_pcm = (
            _pcm16(0, 16000)
            + _pcm16(800, 16000)
            + _pcm16(0, 16000)
        )
        ptt._buf = [edge_silence_pcm]

        with patch("agent.push_to_talk.threading.Thread") as thread:
            ptt._stop_recording("dictate")

        thread.assert_called_once()
        sent_pcm, _ = thread.call_args.kwargs["args"]
        self.assertLess(len(sent_pcm), len(edge_silence_pcm))
        self.assertGreater(analyze_pcm_16k(sent_pcm).duration_sec, 1.0)

    def test_push_to_talk_normalizes_xiao_ble_mid_sentence_audio_before_stt(self):
        on_dictation = MagicMock()
        ptt = PushToTalk(
            on_dictation,
            ptt_key="a",
            device="xiao_ble",
            xiao_ble_options={"normalize_gain": True},
        )
        ptt._xiao_source = MagicMock()
        frame_samples = FRAME_BYTES // 2
        quiet_frame = _pcm16(500, frame_samples)
        ptt._vad_speech_frames = [quiet_frame] * 4

        with patch("agent.push_to_talk.threading.Thread") as thread:
            ptt._dispatch_mid_sentence()

        thread.assert_called_once()
        sent_pcm, _ = thread.call_args.kwargs["args"]
        self.assertGreater(
            analyze_pcm_16k(sent_pcm).rms,
            analyze_pcm_16k(quiet_frame * 4).rms,
        )

    def test_push_to_talk_preserves_xiao_ble_audio_by_default(self):
        on_dictation = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a", device="xiao_ble")
        ptt._xiao_source = MagicMock()
        raw_pcm = _pcm16(0, 16000) + _pcm16(500, 16000) + _pcm16(0, 16000)
        ptt._buf = [raw_pcm]

        with patch("agent.push_to_talk.threading.Thread") as thread:
            ptt._stop_recording("dictate")

        thread.assert_called_once()
        sent_pcm, _ = thread.call_args.kwargs["args"]
        self.assertEqual(sent_pcm, raw_pcm)

    def test_push_to_talk_cancels_delayed_recording_status_when_stopped(self):
        on_dictation = MagicMock()
        ptt = PushToTalk(on_dictation, ptt_key="a")
        timer = MagicMock()
        ptt._recording_status_timer = timer

        ptt._stop_recording("dictate")

        timer.cancel.assert_called_once()
        self.assertIsNone(ptt._recording_status_timer)

    def test_xiao_ble_upsamples_pcm_8k_to_16k_by_duplicating_samples(self):
        pcm8 = b"\x01\x00\x02\x00\xff\xff"

        self.assertEqual(
            upsample_pcm_8k_to_16k(pcm8),
            b"\x01\x00\x01\x00\x02\x00\x02\x00\xff\xff\xff\xff",
        )

    def test_xiao_ble_analyzes_pcm_quality(self):
        quality = analyze_pcm_16k(b"\x00\x00\xe8\x03\x18\xfc")

        self.assertEqual(quality.max_amplitude, 1000)
        self.assertGreater(quality.rms, 800)

    def test_xiao_ble_trims_leading_and_trailing_silence_with_padding(self):
        pcm = _pcm16(0, 16000) + _pcm16(800, 16000) + _pcm16(0, 16000)

        trimmed, leading_sec, trailing_sec = trim_pcm_16k_silence(pcm)

        self.assertLess(len(trimmed), len(pcm))
        self.assertAlmostEqual(leading_sec, 0.88, places=2)
        self.assertAlmostEqual(trailing_sec, 0.88, places=2)
        self.assertAlmostEqual(analyze_pcm_16k(trimmed).duration_sec, 1.24, places=2)

    def test_xiao_ble_normalizes_quiet_pcm_with_limited_gain(self):
        quiet_pcm = _pcm16(100, 16000)

        normalized, gain, quality = normalize_pcm_16k_for_stt(quiet_pcm)

        self.assertEqual(gain, 9.0)
        self.assertGreater(quality.rms, analyze_pcm_16k(quiet_pcm).rms)
        self.assertEqual(analyze_pcm_16k(normalized), quality)


if __name__ == "__main__":
    unittest.main()
