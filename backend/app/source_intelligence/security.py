from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlsplit

import httpx

Resolver = Callable[[str], list[str]]


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
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _connected_peer_address(response: httpx.Response) -> str | None:
    stream = response.extensions.get("network_stream")
    get_extra_info = getattr(stream, "get_extra_info", None)
    if not callable(get_extra_info):
        return None

    server_addr = get_extra_info("server_addr")
    if isinstance(server_addr, tuple) and server_addr:
        return str(server_addr[0])
    if isinstance(server_addr, str):
        return server_addr

    network_socket = get_extra_info("socket")
    get_peer_name = getattr(network_socket, "getpeername", None)
    if callable(get_peer_name):
        peer = get_peer_name()
        if isinstance(peer, tuple) and peer:
            return str(peer[0])
        if isinstance(peer, str):
            return peer
    return None


def validate_connected_peer(response: httpx.Response) -> None:
    address = _connected_peer_address(response)
    if address is None:
        raise SourceFetchError("source connection peer address could not be verified")
    if not _is_public_address(address):
        raise UnsafeSourceUrl("source connection reached a non-public address")


def validate_source_url(url: str, *, resolver: Resolver = system_resolver) -> None:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
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
        raise UnsafeSourceUrl("source URL resolves to a non-public address")


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
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.resolver = resolver
        self.transport = transport

    @staticmethod
    def _filename_for_url(url: str) -> str:
        path = urlsplit(url).path
        name = unquote(path.rsplit("/", 1)[-1]) if path else ""
        return name or "downloaded-source.bin"

    def fetch(self, url: str) -> FetchedSource:
        current = url
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
                        if self.transport is None:
                            validate_connected_peer(response)
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if redirect_count >= self.max_redirects:
                                raise SourceFetchError("source URL exceeded redirect limit")
                            location = response.headers.get("location")
                            if not location:
                                raise SourceFetchError("source redirect did not include Location")
                            current = urljoin(current, location)
                            continue

                        try:
                            response.raise_for_status()
                        except httpx.HTTPStatusError as exc:
                            raise SourceFetchError(
                                f"source URL returned HTTP {response.status_code}"
                            ) from exc

                        declared_length = response.headers.get("content-length")
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
                        for chunk in response.iter_bytes():
                            total += len(chunk)
                            if total > self.max_bytes:
                                raise SourceFetchError("source exceeds configured size limit")
                            chunks.append(chunk)

                        content_type = response.headers.get(
                            "content-type",
                            "application/octet-stream",
                        ).split(";", 1)[0].strip().lower()
                        return FetchedSource(
                            content=b"".join(chunks),
                            final_url=str(response.url),
                            content_type=content_type,
                            filename=self._filename_for_url(str(response.url)),
                        )
                except httpx.HTTPError as exc:
                    raise SourceFetchError("source URL retrieval failed") from exc

        raise SourceFetchError("source URL retrieval did not complete")
