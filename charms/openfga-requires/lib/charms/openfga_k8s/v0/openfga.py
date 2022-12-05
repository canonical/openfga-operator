"""TODO: Add a proper docstring here.

This is a placeholder docstring for this charm library. Docstrings are
presented on Charmhub and updated whenever you push a new version of the
library.

Complete documentation about creating and documenting libraries can be found
in the SDK docs at https://juju.is/docs/sdk/libraries.

See `charmcraft publish-lib` and `charmcraft fetch-lib` for details of how to
share and consume charm libraries. They serve to enhance collaboration
between charmers. Use a charmer's libraries for classes that handle
integration with their charm.

Bear in mind that new revisions of the different major API versions (v0, v1,
v2 etc) are maintained independently.  You can continue to update v0 and v1
after you have pushed v3.

Markdown is supported, following the CommonMark specification.
"""

import logging

from ops.charm import (
    CharmEvents,
    RelationChangedEvent,
    RelationEvent,
    RelationJoinedEvent,
)
from ops.framework import EventSource, Object

# The unique Charmhub library identifier, never change it
LIBID = "216f28cfeea4447b8a576f01bfbecdf5"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

logger = logging.getLogger(__name__)

RELATION_NAME = "openfga"


class OpenFGAEvent(RelationEvent):
    """Base class for OpenFGA events."""

    @property
    def store_id(self):
        return self.relation.data[self.relation.app].get("store-id")

    @property
    def token(self):
        return self.relation.data[self.relation.app].get("token")

    @property
    def address(self):
        return self.relation.data[self.relation.app].get("address")

    @property
    def scheme(self):
        return self.relation.data[self.relation.app].get("scheme")

    @property
    def port(self):
        return self.relation.data[self.relation.app].get("port")


class OpenFGAStoreCreateEvent(OpenFGAEvent):
    """
    Event emitted when a new OpenFGA store is created
    for use on this relation.
    """


class OpenFGAEvents(CharmEvents):
    """Custom charm events."""

    openfga_store_created = EventSource(OpenFGAStoreCreateEvent)


class OpenFGARequires(Object):
    """This class defines the functionality for the 'requires' side of the 'openfga' relation.

    Hook events observed:
        - relation-joined
        - relation-changed
    """

    on = OpenFGAEvents()

    def __init__(self, charm, store_name: str):
        super().__init__(charm, RELATION_NAME)

        self.framework.observe(
            charm.on[RELATION_NAME].relation_joined, self._on_relation_joined
        )
        self.framework.observe(
            charm.on[RELATION_NAME].relation_changed,
            self._on_relation_changed,
        )

        self.data = {}
        self.store_name = store_name

    def _on_relation_joined(self, event: RelationJoinedEvent):
        """Handle the relation-joined event."""
        # `self.unit` isn't available here, so use `self.model.unit`.
        if self.model.unit.is_leader():
            event.relation.data[self.model.app]["store-name"] = self.store_name

    def _on_relation_changed(self, event: RelationChangedEvent):
        """Handle the relation-changed event."""
        if self.model.unit.is_leader():
            self.on.openfga_store_created.emit(
                event.relation, app=event.app, unit=event.unit
            )
