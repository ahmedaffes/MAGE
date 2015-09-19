# coding: utf-8
'''
    @license: Apache License, Version 2.0
    @copyright: 2007-2013 Marc-Antoine Gouillart
    @author: Marc-Antoine Gouillart
'''

## Python imports

## Django imports
from django.db.models.signals import post_syncdb

## MAGE imports
import models
from ref.models.classifier import AdministrationUnit
from ref.models.parameters import setOrCreateParam
from ref.demo_items import utility_create_meta, utility_create_test_instances, \
    utility_create_logical, create_full_test_data

def post_syncdb_handler(sender, **kwargs):
    ## Create or update parameters

    ## General parameters that should never be removed...
    setOrCreateParam(key=u'LINK_COLORS', value=u'#004D60,#1B58B8,#DE4AAD,#D39D09,#AD103C,#180052',
             default_value=u'#004D60,#1B58B8,#DE4AAD',
             description=u'Couleurs des liens de la page d\'accueil')

    setOrCreateParam(key=u'MODERN_COLORS', value=u'#004A00,#61292B,#180052,#AD103C,#004D60,#1B58B8,#DE4AAD',
             default_value=u'#004A00,#61292B,#180052,#AD103C,#004D60,#1B58B8,#DE4AAD',
             description=u'Couleurs des cases de la page d\'accueil')

    ## Welcome screen parameters
    setOrCreateParam(key=u'LINKS_TITLE', value='Liens utiles',
             default_value='Liens utiles',
             description=u'titre du bloc de liens sur la page d\'accueil',
             axis1='welcome')

    ## Root should exist
    root = AdministrationUnit(name='root', description='the root container', block_inheritance=True)
    root.save()

    ## DEBUG
    #create_full_test_data()


## Listen to the syncdb signal
post_syncdb.connect(post_syncdb_handler, sender=models)

"""
C:\Python27\python.exe .\manage.py sqlclear ref,scm | select-string -NotMatch dot  | C:\Python27\python.exe .\manage.py dbshell
C:\Python27\python.exe .\manage.py migrate
C:\Python27\python.exe .\manage.py runserver
"""


"""
from ref.models import  *
p = ComponentInstance.objects.all()[1]
c = p.build_proxy()
c.admin_login
c.server_name
"""

# ((T,oracleinstance)(S,admin_login="login",admin_password="password")(R,server,((S,dns="server.marsu.net"))))

''' 
from ref.models import  *
c = ComponentInstance.objects.filter(description__name='jbossapplication')[0]
p = c.proxy
s = ComponentInstance.objects.filter(description__name='oracleschema')[0]
p.schema.append(s)
p.schema[0]
'''
