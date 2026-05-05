"""Rule implementations. Importing this package registers every rule.

Add a new rule by creating a module and decorating its impl with
``@register("SURFACE.SHORT_NAME")`` from :mod:`finops_assess.engine`. The id
must match the YAML rule definition under ``data/rules/``.
"""

from finops_assess.rules_impl import ado_rules, azure_rules, github_rules, m365_rules  # noqa: F401

__all__: list[str] = []
