"""Lightweight compute capability detection."""

from __future__ import annotations


def _base_capabilities() -> dict:
    return {
        "current_default_device": "cpu",
        "cpu_available": True,
        "cuda_available": False,
        "cuda_version": None,
        "gpus": [],
        "torch_version": None,
        "cuda_error": None,
    }


def detect_device_capabilities(torch_module=None) -> dict:
    """Return JSON-serializable compute capabilities without loading models."""

    capabilities = _base_capabilities()
    if torch_module is None:
        try:
            import torch as torch_module
        except Exception as exc:
            capabilities["cuda_error"] = str(exc)
            return capabilities

    capabilities["torch_version"] = getattr(torch_module, "__version__", None)
    version = getattr(torch_module, "version", None)
    capabilities["cuda_version"] = getattr(version, "cuda", None)

    cuda = getattr(torch_module, "cuda", None)
    if cuda is None:
        return capabilities

    try:
        capabilities["cuda_available"] = bool(cuda.is_available())
    except Exception as exc:
        capabilities["cuda_error"] = str(exc)
        return capabilities

    if not capabilities["cuda_available"]:
        return capabilities

    try:
        device_count = int(cuda.device_count())
        for index in range(device_count):
            props = cuda.get_device_properties(index)
            capabilities["gpus"].append({
                "index": index,
                "name": getattr(props, "name", None),
                "total_memory_bytes": getattr(props, "total_memory", None),
            })
    except Exception as exc:
        capabilities["cuda_error"] = str(exc)

    return capabilities


def resolve_compute_device(
    requested_device: str | None = "auto",
    *,
    capabilities: dict | None = None,
    official_cpu_build: bool = True,
    torch_module=None,
) -> dict:
    """Resolve a requested compute device without changing runtime state."""

    requested = (requested_device or "auto").lower()
    if requested not in {"auto", "cpu", "cuda"}:
        requested = "auto"

    if capabilities is None:
        capabilities = detect_device_capabilities(torch_module)

    cuda_available = bool(capabilities.get("cuda_available"))
    resolved = "cpu"
    fallback_reason = None

    if official_cpu_build:
        fallback_reason = "official_cpu_build"
    elif requested == "auto":
        fallback_reason = "auto_defaults_to_cpu"
    elif requested == "cuda":
        if cuda_available:
            resolved = "cuda"
        else:
            fallback_reason = "cuda_unavailable"

    return {
        "requested_device": requested,
        "resolved_device": resolved,
        "cuda_available": cuda_available,
        "official_cpu_build": bool(official_cpu_build),
        "fallback_reason": fallback_reason,
    }
