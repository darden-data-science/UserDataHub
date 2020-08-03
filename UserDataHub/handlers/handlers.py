from tornado import web
from tornado.httputil import url_concat, split_host_and_port
from urllib.parse import urlparse, parse_qs, parse_qsl, urlunparse, urlencode
from tornado.log import app_log
import time
from copy import deepcopy

from tornado_sqlalchemy import as_future, SessionMixin, SQLAlchemy

import json

from ..utils import url_path_join
from ..orm import User

class BaseHandler(SessionMixin, web.RequestHandler):
    @property
    def log(self):
        return self.settings.get('log', app_log)

    @property
    def db(self):
        return self.settings.get('db')

class Template404(BaseHandler):
    """Render our 404 template"""

    async def prepare(self):
        # await super().prepare()
        super().prepare()
        raise web.HTTPError(404)

class GetUser(BaseHandler):

    @property
    def configurator(self):
        return self.settings.get('configurator')

    @property
    def auth_token_valid_time(self):
        return self.settings.get('auth_token_valid_time')

    def get(self):
        if self.get_argument('user', False):
            user = self.get_secure_cookie(name='user_data', value=self.get_argument('user'))
            if user is not None:
                user = user.decode('utf-8')
                self.set_header('Content-Type', 'text/plain')
                user_data = self.configurator.get_user_data(user)
                if user_data is None:
                    self.log.warning("User %r tried to log in but was not on the allowed list." % user)
                    raise web.HTTPError(403)

                self.configurator.create_home_folder(user)
                
                encoded_data = json.dumps(user_data).encode('utf-8')
                signed_data = self.create_signed_value(name='user_data', value=encoded_data)
                
                self.write(signed_data)

            else:

                self.log.warning("Query is malformed.")
                raise web.HTTPError(400)

        self.finish()

class HealthCheckHandler(BaseHandler):
    """Answer to health check"""

    def get(self, *args):
        self.finish()