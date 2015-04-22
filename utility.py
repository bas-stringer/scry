from werkzeug.exceptions import HTTPException

from os                  import mkdir
from os.path             import sep, isdir, dirname

def assert_dir(path):
    to_add = list()
    if path.endswith(sep): path = path[:-1]
    while not isdir(path):
        to_add.append(path)
        path = dirname(path)
    for i in xrange(len(to_add)):
        path = to_add.pop()
        print 'Making new directory: %s' % (path)
        mkdir(path)
        
class SCRYError(HTTPException):
    def __init__(self,desc):
        Exception.__init__(self)
        self.description = "\n\nSCRY error: %s\n\n" % desc
        self.code        = 500
        print self.description

class URIError(SCRYError):
    pass

class EmptyListError(ValueError):
    pass