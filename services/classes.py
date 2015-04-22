from utility      import SCRYError
from rdflib       import Namespace
from rdflib.graph import Graph
from rdflib.term  import Literal, URIRef

SCRY                = Namespace('http://www.scry.com/')
A                   = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#type')
STANDARD_ATTRIBUTES = ['author','description','provenance','version']

class DescribedURI(object):
    
    def __init__(self,uri,rdf_type,author=str(),description=str(),provenance=str(),version=str()):
        self.uri            = uri         # A required input -- the URI used when describing an object
        self.rdf_type       = rdf_type    # One of scry:procedure or scry:argument
        self.author         = author      # The line bound as a Literal to 'auth' in {?URI scry:author      ?auth .} graph patterns ...
        self.description    = description # The line bound as a Literal to 'desc' in {?URI scry:description ?desc .} graph patterns ...
        self.provenance     = provenance  # The line bound as a Literal to 'prov' in {?URI scry:provenance  ?prov .} graph patterns ...
        self.version        = version     # The line bound as a Literal to 'vers' in {?URI scry:version     ?vers .} graph patterns ...
                                          # ... where ?URI equals this object's uri attribute
        
        def get_description(self):
            raise NotImplementedError("The get_description method must be overwritten by children of the DescribedURI superclass.")

class Procedure(DescribedURI):

    def __init__(self,uri,**kwargs):
        rdf_type = SCRY.procedure
        super(Procedure,self).__init__(uri,rdf_type)

        self.function       = None
        self.accepts        = set() # A set of Argument objects accepted by this procedure
        self.requires       = set() # A subset of 'accepts', with Argument objects *required* by this procedure
        self.generates      = set() # A set of Argument objects generates by this procedure
        self.default_input  = None  # The Argument instance to be associated with UNSPECIFIED scry:input  predicates
                                    # If only 1 required argument is specified, default_input is set to that.
                                    # Else, if only 1 accepted argument is specified, default_input is set to that.
        self.default_output = None  # The Argument instance to be associated with UNSPECIFIED scry:output predicates
                                    # If  only 1 generated argument is specified, default_output is set to that.
                                    
        for key in kwargs:
            setattr(self,key,kwargs[key])

    # This method may be overwritten by expert users, so long as it accepts the same three input arguments
    # They are 1) a dictionary with argument identifier strings pointing towards values
    #          2) a list of argument identifier strings for which output is expected/required
    #          3) the handler of the instance invoking this procedure
    # The function produce a dictionary in which the identifiers from input (2) are mapped to the appropriate output values
    def execute(self,input_dict,expected_outputs,handler):
        return self.function(input_dict,expected_outputs,handler)

    def add_input(self,argument,required=False,default=False):
        self.accepts.add(argument)
        if required:
            self.requires.add(argument)
        if default:
            self.default_input = argument
        
    def add_output(self,argument,default=False):
        self.generates.add(argument)
        if default:
            self.default_output = argument

    ## These commented-out methods are no longer in use
    #def get_inputs(self):
    #    d   = {arg.id_string:arg for arg in self.accepts}
    #    d_i = self.default_input
    #    if d_i:
    #        d['']  = d_i
    #        d['_'] = d_i
    #    return d, d_i
    #
    #def get_outputs(self):
    #    d   = {arg.id_string:arg for arg in self.generates}
    #    d_o = self.default_output
    #    if d_o:
    #        d['']  = d_o
    #        d['_'] = d_o
    #    return d, d_o
    
    def get_description(self):
        g = Graph()
        g.add((SCRY.orb,SCRY.procedure,self.uri))
        g.add((self.uri,A,self.rdf_type))
        for attr in STANDARD_ATTRIBUTES:
            val = getattr(self,attr)
            if val:
                g.add((self.uri,SCRY[attr],Literal(val)))
        
        arg_g = Graph()
        acc   = self.accepts
        req   = self.requires
        gen   = self.generates
        try:
            for arg in acc:
                if not arg.uri: raise ValueError
                if arg in req:
                    arg_g.add((self.uri,SCRY.required_input,arg.uri))
                else:
                    arg_g.add((self.uri,SCRY.accepted_input,arg.uri))
                arg_g += arg.get_description()
                
            for arg in gen:
                if not arg.uri: raise ValueError
                arg_g.add((self.uri,SCRY.generates_output,arg.uri))
                arg_g += arg.get_description()
                
            d_i = self.default_input
            if d_i and d_i.uri:
                arg_g.add((self.uri,SCRY.default_input,d_i.uri))
            else:
                arg_g.add((self.uri,SCRY.default_input,Literal("Undescribed")))

            d_o = self.default_output
            if d_o and d_o.uri:
                arg_g.add((self.uri,SCRY.default_output,d_o.uri))
            else:
                arg_g.add((self.uri,SCRY.default_output,Literal("Undescribed")))
                
        except ValueError:
            for pred in ['required_input','accepted_input','default_input','generates_output','default_output']:
                g.add((self.uri,SCRY[pred],Literal("Undescribed")))
            return g
        
        g += arg_g
        return g
    
    def assert_validity(self):
        # Check if 'function' a specified 'function' attribute actually callable
        if self.function:
            if not hasattr(self.function,'__call__'):
                raise AttributeError("This Procedure's specified function attribute is not callable.")
                
        # Check types for other specified attributes
        d = {'author'         : str,
             'description'    : str,
             'provenance'     : str,
             'version'        : str,
             'default_input'  : (type(None),Argument),
             'default_output' : (type(None),Argument),
             'accepts'        : set,
             'requires'       : set,
             'generates'      : set}
        for k in d:
            att = getattr(self,k)
            if att and not isinstance(att, d[k]):

                raise TypeError("The '%s' attribute of a Procedure must reference an instance of the %s class." % (k,d[k]))

        if any([self.accepts,self.requires,self.generates,self.default_input,self.default_output]):
            self.described_args = True        

            if not self.requires.issubset(self.accepts):
                raise ValueError("The required input arguments of a Procedure must be a subset of its accepted arguments.")

            ids = set()
            i   = 0
            for arg in self.accepts.union(self.generates):
                ids.add(arg.id_string)
                i += 1
                if not isinstance(arg,Argument):
                    raise TypeError("Only instances of the Argument object should be added to a Procedure's inputs and outputs.")
                elif len(ids) != i:
                    raise ValueError("Two Argument instances with the same id (%s) were assigned to this Procedure." % arg.id_string)

            if self.default_input:
                if self.default_input not in self.accepts:
                    raise ValueError("The default input argument of a Procedure must part of of its accepted arguments.")
            else:
                if len(self.requires) == 1:
                    for arg in self.requires:
                        self.default_input = arg
                elif len(self.accepts) == 1:
                    for arg in self.accepts:
                        self.default_input = arg

            if self.default_output:
                if self.default_output not in self.generates:
                    raise ValueError("The default output argument of a Procedure must part of of its generated arguments.")
            elif len(self.generates) == 1:
                for arg in self.generates:
                    self.default_output = arg



class Argument(DescribedURI):

    def __init__(self,id_string,uri=None,valuetype=None,datatype=None,description=None):
        rdf_type = SCRY.argument
        super(Argument,self).__init__(uri,rdf_type)
        
        # Every Argument instance *must* have an identifier
        if not id_string or id_string == '_' or not isinstance(id_string,str):
            raise TypeError("The identifier string of an Argument instance must be an non-empty instance of the string class.")
        self.id_string   = id_string
        # It is *possible*, but strongly discouraged to not specify a URI for Argument instances
        
        # Argument instances may optionally have their description and type specified
        self.description = description # The line shown when a procedure referencing this argument is described
        self.valuetype   = valuetype   # If set, can be displayed upon request, and tested against by assert_type()
                                       # Should be either URIRef or Literal.
        self.datatype    = datatype    # If 'valuetype' is Literal, its datatype may optionally be specified here.
                                       # This will be displayed along with ^ when requested.

    def get_description(self):
        g = Graph()
        g.add((self.uri,A,self.rdf_type))
        g.add((self.uri,SCRY.identifier,Literal(self.id_string)))
        g.add((self.uri,SCRY.description,Literal(self.description)))
        if self.valuetype == URIRef:
            g.add((self.uri,SCRY.valuetype,Literal("URI Reference")))
        else:
            g.add((self.uri,SCRY.valuetype,Literal("Literal")))
            if self.datatype:
                g.add((self.uri,SCRY.datatype,self.datatype))
        return g
        
        
    def set_type(self,valuetype,datatype=None):
        if valuetype == URIRef:
            self.valuetype = valuetype
        elif valuetype == Literal:
            self.valuetype = valuetype
            if datatype:
                self.datatype = datatype
        else:
            raise TypeError("The node type of an Argument instance must be either URIRef or Literal.")
    
    def assert_type(self,node):
        if isinstance(node,self.valuetype):
            if self.datatype and node.datatype != self.datatype: # Only checked when valuetype = Literal
                raise SCRYError("A Literal node bound to an '%s' Argument should have datatype '%s',\ndatatype '%s' is invalid." % (self.id_string, self.datatype, node.datatype))
        else:
            raise SCRYError("Nodes bound to an '%s' Argument should be %s,\n%ss are invalid." % (self.id_string, self.datatype.__class__.__name__, node.__class__.__name__))