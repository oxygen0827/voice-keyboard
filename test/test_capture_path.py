import unittest
from unittest.mock import MagicMock, patch

from agent.capture_path import UtteranceEvent
from agent.push_to_talk import PushToTalk


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


if __name__ == "__main__":
    unittest.main()
