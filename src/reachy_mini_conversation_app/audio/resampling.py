import soxr
import numpy as np
from numpy.typing import NDArray


class AudioResampler:
    """Convert successive mono PCM16 chunks without losing filter history."""

    def __init__(self, input_rate: int, output_rate: int) -> None:
        """Initialize conversion between positive sample rates."""
        if input_rate <= 0 or output_rate <= 0:
            raise ValueError("Sample rates must be positive")
        self.input_rate = input_rate
        self.output_rate = output_rate
        self._stream = soxr.ResampleStream(input_rate, output_rate, 1, dtype="float32")

    def process(self, samples: NDArray[np.int16], *, final: bool = False) -> NDArray[np.int16]:
        """Convert a chunk, optionally draining the end of a normal turn."""
        if self.input_rate == self.output_rate:
            return samples
        converted = np.asarray(
            self._stream.resample_chunk(samples.reshape(-1).astype(np.float32), last=final), dtype=np.float32
        )
        if final:
            self.reset()
        return np.clip(np.rint(converted), -32768, 32767).astype(np.int16)

    def reset(self) -> None:
        """Discard delayed samples belonging to an abandoned turn."""
        self._stream = soxr.ResampleStream(self.input_rate, self.output_rate, 1, dtype="float32")
