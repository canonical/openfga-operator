# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for handling charm state."""

import functools
import json
from typing import TYPE_CHECKING, Any, Callable

from ops import Application, EventBase

if TYPE_CHECKING:
    from charm import OpenFGAOperatorCharm


def requires_state_setter(func: Callable) -> Callable:
    """Wrapper that makes sure peer state is ready and unit is the leader."""

    @functools.wraps(func)
    def wrapper(self: "OpenFGAOperatorCharm", event: EventBase) -> Any:
        if not self.unit.is_leader():
            return
        elif self._state.is_ready():
            return func(self, event)
        else:
            event.defer()
            return

    return wrapper


def requires_state(func: Callable) -> Callable:
    """Wrapper that makes sure peer state is ready."""

    @functools.wraps(func)
    def wrapper(self: "OpenFGAOperatorCharm", event: EventBase) -> Any:
        if self._state.is_ready():
            return func(self, event)
        else:
            event.defer()
            return

    return wrapper


class State:
    """A magic state that uses a relation as the data store.

    The get_relation callable is used to retrieve the relation.
    As relation data values must be strings, all values are JSON encoded.
    """

    def __init__(self, app: Application, get_relation: Callable) -> None:
        """Construct.

        Args:
            app: workload application
            get_relation: get peer relation method
        """
        # Use __dict__ to avoid calling __setattr__ and subsequent infinite recursion.
        self.__dict__["_app"] = app
        self.__dict__["_get_relation"] = get_relation

    def __setattr__(self, name: str, value: Any) -> None:
        """Set a value in the store with the given name.

        Args:
            name: name of value to set in store.
            value: value to set in store.
        """
        v = json.dumps(value)
        self._get_relation().data[self._app].update({name: v})

    def __getattr__(self, name: str) -> Any:
        """Get from the store the value with the given name, or None.

        Args:
            name: name of value to get from store.

        Returns:
            value from store with given name.
        """
        v = self._get_relation().data[self._app].get(name, "null")
        return json.loads(v)

    def __delattr__(self, name: str) -> None:
        """Delete the value with the given name from the store, if it exists.

        Args:
            name: name of value to delete from store.

        Returns:
            deleted value from store.
        """
        self._get_relation().data[self._app].pop(name, None)

    def is_ready(self) -> bool:
        """Report whether the relation is ready to be used.

        Returns:
            A boolean representing whether the relation is ready to be used or not.
        """
        return bool(self._get_relation())
