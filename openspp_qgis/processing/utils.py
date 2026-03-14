# Part of OpenSPP. See LICENSE file for full copyright and licensing details.
"""Shared utilities for OpenSPP Processing algorithms."""


def fetch_variable_options(client, cached_names=None):
    """Fetch variable names from the server for Processing enum dropdowns.

    Uses the published statistics endpoint to discover available variables.
    Returns the cached list if already populated, or an empty list if the
    client is unavailable.

    Args:
        client: OpenSppClient instance (or None)
        cached_names: Previously fetched variable names (returned as-is if non-empty)

    Returns:
        List of variable name strings
    """
    if cached_names:
        return cached_names

    if not client:
        return []

    try:
        stats = client.get_published_statistics()
        names = []
        for category in stats.get("categories", []):
            for stat in category.get("statistics", []):
                name = stat.get("name", "")
                if name:
                    names.append(name)
        return names
    except Exception:
        return []
