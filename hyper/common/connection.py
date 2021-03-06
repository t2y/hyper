# -*- coding: utf-8 -*-
"""
hyper/common/connection
~~~~~~~~~~~~~~~~~~~~~~~

Hyper's HTTP/1.1 and HTTP/2 abstraction layer.
"""
from .exceptions import TLSUpgrade
from ..http11.connection import HTTP11Connection
from ..http20.connection import HTTP20Connection
from ..tls import H2_NPN_PROTOCOLS


class HTTPConnection(object):
    """
    An object representing a single HTTP connection to a server.

    This object behaves similarly to the Python standard library's
    ``HTTPConnection`` object, with a few critical differences.

    Most of the standard library's arguments to the constructor are not
    supported by hyper. Most optional parameters apply to *either* HTTP/1.1 or
    HTTP/2.

    :param host: The host to connect to. This may be an IP address or a
        hostname, and optionally may include a port: for example,
        ``'http2bin.org'``, ``'http2bin.org:443'`` or ``'127.0.0.1'``.
    :param port: (optional) The port to connect to. If not provided and one also
        isn't provided in the ``host`` parameter, defaults to 443.
    :param secure: (optional, HTTP/1.1 only) Whether the request should use
        TLS. Defaults to ``False`` for most requests, but to ``True`` for any
        request issued to port 443.
    :param window_manager: (optional) The class to use to manage flow control
        windows. This needs to be a subclass of the
        :class:`BaseFlowControlManager <hyper.http20.window.BaseFlowControlManager>`.
        If not provided,
        :class:`FlowControlManager <hyper.http20.window.FlowControlManager>`
        will be used.
    :param enable_push: (optional) Whether the server is allowed to push
        resources to the client (see
        :meth:`get_pushes() <hyper.HTTP20Connection.get_pushes>`).
    """
    def __init__(self,
                 host,
                 port=None,
                 secure=None,
                 window_manager=None,
                 enable_push=False,
                 **kwargs):

        self._host = host
        self._port = port
        self._h1_kwargs = {'secure': secure}
        self._h2_kwargs = {
            'window_manager': window_manager, 'enable_push': enable_push
        }

        # Add any unexpected kwargs to both dictionaries.
        self._h1_kwargs.update(kwargs)
        self._h2_kwargs.update(kwargs)

        self._conn = HTTP11Connection(
            self._host, self._port, **self._h1_kwargs
        )

    def request(self, method, url, body=None, headers={}):
        """
        This will send a request to the server using the HTTP request method
        ``method`` and the selector ``url``. If the ``body`` argument is
        present, it should be string or bytes object of data to send after the
        headers are finished. Strings are encoded as UTF-8. To use other
        encodings, pass a bytes object. The Content-Length header is set to the
        length of the body field.

        :param method: The request method, e.g. ``'GET'``.
        :param url: The URL to contact, e.g. ``'/path/segment'``.
        :param body: (optional) The request body to send. Must be a bytestring
            or a file-like object.
        :param headers: (optional) The headers to send on the request.
        :returns: A stream ID for the request, or ``None`` if the request is
            made over HTTP/1.1.
        """
        try:
            return self._conn.request(
                method=method, url=url, body=body, headers=headers
            )
        except TLSUpgrade as e:
            # We upgraded in the NPN/ALPN handshake. We can just go straight to
            # the world of HTTP/2. Replace the backing object and insert the
            # socket into it.
            assert e.negotiated in H2_NPN_PROTOCOLS

            self._conn = HTTP20Connection(
                self._host, self._port, **self._h2_kwargs
            )
            self._conn._sock = e.sock

            # Because we skipped the connecting logic, we need to send the
            # HTTP/2 preamble.
            self._conn._send_preamble()

            return self._conn.request(
                method=method, url=url, body=body, headers=headers
            )

    # Can anyone say 'proxy object pattern'?
    def __getattr__(self, name):
        return getattr(self._conn, name)
