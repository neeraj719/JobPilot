"""Cross-module primitives: pagination + generic response envelopes."""
from app.modules.common.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Pagination,
    count_stmt,
    paginate,
    paginate_sequence,
)
from app.modules.common.schemas import CountResponse, ErrorBody, ErrorResponse, OkResponse, PageResponse

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "Pagination",
    "count_stmt",
    "paginate",
    "paginate_sequence",
    "PageResponse",
    "OkResponse",
    "CountResponse",
    "ErrorBody",
    "ErrorResponse",
]
