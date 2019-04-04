import sys
from c7n.resources import load_resources
import yaml
import re

load_resources()
error = 0
p_num = 0
greater = 0
re_pattern = "code - block:: yaml([\s]*)(?s). +?(?= ^ $)"

for mod in sys.modules.keys():
    if 'c7n.resources.cfn' in mod:
        module = sys.modules[mod]
        for sub_item in dir(module):
            cls = getattr(sys.modules[mod], sub_item, None)
            if isinstance(cls, type):
                if cls.__doc__:
                    splt_doc = [x.split('\n\n ') for x in cls.__doc__.split('yaml')] # split on yaml and new lines
                    import itertools
                    for item in itertools.chain.from_iterable(splt_doc):
                        if 'policies:\n' in item :
                    # splt_doc = cls.__doc__.split('code-block:: yaml')  # fix regex to catch all tests
                    # if len(splt_doc) > 1:
                    #     print(splt_doc)
                        # remove_newlines = splt_doc.split('\n\n ')
                    #     for yml_blk in remove_newlines:
                    #         policy_strings = list(filter(lambda x: 'policies:\n', yml_blk))
                    #
                    #         for pol in policy_strings:
                    #             try:
                    #                 p = yaml.load(pol)
                    #                 # print(p)
                    #                 p_num = p_num + 1
                    #             except:
                    #                 # print(splt_doc)
                    #                 error = error +1
                    # if len(splt_doc) >2:
                    #     greater = greater+1
                    #     print(cls)
                    #     print (splt_doc)
                    #     print(len(splt_doc))


print(error)
print(greater)
print(p_num)