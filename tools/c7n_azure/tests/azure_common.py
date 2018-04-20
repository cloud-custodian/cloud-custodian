import io
import logging
import shutil
import tempfile
import re
import six
from vcr_unittest import VCRTestCase

from c7n import policy
from c7n.schema import generate, validate as schema_validate
from c7n.ctx import ExecutionContext
from c7n.utils import CONN_CACHE
from c7n.resources import load_resources
from c7n_azure.session import Session

load_resources()
C7N_SCHEMA = generate()
DEFAULT_SUBSCRIPTION_ID = 'ea42f556-5106-4743-99b0-c129bfa71a47'


class AzureVCRBaseTest(VCRTestCase):

    def _get_vcr_kwargs(self):
        return super(VCRTestCase, self)._get_vcr_kwargs(
            filter_headers=['Authorization',
                            'client-request-id',
                            'retry-after',
                            'x-ms-client-request-id',
                            'x-ms-correlation-request-id',
                            'x-ms-ratelimit-remaining-subscription-reads',
                            'x-ms-request-id',
                            'x-ms-routing-request-id',
                            'x-ms-gateway-service-instanceid',
                            'x-ms-ratelimit-remaining-tenant-reads',
                            'x-ms-served-by', ],
            before_record_request=self.request_callback
        )

    def _get_vcr(self, **kwargs):
        myvcr = super(VCRTestCase, self)._get_vcr(**kwargs)
        myvcr.register_matcher('azurematcher', self.azure_matcher)
        myvcr.match_on = ['azurematcher']
        return myvcr

    def azure_matcher(self, r1, r2):
        """Replace all subscription ID's before doing request matching"""
        r1_uri = re.sub(
            r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}",
            DEFAULT_SUBSCRIPTION_ID,
            r1.uri)
        r2_uri = re.sub(
            r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}",
            DEFAULT_SUBSCRIPTION_ID,
            r2.uri)

        r1_uri = re.sub(
            r"api-version=\d{4}-\d{2}-\d{2}&?",
            "",
            r1_uri)
        r2_uri = re.sub(
            r"api-version=\d{4}-\d{2}-\d{2}&?",
            "",
            r2_uri)

        return r1_uri == r2_uri

    def request_callback(self, request):
        """Modify requests before saving"""
        if "/subscriptions/" in request.url:
            request.uri = re.sub(
                r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}",
                DEFAULT_SUBSCRIPTION_ID,
                request.url)
        if re.match('https://login.microsoftonline.com/([^/]+)/oauth2/token', request.uri):
            return None
        return request


class BaseTest(AzureVCRBaseTest):

    def cleanUp(self):
        # Clear out thread local session cache
        CONN_CACHE.session = None

    def get_temp_dir(self):
        """ Return a temporary directory that will get cleaned up. """
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)
        return temp_dir

    def get_context(self, config=None, policy=None):
        if config is None:
            self.context_output_dir = self.get_temp_dir()
            config = Config.empty(output_dir=self.context_output_dir)
        ctx = ExecutionContext(
            Session,
            policy or Bag({'name': 'test-policy'}),
            config)
        return ctx

    def load_policy(
            self, data, config=None):
        errors = schema_validate({'policies': [data]}, C7N_SCHEMA)
        if errors:
            raise errors[0]

        config = config or {}

        temp_dir = self.get_temp_dir()
        config['output_dir'] = temp_dir

        conf = Config.empty(**config)
        p = policy.Policy(data, conf, Session)
        p.validate()
        return p

    def capture_logging(
            self, name=None, level=logging.INFO,
            formatter=None, log_file=None):
        if log_file is None:
            log_file = TextTestIO()
        log_handler = logging.StreamHandler(log_file)
        if formatter:
            log_handler.setFormatter(formatter)
        logger = logging.getLogger(name)
        logger.addHandler(log_handler)
        old_logger_level = logger.level
        logger.setLevel(level)

        @self.addCleanup
        def reset_logging():
            logger.removeHandler(log_handler)
            logger.setLevel(old_logger_level)

        return log_file


class Bag(dict):

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class Config(Bag):

    @classmethod
    def empty(cls, **kw):
        d = {}
        d.update({
            'region': None,
            'regions': None,
            'cache': '',
            'profile': None,
            'account_id': None,
            'assume_role': None,
            'external_id': None,
            'log_group': None,
            'metrics_enabled': False,
            'output_dir': '',
            'cache_period': 0,
            'dryrun': False})
        d.update(kw)
        return cls(d)


class TextTestIO(io.StringIO):

    def write(self, b):

        # print handles both str/bytes and unicode/str, but io.{String,Bytes}IO
        # requires us to choose. We don't have control over all of the places
        # we want to print from (think: traceback.print_exc) so we can't
        # standardize the arg type up at the call sites. Hack it here.

        if not isinstance(b, six.text_type):
            b = b.decode('utf8')
        return super(TextTestIO, self).write(b)