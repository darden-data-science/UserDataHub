from tornado import web
from tornado.ioloop import IOLoop
from tornado.log import app_log, access_log, gen_log
import tornado.httpserver
import os
import logging
import binascii
import yaml

from tornado_sqlalchemy import SQLAlchemy

from traitlets.config import Application, catch_config_error

from traitlets import List, Bool, Integer, Set, Unicode, Dict, Any, default, observe, Instance, Float, validate, Bytes, Type, TraitError
from .handlers import Template404, HealthCheckHandler, GetUser
from .users import UserConfigurator, NFSUserConfigurator

from .utils import url_path_join
from .orm import db

COOKIE_SECRET_BYTES = (
    32  # the number of bytes to use when generating new cookie secrets
)

_mswindows = os.name == "nt"

class UserDataHub(Application):

    aliases = {
        'log_level': 'UserDataHub.log_level',
        'f': 'UserDataHub.config_file',
        'config': 'UserDataHub.config_file',
        'port': 'UserDataHub.port'
    }

    flags = {
        'debug': (
            {'Application': {'log_level': logging.DEBUG}},
            "set log level to logging.DEBUG (maximize logging output)",
    ),
        'generate-config': (
            {'UserDataHub': {'generate_config': True}},
            "generate default config file",
        )
    }

    generate_config = Bool(False, help="Generate default config file").tag(config=True)

    config_file = Unicode('userdatahub_config.py', help="The config file to load").tag(
        config=True
    )

    user_data_file = Unicode('user_data.yaml', help="The user data file to load").tag(
        config=True
    )

    cookie_secret = Bytes(
        help="""The cookie secret to use to encrypt cookies.
        Loaded from the AUTH_COOKIE_SECRET env variable by default.
        Should be exactly 256 bits (32 bytes).
        """
    ).tag(config=True, env='AUTH_COOKIE_SECRET')

    @observe('cookie_secret')
    def _cookie_secret_check(self, change):
        secret = change.new
        if len(secret) > COOKIE_SECRET_BYTES:
            self.log.warning(
                "Cookie secret is %i bytes.  It should be %i.",
                len(secret),
                COOKIE_SECRET_BYTES,
            )

    cookie_secret_file = Unicode(
        'userdatahub_cookie_secret', help="""File in which to store the cookie secret."""
    ).tag(config=True)

    port = Integer(default_value=8888, help="Port that server will listen on.").tag(config=True)

    db_url = Unicode(
        'sqlite:///userdatahub.sqlite',
        help="url for the database. e.g. `sqlite:///userdatahub.sqlite`",
    ).tag(config=True)

    @default('log_level')
    def _log_level_default(self):
        return logging.INFO

    @default('log_datefmt')
    def _log_datefmt_default(self):
        """Exclude date from default date format"""
        return "%Y-%m-%d %H:%M:%S"

    @default('log_format')
    def _log_format_default(self):
        """override default log format to include time"""
        return "[%(levelname)1.1s %(asctime)s.%(msecs).03d %(name)s %(module)s:%(lineno)d] %(message)s"

    def write_config_file(self):
        """Write our default config to a .py config file"""
        config_file_dir = os.path.dirname(os.path.abspath(self.config_file))
        if not os.path.isdir(config_file_dir):
            self.exit(
                "{} does not exist. The destination directory must exist before generating config file.".format(
                    config_file_dir
                )
            )
        if os.path.exists(self.config_file):
            answer = ''

            def ask():
                prompt = "Overwrite %s with default config? [y/N]" % self.config_file
                try:
                    return input(prompt).lower() or 'n'
                except KeyboardInterrupt:
                    print('')  # empty line
                    return 'n'

            answer = ask()
            while not answer.startswith(('y', 'n')):
                print("Please answer 'yes' or 'no'")
                answer = ask()
            if answer.startswith('n'):
                return

        config_text = self.generate_config_file()
        if isinstance(config_text, bytes):
            config_text = config_text.decode('utf8')
        print("Writing default config to: %s" % self.config_file)
        with open(self.config_file, mode='w') as f:
            f.write(config_text)


    classes = [UserConfigurator, NFSUserConfigurator]


    @catch_config_error
    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)
        self.log.info("Initializing UserDataHub")
        self.parse_command_line(*args, **kwargs)
        if self.generate_config:
            return
        
        self.log.info("Loading config")
        self.load_config_file(self.config_file)

        self.init_logging()
        self.init_db()
        self.init_secrets()
        self.init_user_database()
        self.init_handlers()
        self.init_tornado_settings()
        self.init_tornado()
    
    def init_handlers(self):
        self.log.info("Initializing handlers.")
        self.handlers = [
                         (r"/get-user", GetUser),
                         (r'/health$', HealthCheckHandler),
                         (r'(.*)', Template404)
                         ]

    def init_db(self):
        self.log.info("Initializing the database.")
        db.configure(self.db_url, engine_options={'echo': False})
        db.create_all()


    def init_user_database(self):
        self.log.info("Initializing the configurator.")
        with open(self.user_data_file, 'r') as f:
            section_dict = yaml.full_load(f)

        self.configurator = NFSUserConfigurator(section_dict=section_dict, parent=self, log=self.log)

    def init_logging(self):
        self.log.info("Initializing loggers.")
        # This prevents double log messages because tornado use a root logger that
        # self.log is a child of. The logging module dipatches log messages to a log
        # and all of its ancenstors until propagate is set to False.
        self.log.propagate = False

        # disable curl debug, which is TOO MUCH
        logging.getLogger('tornado.curl_httpclient').setLevel(
            max(self.log_level, logging.INFO)
        )

        # hook up tornado 3's loggers to our app handlers
        for log in (app_log, access_log, gen_log):
            # ensure all log statements identify the application they come from
            log.name = self.log.name
        logger = logging.getLogger('tornado')
        logger.propagate = True
        logger.parent = self.log
        logger.setLevel(self.log.level)

    def init_tornado_settings(self):
        self.log.info("Initializing tornado settings.")
        self.tornado_settings = dict(
            config = self.config,
            log=self.log,
            # cookie_secret = self.cookie_secret,
            cookie_secret = b'e42c608e4e88d75bfc205e580e3a51c8191b546de7941afdfc5e037a3e8b0ec2',
            app = self,
            configurator = self.configurator,
            db = db
        )

    def init_tornado(self):
        self.log.info("Initializing tornado app.")
        self.tornado_app = web.Application(handlers=self.handlers, **self.tornado_settings)

    def init_secrets(self):
        trait_name = 'cookie_secret'
        trait = self.traits()[trait_name]
        env_name = trait.metadata.get('env')
        secret_file = os.path.abspath(os.path.expanduser(self.cookie_secret_file))
        secret = self.cookie_secret
        secret_from = 'config'
        # load priority: 1. config, 2. env, 3. file
        secret_env = os.environ.get(env_name)
        if not secret and secret_env:
            secret_from = 'env'
            self.log.info("Loading %s from env[%s]", trait_name, env_name)
            secret = binascii.a2b_hex(secret_env)
        if not secret and os.path.exists(secret_file):
            secret_from = 'file'
            self.log.info("Loading %s from %s", trait_name, secret_file)
            try:
                if not _mswindows:  # Windows permissions don't follow POSIX rules
                    perm = os.stat(secret_file).st_mode
                    if perm & 0o07:
                        msg = "cookie_secret_file can be read or written by anybody"
                        raise ValueError(msg)
                with open(secret_file) as f:
                    text_secret = f.read().strip()
                secret = binascii.a2b_hex(text_secret)
            except Exception as e:
                self.log.error(
                    "Refusing to run UserDataHub with invalid cookie_secret_file. "
                    "%s error was: %s",
                    secret_file,
                    e,
                )
                self.exit(1)

        if not secret:
            secret_from = 'new'
            self.log.debug("Generating new %s", trait_name)
            secret = os.urandom(COOKIE_SECRET_BYTES)

        if secret_file and secret_from == 'new':
            # if we generated a new secret, store it in the secret_file
            self.log.info("Writing %s to %s", trait_name, secret_file)
            text_secret = binascii.b2a_hex(secret).decode('ascii')
            with open(secret_file, 'w') as f:
                f.write(text_secret)
                f.write('\n')
            if not _mswindows:  # Windows permissions don't follow POSIX rules
                try:
                    os.chmod(secret_file, 0o600)
                except OSError:
                    self.log.warning("Failed to set permissions on %s", secret_file)
        # store the loaded trait value
        self.cookie_secret = secret

    def start(self):

        self.log.info("Starting the app.")
        if self.generate_config:
            self.write_config_file()
            return

        http_server = tornado.httpserver.HTTPServer(self.tornado_app)
        http_server.listen(self.port)
        try:
            IOLoop.instance().start()
        except KeyboardInterrupt:
            IOLoop.instance().stop()

def main(argv=None):
    app = UserDataHub()
    app.initialize()
    app.start()

if __name__ == "__main__":
    main()