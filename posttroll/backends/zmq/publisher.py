"""ZMQ implementation of the publisher."""

import logging
from threading import Lock
from urllib.parse import urlsplit, urlunsplit

import zmq
from zmq.auth.thread import ThreadAuthenticator

from posttroll.backends.zmq import _set_tcp_keepalive, get_context

LOGGER = logging.getLogger(__name__)


class UnsecureZMQPublisher:
    """Unsecure ZMQ implementation of the publisher class."""

    def __init__(self, address, name="", min_port=None, max_port=None):
        """Set up the publisher.

        Args:
            address: the address to connect to.
            name: the name of this publishing service.
            min_port: the minimal port number to use.
            max_port: the maximal port number to use.

        """
        self.name = name
        self.destination = address
        self.publish_socket = None
        self.min_port = min_port
        self.max_port = max_port
        self.port_number = None
        self._pub_lock = Lock()

    def start(self):
        """Start the publisher."""
        self.publish_socket = get_context().socket(zmq.PUB)
        _set_tcp_keepalive(self.publish_socket)

        self._bind()
        LOGGER.info(f"Publisher for {self.destination} started on port {self.port_number}.")
        return self

    def _bind(self):
        # Check for port 0 (random port)
        u__ = urlsplit(self.destination)
        port = u__.port
        if port == 0:
            dest = urlunsplit((u__.scheme, u__.hostname,
                               u__.path, u__.query, u__.fragment))
            self.port_number = self.publish_socket.bind_to_random_port(
                dest,
                min_port=self.min_port,
                max_port=self.max_port)
            netloc = u__.hostname + ":" + str(self.port_number)
            self.destination = urlunsplit((u__.scheme, netloc, u__.path,
                                           u__.query, u__.fragment))
        else:
            self.publish_socket.bind(self.destination)
            self.port_number = port

    def send(self, msg):
        """Send the given message."""
        with self._pub_lock:
            self.publish_socket.send_string(msg)

    def stop(self):
        """Stop the publisher."""
        self.publish_socket.setsockopt(zmq.LINGER, 1)
        self.publish_socket.close()


class SecureZMQPublisher(UnsecureZMQPublisher):
    """Secure ZMQ implementation of the publisher class."""

    def __init__(self, *args, server_secret_key=None, public_keys_directory=None, authorized_sub_addresses=None, **kwargs):  # noqa
        """Set up the secure ZMQ publisher.

        Args:
            address: the address to connect to.
            server_secret_key: the secret key for this publisher.
            public_keys_directory: the directory containing the public keys of the subscribers that are allowed to
                connect.
            authorized_sub_addresses: the list of addresse allowed to subscibe to this publisher. By default, all are
                allowed.
            kwargs: passed to the underlying UnsecureZMQPublisher instance.

        """
        if server_secret_key is None:
            raise TypeError("Missing server_secret_key argument.")
        if public_keys_directory is None:
            raise TypeError("Missing public_keys_directory argument.")
        self._server_secret_key = server_secret_key
        self._authorized_sub_addresses = authorized_sub_addresses or []
        self._pub_keys_dir = public_keys_directory
        self._authenticator = None

        super().__init__(*args, **kwargs)

    def start(self):
        """Start the publisher."""
        ctx = get_context()

        # Start an authenticator for this context.
        auth = ThreadAuthenticator(ctx)
        auth.start()
        auth.allow(*self._authorized_sub_addresses)
        # Tell authenticator to use the certificate in a directory
        auth.configure_curve(domain="*", location=self._pub_keys_dir)
        self._authenticator = auth

        self.publish_socket = ctx.socket(zmq.PUB)

        server_public, server_secret =zmq.auth.load_certificate(self._server_secret_key)
        self.publish_socket.curve_secretkey = server_secret
        self.publish_socket.curve_publickey = server_public
        self.publish_socket.curve_server = True

        _set_tcp_keepalive(self.publish_socket)

        self._bind()
        LOGGER.info(f"Publisher for {self.destination} started on port {self.port_number}.")
        return self

    def stop(self):
        """Stop the publisher."""
        super().stop()
        self._authenticator.stop()
