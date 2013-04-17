# coding: utf-8

## GCL

from django.db import models
from ref.models import ComponentInstance, LogicalComponent, ComponentImplementationClass, Environment
from exceptions import MageScmUndefinedVersionError
from scm.exceptions import MageScmUnrelatedItemsError, MageScmMissingComponent, \
    MageScmFailedInstanceDependencyCheck, \
    MageScmFailedEnvironmentDependencyCheck
from MAGE.exceptions import MageError

class InstallableSet(models.Model):
    """Référentiel GCL : ensemble pouvant être installé 
    Destiné à servir de clase de base. (par ex pour : patch, sauvegarde...)"""
    name = models.CharField(max_length=40, verbose_name=u'référence', unique=True)
    description = models.CharField(max_length=1000, verbose_name=u'résumé du contenu', unique=False, blank=True, null=True)
    set_date = models.DateTimeField(verbose_name=u'date de réception', auto_now_add=True)
    ticket_list = models.CharField(max_length=100, verbose_name='ticket(s) lié(s) séparés par une virgule', null=True , blank=True)
    # Through related_name: set_content
    
    removed = models.DateTimeField(null=True, blank=True)
    def __is_available(self):
        return self.removed == None
    available = property(__is_available)
    
    def __unicode__(self):
        return u'%s' % (self.name)
    
    def check_prerequisites(self, envt_name):
        failures = []
        for ii in self.set_content.all():
            try:
                ii.check_prerequisites(envt_name)
            except MageScmFailedEnvironmentDependencyCheck, e:
                failures.extend(e.failing_dep)
        
        if len(failures) == 0:
            return True
        else:
            raise MageScmFailedEnvironmentDependencyCheck(envt_name, self, failures)
    

class Delivery(InstallableSet):
    pass

class BackupSet(InstallableSet):
    pass
    
class LogicalComponentVersion(models.Model):
    version = models.CharField(max_length=50)
    logical_component = models.ForeignKey(LogicalComponent)
    
    def __unicode__(self):
        return u'%s in version [%s]' % (self.logical_component.name, self.version)
    
    def compare(self, lcv2):
        """
            Order relation between LCV objects
            
            The relation is deduced from the dependencies (as they can be seen as links between the LCV).
            This function will not detect inconsistencies in dependencies (such as loops),
            as it will return the first result it will find. (This is, among others, to prevent infinite 
            loops and fasten things.)
            
            It is possible to compare LCV of different model classes, since there can be relationships 
            between different classes.
            
            @return: 1 if the lcv1 should be installed AFTER the lcv2 (lcv1 > lcv2)
                     0 if it doesn't matter ("equality")
                    -1 if the ctv1 should be installed BEFORE the ctv2 (lcv1 < lcv2)
            
            @note: do NOT overload __cmp__ or eq with this function as they are already used by Django internals.
        """
        lcv1 = self
        try: return lcv1.__compareWith(lcv2)
        except MageScmUnrelatedItemsError: return 0
    
    def __compareWith(self, lcv2, __reverseCall=False):
        """ The function actually doing the comparison. Here, equality (0) has a strict meaning. """
        lcv1 = self
        
        ## Argument check
        if not isinstance(lcv1, LogicalComponentVersion) or not isinstance(lcv2, LogicalComponentVersion):
            raise MageError("Arguments must be component version objects")
        
        ## Easy equality
        if (lcv1.logical_component == lcv2.logical_component) and (lcv1.version == lcv2.version):
            return 0
        
        ## Loop on all the InstallableSets that install ctv1
        for ii in lcv1.installed_by.all():
            ## Loop on all the requirements of the installable set
            for dep in ii.dependencies.all():              
                ## Terminaison condition: we have found ctv2
                if dep.depends_on_version == lcv2:
                    if dep.operator == '>=' or dep.operator == '==': 
                        return 1
                    else:
                        return 0
                
                ## Recursion
                try:
                    tmp = dep.depends_on_version.__compareWith(lcv2)
                except MageScmUnrelatedItemsError:
                    continue ## Nothing can be deduced from this relation - go on to the others
                
                ## Analysis of the recursion result
                if (tmp == 1 or tmp == 0) and (dep.operator == '>=' or dep.operator == '=='):
                    return 1    ## Transitivity on >
                if (tmp == -1 or tmp == 0) and (dep.operator == '<='):
                    return -1   ## Transitivity on <
                
                ## If here : the dependency that was analysed does not provide any useful relationship. Let's loop to the next one!
                
            ## If here : no relationship has given fruit. Let's try the reverse relationship analysis.
            if not __reverseCall:
                return -lcv2.__compareWith(lcv1, True)
            
        ## If here : there is really nothing to say between ctv1 and ctv2, so say it : no order relationship
        raise MageScmUnrelatedItemsError(lcv1, lcv2)   


class InstallationMethod(models.Model):
    name = models.CharField(max_length=254)
    halts_service = models.BooleanField(default=True)
    method_compatible_with = models.ManyToManyField(ComponentImplementationClass, related_name='installation_methods')
    available = models.BooleanField(default = True)
    
    def __unicode__(self):
        a=""
        if not self.available:
            a="OBSOLETE - "
        return u'%s%s for %s' %(a, self.name, ",".join([ i.name for i in self.method_compatible_with.all()]))
    
class InstallableItem(models.Model):
    what_is_installed = models.ForeignKey(LogicalComponentVersion, related_name='installed_by')
    how_to_install = models.ManyToManyField(InstallationMethod, verbose_name='techniquement compatible avec')
    belongs_to_set = models.ForeignKey(InstallableSet, related_name='set_content')
    is_full = models.BooleanField(verbose_name='initial/annule et remplace', default=False)
    data_loss = models.BooleanField(verbose_name=u'entraine des pertes de données', default=False)
    #TODO: Add a property to access compatible envt types
    
    def __unicode__(self):
        if self.id is not None:
            return u'Installation of [%s] in version [%s] (%s dependencies with other components'' versions)' % (self.what_is_installed.logical_component.name, self.what_is_installed.version, self.dependencies.count())
        else:
            return u'installable item'
    
    def dependsOn(self, lcv, operator='>='):
        if not self.dependencies.filter(depends_on_version_id=lcv.id, operator=operator).exists():
            ide = ItemDependency(installable_item=self, depends_on_version=lcv, operator=operator)
            ide.save()
            
    def check_prerequisites(self, envt_name):
        #print self
        if self.is_full:
            return True

        failures = []
        for dep in self.dependencies.all():
            potential_cic = []
            for i in self.how_to_install.all():
                potential_cic.extend(i.method_compatible_with.all())
            rs = ComponentInstance.objects.filter(environments__name=envt_name,
                                          instanciates__in= potential_cic,
                                          instanciates__implements=dep.depends_on_version.logical_component)
            if rs.count() == 0:
                #raise MageScmMissingComponent(self, dep.depends_on_version.version, envt_name)
                failures.append(MageScmFailedInstanceDependencyCheck(dep.depends_on_version.logical_component.name, dep, 'there is no compatible component in this environment'))
                continue
            
            for compo in rs.all():
                ## Retrieve current version
                try:
                    ver = compo.latest_cic.result_of.what_is_installed
                except MageScmUndefinedVersionError:
                    failures.append(MageScmFailedInstanceDependencyCheck(compo, dep, 'No version is defined for this component - cannot check dependency!'))
                    continue
                
                ## Check current version against dependency
                compa = ver.compare(dep.depends_on_version)
                #print '%s compare %s: %s' % (ver, dep.depends_on_version, compa)
                if dep.operator == '==' and compa != 0:
                    failures.append(MageScmFailedInstanceDependencyCheck(compo, dep, 'incorrect version - it\'s [%s]' % ver.version))
                    continue
                
                if dep.operator == '>=' and compa < 0:
                    failures.append(MageScmFailedInstanceDependencyCheck(compo, dep, 'incorrect version - it\'s [%s]' % ver.version))
                    continue
                
                if dep.operator == '<=' and compa > 0:
                    failures.append(MageScmFailedInstanceDependencyCheck(compo, dep, 'incorrect version - it\'s [%s]' % ver.version))
                    continue

        if len(failures) == 0:
            return True
        else:
            raise MageScmFailedEnvironmentDependencyCheck(envt_name, self, failures)       
    

class ItemDependency(models.Model):
    OPERATOR_CHOICES = (('>=', '>='),
                        ('<=', '<='),
                        ('==', '=='))
    installable_item = models.ForeignKey(InstallableItem, related_name='dependencies')
    depends_on_version = models.ForeignKey(LogicalComponentVersion)
    operator = models.CharField(max_length=2, choices=OPERATOR_CHOICES)
    
    def __unicode__(self):
        return u'dépendance de [%s] envers [%s en version %s %s]' % (self.installable_item.what_is_installed.logical_component.name, self.depends_on_version.logical_component.name,
                                                                 self.operator, self.depends_on_version.version)

class SetDependency(models.Model):
    OPERATOR_CHOICES = (('>=', '>='),
                        ('<=', '<='),
                        ('==', '=='))
    installable_set = models.ForeignKey(InstallableSet, related_name='requirements')
    depends_on_version = models.ForeignKey(LogicalComponentVersion)
    operator = models.CharField(max_length=2, choices=OPERATOR_CHOICES)
    
    def __unicode__(self):
        return u'IS [%s] requires [%s in version %s %s]' % (self.installable_set.name, self.depends_on_version.logical_component.name,
                                                                 self.operator, self.depends_on_version.version)

class Installation(models.Model):
    installed_set = models.ForeignKey(InstallableSet, verbose_name='livraison appliquée ')
    asked_in_ticket = models.IntegerField(max_length=6, verbose_name='ticket lié ', blank=True, null=True)
    install_date = models.DateTimeField(verbose_name='date d\installation ')

    def __unicode__(self):
        return '%s sur %s le %s' % (self.installed_set.name, self.target_envt.name, self.install_date)
        
class ComponentInstanceConfiguration(models.Model):
    component_instance = models.ForeignKey(ComponentInstance, related_name='configurations')
    result_of = models.ForeignKey(InstallableItem)
    part_of_installation = models.ForeignKey(Installation, related_name='modified_components')
    created_on = models.DateTimeField()
    install_failure = models.BooleanField(default=False)
    
    def __unicode__(self):
        return u'At %s, component %s was at version %s' % (self.created_on, self.component_instance.name, self.result_of.version.version)
    
class Tag(models.Model):
    name = models.CharField(max_length=40, verbose_name=u'référence', unique=True)
    versions = models.ManyToManyField(LogicalComponentVersion, verbose_name=u'version des composants')
    from_envt = models.ForeignKey(Environment)
    snapshot_date = models.DateTimeField(verbose_name=u'date de prise de la photo', auto_now_add=True)

    def __unicode__(self):
        return u'Tag n°%s - %s (concerne %s composants)' % (self.pk, self.name, self.versions.count())



#######################################################################################
## Update Component class with GCL objects
#######################################################################################

## Add a version property to component objects   
def getLatestCIC(comp):
    """@return: the latest installed ComponentInstanceConguration (CIC) on the Component"""
    try:
        return comp.configurations.latest('pk')
    except:
        raise MageScmUndefinedVersionError(comp)
def getComponentVersion(comp):
    """@return: the latest installed ICV on the Component"""
    return getLatestCIC(comp).result_of.what_is_installed
def getComponentVersionText(comp):
    try:
        return getComponentVersion(comp).version
    except MageScmUndefinedVersionError:
        return "inconnue"
ComponentInstance.version = property(getComponentVersionText)  
ComponentInstance.latest_cic = property(getLatestCIC)