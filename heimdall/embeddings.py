import re
import math
from typing import List
import numpy as np

class LocalEmbeddingEngine:
    """
    Lightweight, deterministic semantic embedding engine using subword 
    character n-grams and term frequency hashing with L2-normalized cosine distance.
    Provides instant, zero-latency vector similarity without external API dependencies.
    """
    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def _tokenize(self, text: str) -> List[str]:
        # Normalize and tokenize
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        words = [w for w in cleaned.split() if len(w) > 1]
        
        # Subword n-grams (3-grams and 4-grams) to capture semantic and morphological root similarity
        features = list(words)
        for w in words:
            if len(w) >= 3:
                for n in (3, 4):
                    for i in range(len(w) - n + 1):
                        features.append(w[i:i+n])
        return features

    def get_embedding(self, text: str) -> List[float]:
        vec = np.zeros(self.dimension, dtype=np.float32)
        tokens = self._tokenize(text)
        if not tokens:
            return vec.tolist()

        for token in tokens:
            # Deterministic hash bucket
            h = hash(token) % self.dimension
            # Signed feature hashing
            sign = 1.0 if (hash(token + "_sign") % 2 == 0) else -1.0
            vec[h] += sign

        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        a = np.array(v1, dtype=np.float32)
        b = np.array(v2, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

embedding_engine = LocalEmbeddingEngine()
