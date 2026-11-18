import re
import zlib
from functools import lru_cache
from typing import List
import numpy as np


class LocalEmbeddingEngine:
    """
    Lightweight, 100% deterministic semantic embedding engine using subword
    character n-grams and CRC32 feature hashing with L2-normalized cosine distance.
    Deterministic across process restarts and executes in < 0.2ms per query.
    """

    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        words = [w for w in cleaned.split() if len(w) > 1]

        features = list(words)
        for w in words:
            wlen = len(w)
            if wlen >= 3:
                for i in range(wlen - 2):
                    features.append(w[i : i + 3])
            if wlen >= 4:
                for i in range(wlen - 3):
                    features.append(w[i : i + 4])
        return features

    @lru_cache(maxsize=1024)
    def _compute_normalized_vector(self, text: str) -> tuple:
        vec = np.zeros(self.dimension, dtype=np.float32)
        tokens = self._tokenize(text)
        if not tokens:
            return tuple(vec.tolist())

        dim = self.dimension
        for token in tokens:
            raw = token.encode("utf-8")
            h_val = zlib.crc32(raw) & 0xFFFFFFFF
            bucket = h_val % dim
            sign = 1.0 if ((h_val >> 16) & 1) == 0 else -1.0
            vec[bucket] += sign

        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec /= norm
        return tuple(vec.tolist())

    def get_embedding(self, text: str) -> List[float]:
        return list(self._compute_normalized_vector(text.strip()))

    def get_embedding_np(self, text: str) -> np.ndarray:
        return np.asarray(self._compute_normalized_vector(text.strip()), dtype=np.float32)

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        a = np.asarray(v1, dtype=np.float32)
        b = np.asarray(v2, dtype=np.float32)
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def batch_cosine_similarity(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        """Vectorized cosine similarity between L2-normalized query_vec (D,) and matrix (N, D)."""
        if matrix.size == 0:
            return np.empty(0, dtype=np.float32)
        return matrix @ query_vec


embedding_engine = LocalEmbeddingEngine()
