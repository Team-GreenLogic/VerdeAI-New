"""Auth dependency — re-exports from shared for gateway use."""

from verdeai_shared.auth.tenant import CurrentPrincipal, get_current_principal

__all__ = ["CurrentPrincipal", "get_current_principal"]
