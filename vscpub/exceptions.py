class VscpubError(Exception):
    pass


class ConfigError(VscpubError):
    pass


class ApiError(VscpubError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")
