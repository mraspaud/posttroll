"""Main module for the zmq backend."""
import logging
import os

import zmq

from posttroll import config

logger = logging.getLogger(__name__)
context = {}


def get_context():
    """Provide the context to use.

    This function takes care of creating new contexts in case of forks.
    """
    pid = os.getpid()
    if pid not in context:
        context[pid] = zmq.Context()
        logger.debug("renewed context for PID %d", pid)
    return context[pid]

def destroy_context(linger=None):
    """Destroy the context."""
    pid = os.getpid()
    context.pop(pid).destroy(linger)

def _set_tcp_keepalive(socket):
    """Set the tcp keepalive parameters on *socket*."""
    keepalive_options = get_tcp_keepalive_options()
    for param, value in keepalive_options.items():
        socket.setsockopt(param, value)

def get_tcp_keepalive_options():
    """Get the tcp_keepalive options from config."""
    keepalive_options = dict()
    for opt in ("tcp_keepalive",
                "tcp_keepalive_cnt",
                "tcp_keepalive_idle",
                "tcp_keepalive_intvl"):
        try:
            value = int(config[opt])
        except (KeyError, TypeError):
            continue
        param = getattr(zmq, opt.upper())
        keepalive_options[param] = value
    return keepalive_options
