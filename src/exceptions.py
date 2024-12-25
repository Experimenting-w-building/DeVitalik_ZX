class ZerePyError(Exception):
    """Base exception for ZerePy errors"""
    pass

class AgentConfigError(ZerePyError):
    """Raised when there are issues with agent configuration"""
    pass

class ServiceError(ZerePyError):
    """Raised when a service encounters an error"""
    pass

class ConnectionError(ZerePyError):
    """Raised when there are connection issues"""
    pass 