import numpy as np

from reachy_mini_conversation_app.audio.resampling import AudioResampler


def test_streaming_conversion_preserves_duration_and_chunk_continuity() -> None:
    """Chunk boundaries do not alter the resampled signal."""
    samples = (np.sin(np.arange(24000) * 2 * np.pi * 440 / 24000) * 10000).astype(np.int16)
    whole = AudioResampler(24000, 16000)
    expected = whole.process(samples, final=True)
    chunked = AudioResampler(24000, 16000)
    actual = np.concatenate(
        [chunked.process(chunk, final=index == 9) for index, chunk in enumerate(np.split(samples, 10))]
    )
    assert len(actual) == 16000
    np.testing.assert_allclose(actual, expected, atol=2, rtol=0)


def test_reset_discards_previous_audio_and_equal_rate_is_unchanged() -> None:
    """An interrupted turn cannot leak converter history into the next turn."""
    converter = AudioResampler(24000, 16000)
    converter.process(np.full(200, 10000, dtype=np.int16))
    converter.reset()
    silent = converter.process(np.zeros(2400, dtype=np.int16), final=True)
    assert not np.any(silent)
    samples = np.arange(200, dtype=np.int16)
    np.testing.assert_array_equal(AudioResampler(16000, 16000).process(samples), samples)
