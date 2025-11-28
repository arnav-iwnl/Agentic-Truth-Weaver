"""Text cleaning utilities for preprocessing stage."""
from typing import List


def basic_clean(text: str) -> str:
    """Very simple normalization; extend as needed."""
    return " ".join(text.strip().split())


def clean_corpus(texts: List[str]) -> List[str]:
    return [basic_clean(t) for t in texts]
