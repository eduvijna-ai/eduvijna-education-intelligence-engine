from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx

Resolver = Callable[[str], list[str]]
ConnectionFactory = Callable[
    [str, str, int, float],
    http.client.HTTPConnection,
]


class UnsafeSourceUrl(ValueError):
    pass


class SourceFetchError(RuntimeError):
    pass


def system_resolver(hostname: str) -> list[str]:
    addresses: list[str] = []
    for entry in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM):
        address = str(entry[4][0])
        if address not in addresses:
            addresses.append(address)
    return addresses


def _is_public_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def _validated_addresses(
    url: str,
    *,
    resolver: Resolver,
) -> tuple[str, str, int, list[str]]:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeSourceUrl("source URL must use http or https")
    if not parsed.hostname:
        raise UnsafeSourceUrl("source URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeSourceUrl("source URL must not contain embedded credentials")

    hostname = parsed.hostname.rstrip(".").lower()
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
        or hostname.endswith(".home.arpa")
    ):
        raise UnsafeSourceUrl("source URL hostname is not public")

    try:
        direct_ip = ipaddress.ip_address(hostname)
    except ValueError:
        direct_ip = None

    addresses = [str(direct_ip)] if direct_ip is not None else resolver(hostname)
    if not addresses:
        raise UnsafeSourceUrl("source URL hostname did not resolve")
    if any(not _is_public_address(address) for address in addresses):
        raise UnsafeSourceUrl("source URL resolves to a non-global address")

    port = parsed.port or (443 if scheme == "https" else 80)
    return scheme, hostname, port, addresses


def validate_source_url(url: str, *, resolver: Resolver = system_resolver) -> None:
    _validated_addresses(url, resolver=resolver)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        hostname: str,
        pinned_ip: str,
        port: int,
        timeout: float,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        hostname: str,
        pinned_ip: str,
        port: int,
        timeout: float,
    ) -> None:
        super().__init__(
            hostname,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            sock = self.sock
        self.sock = self._context.wrap_socket(
            sock,
            server_hostname=self.host,
        )


def pinned_connection_factory(
    scheme: str,
    hostname: str,
    port: int,
    timeout: float,
    *,
    pinned_ip: str,
) -> http.client.HTTPConnection:
    if scheme == "https":
        return _PinnedHTTPSConnection(hostname, pinned_ip, port, timeout)
    return _PinnedHTTPConnection(hostname, pinned_ip, port, timeout)


@dataclass(frozen=True, slots=True)
class FetchedSource:
    content: bytes
    final_url: str
    content_type: str
    filename: str


class SourceUrlFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_bytes: int,
        max_redirects: int,
        resolver: Resolver = system_resolver,
        transport: httpx.BaseTransport | None = None,
        connection_factory: Callable[
            [str, str, int, float, str],
            http.client.HTTPConnection,
        ]
        | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.resolver = resolver
        self.transport = transport
        self.connection_factory = connection_factory

    @staticmethod
    def _filename_for_url(url: str) -> str:
        path = urlsplit(url).path
        name = unquote(path.rsplit("/", 1)[-1]) if path else ""
        return name or "downloaded-source.bin"

    def _read_bounded_http_response(
        self,
        response: http.client.HTTPResponse,
    ) -> bytes:
        declared_length = response.getheader("content-length")
        if declared_length is not None:
            try:
                if int(declared_length) > self.max_bytes:
                    raise SourceFetchError("source exceeds configured size limit")
            except ValueError as exc:
                raise SourceFetchError(
                    "source returned an invalid Content-Length"
                ) from exc

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(65536, self.max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > self.max_bytes:
                raise SourceFetchError("source exceeds configured size limit")
            chunks.append(chunk)
        return b"".join(chunks)

    def _fetch_real(self, url: str) -> FetchedSource:
        current = url
        for redirect_count in range(self.max_redirects + 1):
            scheme, hostname, port, addresses = _validated_addresses(
                current,
                resolver=self.resolver,
            )
            pinned_ip = addresses[0]
            parsed = urlsplit(current)
            request_target = urlunsplit(
                (
                    "",
                    "",
                    parsed.path or "/",
                    parsed.query,
                    "",
                )
            )
            host_header = hostname
            if (scheme, port) not in {("http", 80), ("https", 443)}:
                host_header = f"{hostname}:{port}"

            if self.connection_factory is not None:
                connection = self.connection_factory(
                    scheme,
                    hostname,
                    port,
                    self.timeout_seconds,
                    pinned_ip,
                )
            else:
                connection = pinned_connection_factory(
                    scheme,
                    hostname,
                    port,
                    self.timeout_seconds,
                    pinned_ip=pinned_ip,
                )

            try:
                connection.request(
                    "GET",
                    request_target,
                    headers={
                        "Host": host_header,
                        "User-Agent": "Eduvijna-Source-Intelligence/1.0",
                        "Accept": "*/*",
                        "Connection": "close",
                    },
                )
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    if redirect_count >= self.max_redirects:
                        raise SourceFetchError("source URL exceeded redirect limit")
                    location = response.getheader("location")
                    if not location:
                        raise SourceFetchError(
                            "source redirect did not include Location"
                        )
                    current = urljoin(current, location)
                    continue
                if response.status >= 400:
                    raise SourceFetchError(
                        f"source URL returned HTTP {response.status}"
                    )
                content = self._read_bounded_http_response(response)
                content_type = (
                    response.getheader(
                        "content-type",
                        "application/octet-stream",
                    )
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                return FetchedSource(
                    content=content,
                    final_url=current,
                    content_type=content_type,
                    filename=self._filename_for_url(current),
                )
            except (OSError, http.client.HTTPException) as exc:
                raise SourceFetchError("source URL retrieval failed") from exc
            finally:
                connection.close()

        raise SourceFetchError("source URL retrieval did not complete")

    def _fetch_mocked(self, url: str) -> FetchedSource:
        current = url
        assert self.transport is not None
        with httpx.Client(
            follow_redirects=False,
            timeout=self.timeout_seconds,
            transport=self.transport,
            headers={"user-agent": "Eduvijna-Source-Intelligence/1.0"},
            trust_env=False,
        ) as client:
            for redirect_count in range(self.max_redirects + 1):
                validate_source_url(current, resolver=self.resolver)
                try:
                    with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if redirect_count >= self.max_redirects:
                                raise SourceFetchError(
                                    "source URL exceeded redirect limit"
                                )
                            location = response.headers.get("location")
                            if not location:
                                raise SourceFetchError(
                                    "source redirect did not include Location"
                                )
                            current = urljoin(current, location)
                            continue
                        try:
                            response.raise_for_status()
                        except httpx.HTTPStatusError as exc:
                            raise SourceFetchError(
                                f"source URL returned HTTP {response.status_code}"
                            ) from exc

                        content = b"".join(response.iter_bytes())
                        if len(content) > self.max_bytes:
                            raise SourceFetchError(
                                "source exceeds configured size limit"
                            )
                        return FetchedSource(
                            content=content,
                            final_url=str(response.url),
                            content_type=response.headers.get(
                                "content-type",
                                "application/octet-stream",
                            )
                            .split(";", 1)[0]
                            .strip()
                            .lower(),
                            filename=self._filename_for_url(str(response.url)),
                        )
                except httpx.HTTPError as exc:
                    raise SourceFetchError("source URL retrieval failed") from exc
        raise SourceFetchError("source URL retrieval did not complete")

    def fetch(self, url: str) -> FetchedSource:
        if self.transport is not None:
            return self._fetch_mocked(url)
        return self._fetch_real(url)
