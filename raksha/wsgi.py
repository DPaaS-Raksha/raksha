# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Utility methods for working with WSGI servers."""

import errno
import os
import socket
import ssl
import sys
import time

import eventlet
import eventlet.wsgi
import greenlet
from oslo.config import cfg
from paste import deploy
import routes.middleware
import webob.dec
import webob.exc

from raksha import exception
from raksha import flags
from raksha.openstack.common import log as logging
from raksha import utils

socket_opts = [
    cfg.IntOpt('backlog',
               default=4096,
               help="Number of backlog requests to configure the socket with"),
    cfg.IntOpt('tcp_keepidle',
               default=600,
               help="Sets the value of TCP_KEEPIDLE in seconds for each "
                    "server socket. Not supported on OS X."),
    cfg.StrOpt('ssl_ca_file',
               default=None,
               help="CA certificate file to use to verify "
                    "connecting clients"),
    cfg.StrOpt('ssl_cert_file',
               default=None,
               help="Certificate file to use when starting "
                    "the server securely"),
    cfg.StrOpt('ssl_key_file',
               default=None,
               help="Private key file to use when starting "
                    "the server securely"),
]

CONF = cfg.CONF
CONF.register_opts(socket_opts)

FLAGS = flags.FLAGS
LOG = logging.getLogger(__name__)


class Server(object):
    """Server class to manage a WSGI server, serving a WSGI application."""

    default_pool_size = 1000

    def __init__(self, name, app, host=None, port=None, pool_size=None,
                 protocol=eventlet.wsgi.HttpProtocol):
        """Initialize, but do not start, a WSGI server.

        :param name: Pretty name for logging.
        :param app: The WSGI application to serve.
        :param host: IP address to serve the application.
        :param port: Port number to server the application.
        :param pool_size: Maximum number of eventlets to spawn concurrently.
        :returns: None

        """
        self.name = name
        self.app = app
        self._host = host or "0.0.0.0"
        self._port = port or 0
        self._server = None
        self._socket = None
        self._protocol = protocol
        self._pool = eventlet.GreenPool(pool_size or self.default_pool_size)
        self._logger = logging.getLogger("eventlet.wsgi.server")
        self._wsgi_logger = logging.WritableLogger(self._logger)

    def _get_socket(self, host, port, backlog):
        bind_addr = (host, port)
        # TODO(dims): eventlet's green dns/socket module does not actually
        # support IPv6 in getaddrinfo(). We need to get around this in the
        # future or monitor upstream for a fix
        try:
            info = socket.getaddrinfo(bind_addr[0],
                                      bind_addr[1],
                                      socket.AF_UNSPEC,
                                      socket.SOCK_STREAM)[0]
            family = info[0]
            bind_addr = info[-1]
        except Exception:
            family = socket.AF_INET

        cert_file = CONF.ssl_cert_file
        key_file = CONF.ssl_key_file
        ca_file = CONF.ssl_ca_file
        use_ssl = cert_file or key_file

        if cert_file and not os.path.exists(cert_file):
            raise RuntimeError(_("Unable to find cert_file : %s") % cert_file)

        if ca_file and not os.path.exists(ca_file):
            raise RuntimeError(_("Unable to find ca_file : %s") % ca_file)

        if key_file and not os.path.exists(key_file):
            raise RuntimeError(_("Unable to find key_file : %s") % key_file)

        if use_ssl and (not cert_file or not key_file):
            raise RuntimeError(_("When running server in SSL mode, you must "
                                 "specify both a cert_file and key_file "
                                 "option value in your configuration file"))

        def wrap_ssl(sock):
            ssl_kwargs = {
                'server_side': True,
                'certfile': cert_file,
                'keyfile': key_file,
                'cert_reqs': ssl.CERT_NONE,
            }

            if CONF.ssl_ca_file:
                ssl_kwargs['ca_certs'] = ca_file
                ssl_kwargs['cert_reqs'] = ssl.CERT_REQUIRED

            return ssl.wrap_socket(sock, **ssl_kwargs)

        sock = None
        retry_until = time.time() + 30
        while not sock and time.time() < retry_until:
            try:
                sock = eventlet.listen(bind_addr,
                                       backlog=backlog,
                                       family=family)
                if use_ssl:
                    sock = wrap_ssl(sock)

            except socket.error, err:
                if err.args[0] != errno.EADDRINUSE:
                    raise
                eventlet.sleep(0.1)
        if not sock:
            raise RuntimeError(_("Could not bind to %(host)s:%(port)s "
                               "after trying for 30 seconds") %
                               {'host': host, 'port': port})
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # sockets can hang around forever without keepalive
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        # This option isn't available in the OS X version of eventlet
        if hasattr(socket, 'TCP_KEEPIDLE'):
            sock.setsockopt(socket.IPPROTO_TCP,
                            socket.TCP_KEEPIDLE,
                            CONF.tcp_keepidle)

        return sock

    def _start(self):
        """Run the blocking eventlet WSGI server.

        :returns: None

        """
        eventlet.wsgi.server(self._socket,
                             self.app,
                             protocol=self._protocol,
                             custom_pool=self._pool,
                             log=self._wsgi_logger)

    def start(self, backlog=128):
        """Start serving a WSGI application.

        :param backlog: Maximum number of queued connections.
        :returns: None
        :raises: raksha.exception.InvalidInput

        """
        if backlog < 1:
            raise exception.InvalidInput(
                reason='The backlog must be more than 1')

        self._socket = self._get_socket(self._host,
                                        self._port,
                                        backlog=backlog)
        self._server = eventlet.spawn(self._start)
        (self._host, self._port) = self._socket.getsockname()[0:2]
        LOG.info(_("Started %(name)s on %(_host)s:%(_port)s") % self.__dict__)

    @property
    def host(self):
        return self._host

    @property
    def port(self):
        return self._port

    def stop(self):
        """Stop this server.

        This is not a very nice action, as currently the method by which a
        server is stopped is by killing its eventlet.

        :returns: None

        """
        LOG.info(_("Stopping WSGI server."))
        self._server.kill()

    def wait(self):
        """Block, until the server has stopped.

        Waits on the server's eventlet to finish, then returns.

        :returns: None

        """
        try:
            self._server.wait()
        except greenlet.GreenletExit:
            LOG.info(_("WSGI server has stopped."))


class Request(webob.Request):
    pass


class Application(object):
    """Base WSGI application wrapper. Subclasses need to implement __call__."""

    @classmethod
    def factory(cls, global_config, **local_config):
        """Used for paste app factories in paste.deploy config files.

        Any local configuration (that is, values under the [app:APPNAME]
        section of the paste config) will be passed into the `__init__` method
        as kwargs.

        A hypothetical configuration would look like:

            [app:wadl]
            latest_version = 1.3
            paste.app_factory = raksha.api.fancy_api:Wadl.factory

        which would result in a call to the `Wadl` class as

            import raksha.api.fancy_api
            fancy_api.Wadl(latest_version='1.3')

        You could of course re-implement the `factory` method in subclasses,
        but using the kwarg passing it shouldn't be necessary.

        """
        return cls(**local_config)

    def __call__(self, environ, start_response):
        r"""Subclasses will probably want to implement __call__ like this:

        @webob.dec.wsgify(RequestClass=Request)
        def __call__(self, req):
          # Any of the following objects work as responses:

          # Option 1: simple string
          res = 'message\n'

          # Option 2: a nicely formatted HTTP exception page
          res = exc.HTTPForbidden(detail='Nice try')

          # Option 3: a webob Response object (in case you need to play with
          # headers, or you want to be treated like an iterable, or or or)
          res = Response();
          res.app_iter = open('somefile')

          # Option 4: any wsgi app to be run next
          res = self.application

          # Option 5: you can get a Response object for a wsgi app, too, to
          # play with headers etc
          res = req.get_response(self.application)

          # You can then just return your response...
          return res
          # ... or set req.response and return None.
          req.response = res

        See the end of http://pythonpaste.org/webob/modules/dec.html
        for more info.

        """
        raise NotImplementedError(_('You must implement __call__'))


class Middleware(Application):
    """Base WSGI middleware.

    These classes require an application to be
    initialized that will be called next.  By default the middleware will
    simply call its wrapped app, or you can override __call__ to customize its
    behavior.

    """

    @classmethod
    def factory(cls, global_config, **local_config):
        """Used for paste app factories in paste.deploy config files.

        Any local configuration (that is, values under the [filter:APPNAME]
        section of the paste config) will be passed into the `__init__` method
        as kwargs.

        A hypothetical configuration would look like:

            [filter:analytics]
            redis_host = 127.0.0.1
            paste.filter_factory = raksha.api.analytics:Analytics.factory

        which would result in a call to the `Analytics` class as

            import raksha.api.analytics
            analytics.Analytics(app_from_paste, redis_host='127.0.0.1')

        You could of course re-implement the `factory` method in subclasses,
        but using the kwarg passing it shouldn't be necessary.

        """
        def _factory(app):
            return cls(app, **local_config)
        return _factory

    def __init__(self, application):
        self.application = application

    def process_request(self, req):
        """Called on each request.

        If this returns None, the next application down the stack will be
        executed. If it returns a response then that response will be returned
        and execution will stop here.

        """
        return None

    def process_response(self, response):
        """Do whatever you'd like to the response."""
        return response

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, req):
        response = self.process_request(req)
        if response:
            return response
        response = req.get_response(self.application)
        return self.process_response(response)


class Debug(Middleware):
    """Helper class for debugging a WSGI application.

    Can be inserted into any WSGI application chain to get information
    about the request and response.

    """

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, req):
        print ('*' * 40) + ' REQUEST ENVIRON'
        for key, value in req.environ.items():
            print key, '=', value
        print
        resp = req.get_response(self.application)

        print ('*' * 40) + ' RESPONSE HEADERS'
        for (key, value) in resp.headers.iteritems():
            print key, '=', value
        print

        resp.app_iter = self.print_generator(resp.app_iter)

        return resp

    @staticmethod
    def print_generator(app_iter):
        """Iterator that prints the contents of a wrapper string."""
        print ('*' * 40) + ' BODY'
        for part in app_iter:
            sys.stdout.write(part)
            sys.stdout.flush()
            yield part
        print


class Router(object):
    """WSGI middleware that maps incoming requests to WSGI apps."""

    def __init__(self, mapper):
        """Create a router for the given routes.Mapper.

        Each route in `mapper` must specify a 'controller', which is a
        WSGI app to call.  You'll probably want to specify an 'action' as
        well and have your controller be an object that can route
        the request to the action-specific method.

        Examples:
          mapper = routes.Mapper()
          sc = ServerController()

          # Explicit mapping of one route to a controller+action
          mapper.connect(None, '/svrlist', controller=sc, action='list')

          # Actions are all implicitly defined
          mapper.resource('server', 'servers', controller=sc)

          # Pointing to an arbitrary WSGI app.  You can specify the
          # {path_info:.*} parameter so the target app can be handed just that
          # section of the URL.
          mapper.connect(None, '/v1.0/{path_info:.*}', controller=BlogApp())

        """
        self.map = mapper
        self._router = routes.middleware.RoutesMiddleware(self._dispatch,
                                                          self.map)

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, req):
        """Route the incoming request to a controller based on self.map.

        If no match, return a 404.

        """
        return self._router

    @staticmethod
    @webob.dec.wsgify(RequestClass=Request)
    def _dispatch(req):
        """Dispatch the request to the appropriate controller.

        Called by self._router after matching the incoming request to a route
        and putting the information into req.environ.  Either returns 404
        or the routed WSGI app's response.

        """
        match = req.environ['wsgiorg.routing_args'][1]
        if not match:
            return webob.exc.HTTPNotFound()
        app = match['controller']
        return app


class Loader(object):
    """Used to load WSGI applications from paste configurations."""

    def __init__(self, config_path=None):
        """Initialize the loader, and attempt to find the config.

        :param config_path: Full or relative path to the paste config.
        :returns: None

        """
        config_path = config_path or FLAGS.api_paste_config
        self.config_path = utils.find_config(config_path)

    def load_app(self, name):
        """Return the paste URLMap wrapped WSGI application.

        :param name: Name of the application to load.
        :returns: Paste URLMap object wrapping the requested application.
        :raises: `raksha.exception.PasteAppNotFound`

        """
        try:
            return deploy.loadapp("config:%s" % self.config_path, name=name)
        except LookupError as err:
            LOG.error(err)
            raise exception.PasteAppNotFound(name=name, path=self.config_path)
