"""Action registry — lookup and discovery of ActionDefs."""

from actflow.schema.action_def import ActionDef


class Registry:
    """In-memory ActionDef registry.

    In future phases this will be backed by a community-contributed
    Schema Registry (actionflow-schema.org).
    """

    def __init__(self):
        self._actions: dict[str, ActionDef] = {}

    def register(self, action: ActionDef) -> "Registry":
        key = f"{action.domain}/{action.name}@{action.version}"
        self._actions[key] = action
        return self

    def get(self, name: str, domain: str = "default", version: str | None = None) -> ActionDef | None:
        if version:
            return self._actions.get(f"{domain}/{name}@{version}")
        candidates = [
            v for k, v in self._actions.items()
            if k.startswith(f"{domain}/{name}@")
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x.version, reverse=True)
        return candidates[0]

    def list_domains(self) -> list[str]:
        domains: set[str] = set()
        for k in self._actions:
            domains.add(k.split("/")[0])
        return sorted(domains)

    def list_actions(self, domain: str | None = None) -> list[str]:
        names: list[str] = []
        for k in self._actions:
            d, rest = k.split("/", 1)
            if domain is None or d == domain:
                names.append(rest.split("@")[0])
        return sorted(set(names))


registry = Registry()
