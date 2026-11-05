import re


def normalize_kubernetes_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9-]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    normalized = normalized[:63].rstrip("-")
    if len(normalized) < 2:
        raise ValueError("Kubernetes names must contain at least two valid characters.")
    return normalized
