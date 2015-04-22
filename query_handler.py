import rdflib.plugins.sparql as sparql

from __init__        import SUPPORTED_REQUEST_METHODS, SUPPORTED_RESPONSE_TYPES
from context_handler import OrbHandler, CallHandler, VarSubCallHandler, ValuesHandler, BindHandler
from utility         import SCRYError

from rdflib          import Namespace
from rdflib.graph    import ConjunctiveGraph
from rdflib.term     import URIRef, Variable
from flask           import Response
from log             import log_request, log_response

from tempfile        import mkdtemp
from shutil          import rmtree


class QueryHandler(object):


    def __init__(self, request, global_dict):
        self.request          = request                       # The HTTP request object as passed by Flask
        self.global_dict      = global_dict                   # The global environment dictionary of the Flask application
        self.service_config   = global_dict['service_config'] # A service configuration dictionary, pointing from PAUs to procedures
        self.parsed           = dict()                        # A dictionary for the results of parsing the HTTP request
        self.query            = None                          # An object with .prologue and .algebra attributes, generated from the query string through RDFLib's SPARQL parser
        self.query_type       = None                          # One of: 'SELECT', 'CONSTRUCT', 'ASK' or 'DESCRIBE'
        self.triples          = list()                        # A list of triples parsed from the query algebra
        self.response_type    = None                          # The selected MIME type of the response
        self.graph            = ConjunctiveGraph()            # The graph object against which 'query' will be resolved
        self.orb_description  = False                         # When an OrbHandler adds the scry:orb_description context, this attribute stores the pointer to it
        self.context_handlers = list()                        # A list of context handlers, needed for the bookkeeping of call_services()
        self.var_binders      = dict()                        # A dictionary of ?variables used in the query, pointing to the context_handlers that bind values to them        
        self.result           = None                          # An RDFLib Result object, generated through graph.query()
        self.output           = None                          # Formatted results, generated through result.serialize()
        self.service_env      = dict()                        # An environment for services to store whatever data they require
        self.temp_dirs         = list()                       # A list of temporary directories generated for this query's service calls
                                                              # Cleaned up towards the end of resolving


    def resolve(self):
        try:
            date, time = log_request(self.request)
            self.parse_http()           # Retrieve required information from the HTTP request              -- sets the 'parsed' attribute
            self.parse_query()          # Parse the triples and possibly a VALUES statement from the query -- sets the 'query', 'query_type', 'triples', 'values' and 'values_vars' attributes
            self.select_response_type() # Based on ^, determine how to serialize the results later on      -- executed here to assert a valid response type is supported
            self.call_services()        # Populate the 'graph' attribute's RDF graph by invoking the procedures encoded in 'triples'
            self.resolve_query()        # Evaluate 'query' against 'graph'                                 -- sets the 'result' attribute
            self.format_result()        # Serialize the results in a way determined by 'response_type'     -- sets the 'output' attribute
            self.cleanup()
            log_response(self.output, date, time)
            return Response(self.output, mimetype=self.response_type)            

        except SCRYError as e:
            self.output = e.description
            self.cleanup()
            log_response(self.output, date, time)
            raise e


                
    def parse_http(self):
        rq     = self.request
        parsed = dict()        

        def parse_http_request_method():
            if rq.method == 'GET':
                method = 'get'
            else: # POST
                content_type = rq._parsed_content_type[0]
                if content_type == 'application/sparql-query':
                    method = 'direct-post'
                elif content_type == 'application/x-www-form-urlencoded':
                    method = 'url-encoded-post'
                else:
                    raise AttributeError('Invalid SPARQL request')
            if method not in SUPPORTED_REQUEST_METHODS:
                raise NotImplementedError('Handling %s SPARQL requests has not yet been implemented.' % method)
            return method

        def parse_http_query_parameters():
            ### NEEDS REFINEMENT AND MORE THOROUGH TESTING WITH DIFFERENT TYPES OF QUERIES AND TRIPLE STORES
            ### NOT SURE IF request.values['query'] ALWAYS EXISTS, OR WHERE TO GRAB DEFAULT AND NAMED GRAPHS FROM
            query_string  = rq.values['query']
            default_graph = ''
            named_graphs  = []
            return query_string, default_graph, named_graphs    
        
        method                       = parse_http_request_method()
        parsed['method']             = method

        accepted                     = str(rq.accept_mimetypes).split(',')
        parsed['accepted_responses'] = [a.split(';')[0] for a in accepted] # Ignore parameters (like q [preference], level, etc.)
        
        q_string, q_default, q_named = parse_http_query_parameters()
        parsed['query_string']       = q_string
        parsed['default_graph']      = q_default
        parsed['named_graphs']       = q_named

        self.parsed = parsed


    def parse_query(self):
        qry             = sparql.prepareQuery(self.parsed['query_string'])
        self.query      = qry
        self.query_type = qry.algebra.name[0:-5].upper() # 'SELECT', 'CONSTRUCT', 'ASK' or 'DESCRIBE'

        def parse_algebra(algebra):
            if isinstance(algebra,sparql.algebra.CompValue):
                n = algebra.name
                if n == 'values':
                    self.context_handlers.append(ValuesHandler(self,algebra))
                elif n == 'Extend':
                    self.context_handlers.append(BindHandler(self,algebra))
                elif n == 'Graph' and algebra.term == URIRef('http://www.scry.com/orb_description'):
                    self.context_handlers.append(OrbHandler(self,algebra))
                    return
                for key in algebra:
                    if key == 'triples':
                        for t in algebra[key]:
                            self.triples.append(t)
                    parse_algebra(algebra[key])

        parse_algebra(qry.algebra)

    def select_response_type(self):
        ### NEEDS REFINEMENT AND MORE THOROUGH TESTING WITH DIFFERENT TYPES OF QUERIES
        ### HAVE TO CHECK IF ALL RESPONSE TYPES ARE VALID FOR ALL QUERY TYPES, AND IF NOT, MAKE SEPARATE LISTS FOR SELECT/CONSTRUCT/ASK
        accepted = self.parsed['accepted_responses']
        for t in SUPPORTED_RESPONSE_TYPES:
            if t in accepted:
                self.response_type = t.strip()
                break
        if self.response_type is None:
            raise NotImplementedError(("None of the request's accepted response types are currently implemented.\n" +
                                       "Implemented : %s\n" % ', '.join(SUPPORTED_RESPONSE_TYPES.keys())         +
                                       "Accepted    : %s\n" % ', '.join(accepted)))


    def call_services(self):
        # First,  determine which triples use SCRY predicates (input, output, OTHERS???) and assign them to the appropriate CallHandlers
        # Second, determine I/O dependence between the CallHandlers
        # Third,  call the services in the appropriate order, passing on outputs as inputs where required
        #         [Refine this to also take specifications from VALUES and BIND statements into account!]
        #         [Fake it with CallHandler subclasses?]
        
        call_dict     = dict() # A dictionary mapping Procedure Associated URIs to their call handlers
        var_call_dict = dict() # Similar to ^, except mapping Variable URIs to their call handlers
        def get_call_handler(uri):
            if uri in call_dict:
                return call_dict[uri]
            
            if isinstance(uri,URIRef):
                short_uri = URIRef(uri.encode().split('?')[0]) # Crop off parameters if any are specified
                if short_uri in self.service_config:
                    proc = self.service_config[short_uri]
                    handler        = CallHandler(self,proc,uri)
                    call_dict[uri] = handler
                    self.context_handlers.append(handler)
                else:
                    raise SCRYError("A SCRY predicate was used with a subject URI that is not associated with any procedures: %s" % uri.encode())
                return call_dict[uri]
            elif isinstance(uri,Variable):
                if uri not in var_call_dict:
                    handler = VarSubCallHandler(self,uri)
                    var_call_dict[uri] = handler
                    self.context_handlers.append(handler)
                return var_call_dict[uri]
        
        def parse_triples():
            scry = Namespace('http://www.scry.com/')
            for t in self.triples:
                if t[0] == scry.orb:
                    self.describe_orb()
                    continue
                pred = URIRef(t[1].encode().split('?')[0]) # Strip any specifiers/parameters from the predicate
                if pred == scry.input:
                    get_call_handler(t[0]).add_input(t)
                elif pred == scry.output:
                    get_call_handler(t[0]).add_output(t)
                elif pred in [scry.author, scry.description, scry.provenance, scry.version]:
                    get_call_handler(t[0]).add_description(t)
        
        output_dict = dict() # A dictionary mapping bound variables to the execution handlers that bind them as outputs
        def set_dependencies():
            for h in self.context_handlers:
                h.set_bound_vars()
                for output in h.output_vars:
                    if output not in output_dict:
                        output_dict[output] = set()
                    output_dict[output].add(h)
            
            for h in self.context_handlers:
                for var in h.input_vars:
                    try:
                        h.dependencies = h.dependencies.union(output_dict[var])
                    except KeyError as k:
                        raise SCRYError("Unable to resolve depencies involving the Variable %s" % k)

        def execute_all():
            for h in self.context_handlers:
                while not h.executed:
                    indep = h.get_independent_handler(list())
                    indep.execute()
                        
        parse_triples()
        set_dependencies()
        execute_all()

    
    def resolve_query(self):
        self.result = self.graph.query(self.query)
    
    
    def format_result(self):
        if self.response_type is not None:
            format = SUPPORTED_RESPONSE_TYPES[self.response_type]
        else:
            format = 'xml'  
        self.output = self.result.serialize(format = format)


    def get_temp_dir(self):
        path = mkdtemp()
        self.temp_dirs.append(path)
        return path


    def cleanup(self):
        for path in self.temp_dirs:
            rmtree(path)
            
### END OF QueryHandler