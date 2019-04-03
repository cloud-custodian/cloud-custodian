import sys
from c7n.resources import load_resources
import yaml

load_resources()
error = 0
p_num = 0

for mod in sys.modules.keys():
    if 'c7n.resources' in mod:
        module = sys.modules[mod]
        for sub_item in dir(module):
            cls = getattr(sys.modules[mod], sub_item, None)
            if isinstance(cls, type):
                if cls.__doc__:
                    splt_doc = cls.__doc__.split('yaml\n\n            ')
                    if len(splt_doc) ==2:
                        try:
                            p = yaml.load(splt_doc[1])
                            print(p)
                            p_num = p_num + 1
                        except:
                            error = error +1


print(error)
print(p_num)