import os
import sys

realpath = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                         "../app"))
sys.path.append(realpath)
