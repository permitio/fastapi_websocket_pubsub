class PubSubException(Exception):
    pass


class PubSubClientException(Exception):
    pass


class PubSubClientInvalidStateException(PubSubClientException):
    """
    Raised when an operation is attempted on an PubSubClient which isn't in the right state.
    Common examples - trying to publish events before conencting; trying to subscribe after connection is established.
    """
    pass
