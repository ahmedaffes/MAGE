# coding: utf-8
'''
    @license: Apache License, Version 2.0
    @copyright: 2007-2013 Marc-Antoine Gouillart
    @author: Marc-Antoine Gouillart
'''

class MageError(Exception):
    pass

class MageInternalError(MageError):
    pass

class MageCallerError(MageError):
    pass