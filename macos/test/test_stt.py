import unittest
from unittest.mock import patch

from agent.stt import BYTES_PER_SECOND, _GLMASR2512STT, _join_transcription_chunks


class GLMASR2512STTTests(unittest.TestCase):
    def test_long_audio_is_split_below_provider_duration_limit(self):
        stt = _GLMASR2512STT({
            "api_key": "test-key",
            "chunk_seconds": 25,
        })
        pcm = b"\0" * (BYTES_PER_SECOND * 57)

        with patch.object(
            stt,
            "transcribe_wav",
            side_effect=["第一段。", "第二段。", "第三段。"],
        ) as transcribe_wav:
            text = stt.transcribe(pcm)

        self.assertEqual(text, "第一段。第二段。第三段。")
        self.assertEqual(transcribe_wav.call_count, 3)

    def test_chunk_seconds_is_capped_below_glm_asr_duration_limit(self):
        stt = _GLMASR2512STT({
            "api_key": "test-key",
            "chunk_seconds": 60,
        })
        pcm = b"\0" * (BYTES_PER_SECOND * 58)

        with patch.object(
            stt,
            "transcribe_wav",
            side_effect=["一", "二"],
        ) as transcribe_wav:
            text = stt.transcribe(pcm)

        self.assertEqual(text, "一二")
        self.assertEqual(transcribe_wav.call_count, 2)


class TranscriptionChunkJoinTests(unittest.TestCase):
    def test_join_inserts_space_only_between_ascii_words(self):
        self.assertEqual(
            _join_transcription_chunks(["hello", "world", "中文", "继续"]),
            "hello world中文继续",
        )


if __name__ == "__main__":
    unittest.main()
