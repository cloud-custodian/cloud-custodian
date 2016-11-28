import json
import logging
import os
import shutil
import tempfile

from common import BaseTest


class HandleTest(BaseTest):

    def test_handler(self):
        level = logging.root.level
        botocore_level = logging.getLogger('botocore').level

        self.run_dir = tempfile.mkdtemp()
        cur_dir = os.path.abspath(os.getcwd())
        os.chdir(self.run_dir)

        def cleanup():
            os.chdir(cur_dir)
            shutil.rmtree(self.run_dir)
            logging.root.setLevel(level)
            logging.getLogger('botocore').setLevel(botocore_level)

        self.addCleanup(cleanup)
        self.change_environment(C7N_OUTPUT_DIR=self.run_dir)

        from c7n import handler

        with open(os.path.join(self.run_dir, 'config.json'), 'w') as fh:
            json.dump({'policies': []}, fh)

        self.assertEqual(
            handler.dispatch_event(
                {'detail': {'errorCode': '404'}}, None),
            None)
        self.assertEqual(
            handler.dispatch_event({'detail': {}}, None), True)

        config = handler.Config.empty()
        self.assertEqual(config.assume_role, None)
        try:
            config.foobar
        except AttributeError:
            pass
        else:
            self.fail("should have raised an error")
