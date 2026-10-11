import logging

from bookmarks.services import http_client
from bookmarks.services.website_loader import fake_request_headers

logger = logging.getLogger(__name__)

# Source expressions in frame-ancestors that allow any origin to embed the page.
# Host sources and 'self' are treated as blocking, as the origin that embeds the
# page is not known when checking.
_OPEN_FRAME_ANCESTOR_SOURCES = {"*", "http:", "https:"}


def _frame_ancestors_allow_embedding(policy_header: str) -> bool | None:
    """
    Evaluates the frame-ancestors directive of a Content-Security-Policy header.
    Returns None if the header does not contain such a directive.
    """
    result = None
    # Multiple policies are combined by joining them with a comma, an embedder
    # must satisfy all of them
    for policy in policy_header.split(","):
        for directive in policy.split(";"):
            tokens = directive.strip().split()
            if not tokens or tokens[0].lower() != "frame-ancestors":
                continue
            sources = {token.lower() for token in tokens[1:]}
            allowed = bool(sources & _OPEN_FRAME_ANCESTOR_SOURCES)
            result = allowed if result is None else result and allowed
            # Only the first occurrence of a directive in a policy counts
            break
    return result


def headers_allow_embedding(headers) -> bool:
    # If a CSP frame-ancestors directive is present, browsers ignore X-Frame-Options
    frame_ancestors = _frame_ancestors_allow_embedding(
        headers.get("Content-Security-Policy", "")
    )
    if frame_ancestors is not None:
        return frame_ancestors

    # Any value, DENY, SAMEORIGIN or the obsolete ALLOW-FROM, restricts embedding
    return not headers.get("X-Frame-Options", "").strip()


def check_embeddable(url: str) -> bool | None:
    """
    Checks whether a page allows being embedded in an iframe of another origin,
    based on its response headers. Returns None if that could not be determined.
    """
    try:
        with http_client.get(
            url, timeout=10, headers=fake_request_headers(), stream=True
        ) as response:
            # Streaming without reading the body, only the headers are needed
            if response.status_code >= 400:
                logger.debug(
                    f"Bad response status code for embed check: {url} status_code={response.status_code}"
                )
                return None
            return headers_allow_embedding(response.headers)
    except http_client.RequestException as error:
        logger.debug(f"Failed to check if page is embeddable: {url}", exc_info=error)
        return None
