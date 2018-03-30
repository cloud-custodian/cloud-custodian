from vcr_unittest import VCRTestCase


class BaseTest(VCRTestCase):

    def _get_vcr_kwargs(self):
        return super(BaseTest, self)._get_vcr_kwargs(
            filter_headers=[('Authorization', 'bearer filtered')],
        )

    def load_policy(
            self, data, config=None, session_factory=None):
        pass

        
        
