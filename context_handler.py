from utility                       import SCRYError, EmptyListError

from rdflib                        import Namespace
from rdflib.graph                  import Graph
from rdflib.term                   import URIRef, Literal, BNode, Variable
from rdflib.plugins.sparql.sparql  import Prologue, Query
from rdflib.plugins.sparql.algebra import CompValue


# Superclass of OrbHandler, CallHandler, VarSubCallHandler, ValuesHandler and BindHandler
class ContextHandler(object):
    def __init__(self, query_handler):
        self.query_handler       = query_handler
        self.input_vars          = set()   # A set of Variable instances which must be bound prior to executing this handler
        self.output_vars         = set()   # A set of Variable instances which will have bindings generated for them by this handler
        self.bound_vars          = set()   # The union of this handler's input and output Variables
        self.dependencies        = set()   # A set of other ContextHandlers, whose outputs intersect this handler's inputs

        self.executed            = False   # A boolean to keep track of whether or not this Handler's bindings have been evaluated
        self.bindings            = list()  # A list of dictionaries with the values for 'bound_vars' produced by this handler

    def get_independent_handler(self,checked):
        if self in checked:
            raise SCRYError("Circular Input/Output dependencies could not be resolved!")
        checked.append(self)
        for handler in self.dependencies:
            if not handler.executed:
                return handler.get_independent_handler(checked)
        return self

    def set_bound_vars(self):
        self.bound_vars = self.input_vars.union(self.output_vars)
        
    def execute(self):
        raise NotImplementedError("Children of the ContextHandler class should override the 'execute' method's definition!")

    # Used by CallHandler and BindHandler to combine valid inputs from the outputs of their dependencies
    def merge_and_filter(self,keys,dict_lists):
        N = len(dict_lists)
        
        def num_shared_keys(i,j):
            try:
                x = dict_lists[i][0].keys()
                y = dict_lists[j][0].keys()
            except IndexError:
                raise EmptyListError()
            return len(set(x).intersection(set(y)))
        
        def merge_two(shared,i,j):
            try:
                x     = dict_lists.pop(j)
                y     = dict_lists.pop(i)
                z     = list()
                valid = list()        
                E     = len(x[0]) + len(y[0]) - shared # Expected size of merged dictionaries
            except IndexError:
                raise EmptyListError()
            for a in x:
                for b in y:
                    c = set(a.items()).union(set(b.items()))
                    if len(c) == E:
                        valid.append(c)        
            for v in valid: # Iterate over valid sets
                for u in z: # Iterate over unique sets stored so far
                    if v == u:
                        break
                else:
                    z.append(v)
            out = [{t[0]:t[1] for t in s} for s in z]
            dict_lists.append(out)

        try:
            while N != 1:
                max_shared = (0,0,1)
                for i in range(N):
                    for j in range(i+1,N):
                        shared = num_shared_keys(i,j)
                        if shared > max_shared[0]:
                            max_shared = (shared,i,j)
                merge_two(*max_shared)
                N -= 1
            return dict_lists[0]
        except EmptyListError:
            return list()
            
### END OF ContextHandler



# The most commonly used class in this file -- executes service calls to services specified by its PAU
class CallHandler(ContextHandler):
    def __init__(self,query_handler,proc,pau):
        super(CallHandler,self).__init__(query_handler)
        self.procedure           = proc    # The Procedure instance this Call is associated with
        self.pau                 = pau     # The Procedure Associated URI for which this Call was made
        self.input_triples       = list()
        self.output_triples      = list()
        self.description_triples = list()
      
    def add_input(self,triple):
        self.input_triples.append(triple)
        if isinstance(triple[2],Variable):
            self.input_vars.add(triple[2])
    
    def add_output(self,triple):
        self.output_triples.append(triple)
        if isinstance(triple[2],Variable):
            self.output_vars.add(triple[2])

    def add_description(self,triple):
        self.description_triples.append(triple)
        if isinstance(triple[2],Variable):
            self.output_vars.add(triple[2])
    
    def get_input_specifiers(self,procedure):
        known   = dict()
        var     = dict()
        default = procedure.default_input
        def_id  = None
        
        for t in self.input_triples:
            p = t[1].encode()
            try:
                spec = p.split('?')[1]
                if spec == '_': raise IndexError
            except IndexError:
                if default:
                    def_id = default.id_string
                    spec   = def_id
                else:
                    raise SCRYError("No valid input specifier was defined in the triple below,\n"         +
                                    "nor does the associated procedure have a default input described.\n" +
                                    "subject   : %s\n" % t[0].encode() +
                                    "predicate : %s\n" % t[1].encode() +
                                    "object    : %s\n" % t[2].encode() )
            
            if isinstance(t[2],Variable):
                var[spec] = t
            else:
                known[spec] = t
        return known, var, def_id
    
    def get_output_specifiers(self,procedure):
        out_spec = dict()
        default  = procedure.default_output
        def_id   = None
        
        for t in self.output_triples:
            p = t[1].encode()
            try:
                spec = p.split('?')[1]
                if spec == '_': raise IndexError
            except IndexError:
                if default:
                    def_id = default.id_string
                    spec   = def_id
                else:
                    raise SCRYError("No output specifier was defined in the triple below,\n"               +
                                    "nor does the associated procedure have a default output described.\n" +
                                    "subject   : %s\n" % t[0].encode() +
                                    "predicate : %s\n" % t[1].encode() +
                                    "object    : %s\n" % t[2].encode() )
            out_spec[spec] = t
        return out_spec, def_id
           
    def get_descriptions(self,procedure,pau):
        g    = Graph()
        for t in self.description_triples:
            for attr in ['author','description','provenance','version']:
                p = URIRef('http://www.scry.com/%s' % attr)
                if t[1] == p:
                    val = getattr(procedure,attr)
                    o   = (val if val else "This procedure has no %s specified." % attr)
                    g.add((pau,t[1],Literal(o)))
                    break
        return g

    def execute(self):
        # First, retrieve 'bindings' from all Calls this one depends upon
        # Second, compile a list of "input value dictionaries" based on the input_triples, along with
        # input_vars and the first step's results
        #
        # As an example, let these be the input triples:
        #   <PAU> input?a "foo"
        #   <PAU> input?b ?bar
        #
        # ... and let these be the bindings for ?bar as retrieved from a previously executed call:
        #
        # [ {?bar:<http://www.example.com/hello>}, {?bar:<http://www.example.com/world>} ]
        #
        # Then the list of input values would look as follows:
        #
        # [ {'a':"foo", 'b':<http://www.example.com/hello>}, {'a':"foo", 'b':<http://www.example.com/world>} ]
        #
        # Third, execute the function associated with this call's procedure N times, where N is the
        # number of input value dictionaries. Note that these functions are expected to accept
        # exactly three input arguments:
        #  1) an input value dictionary as shown above
        #  2) a list of specifiers from the Call's scry:output?$spec$ predicates
        #  3) a reference to the QueryHandler object executing this Call (among others, to offer functions access to QH.service_env)
        #
        # Furthermore, the function is expected to return a list of dictionaries, where 1 dictionary corresponds to 1 solution.
        # If a dictionary is returned, rather than a list, SCRY will interpret this as meaning there is only 1 solution.
        # If an RDF Node is returned, SCRY will interpret this as being the only property of the only solution, and bind it to
        # the procedure's default argument, at the risk of throwing an error if there is none. (A last option is that a function
        # call produces no answer at all, in which case the next one is attempted.)
        #
        # Every solution dictionary must contain keys matching the specifier of the scry:output?$spec$ predicates.
        # Each of this Call's output predicate specifiers *must* be included. No specifier may be unmapped.
        # Solution dictionaries *may* contain more keys than that, but they will be ignored.
        #
        # Finally, the execute function will add 1 subgraph to the QueryHandler's conjunctive graph for every solution
        # dictionary. It will also update its own 'bindings' attribute, so that future Calls may access them.

        dep_binds = [dep.bindings for dep in self.dependencies]
        
        known_in, var_in, default_in = self.get_input_specifiers(self.procedure)
        out_spec, default_out        = self.get_output_specifiers(self.procedure)
        var_nodes                    = [var_in[k] for k in var_in]
        var_in_values                = self.merge_and_filter(var_nodes,dep_binds)
        
        constants  = Graph()
        constants += self.get_descriptions(self.procedure,self.pau)
        for spec in known_in:
           constants.add(known_in[spec])
        
        if not (var_in_values or var_in):
            var_in_values.append(dict())
        for d in var_in_values:
            in_dict = dict()
            for k in known_in:
                in_dict[k] = known_in[k][2]
            for k in var_in:
                in_dict[k] = d[var_in[k][2]]
            
            solution_dicts = self.procedure.execute(in_dict,out_spec.keys(),self.query_handler)

            if not solution_dicts:
                continue # Abort if the function call produced no output
            elif isinstance(solution_dicts,list):
                pass
            elif isinstance(solution_dicts,dict):
                solution_dicts = [solution_dicts]
            elif isinstance(solution_dicts,(URIRef,Literal)):
                solution_dicts = [{default_out:solution_dicts}]
            else:
                raise SCRYError("Invalid output type: %s" % type(solution_dicts))

            for sd in solution_dicts:
                # Add a subgraph and update self.bindings
                binds = dict()
                g     = Graph(self.query_handler.graph.store,BNode())
                g    += constants
                for k in var_in:
                    s,p,var    = var_in[k]
                    binds[var] = in_dict[k]
                    g.add((s,p,in_dict[k]))

                for k in out_spec:
                    s,p,var = out_spec[k]
                    if isinstance(var,Variable):
                        binds[var] = sd[k] 
                    g.add((s,p,sd[k]))
             
                self.bindings.append(binds)
        
        if not self.input_triples + self.output_triples: # If only descriptive predicates were used with this PAU...
            g  = Graph(self.query_handler.graph.store,BNode())
            g += constants

        self.executed = True
 
### END OF CallHandler


class VarSubCallHandler(CallHandler):
    def __init__(self,query_handler,var):
        super(VarSubCallHandler,self).__init__(query_handler,None,None)
        self.subject = var
        self.input_vars.add(var)
    
    def execute(self):
        dep_binds      = [dep.bindings for dep in self.dependencies]
        service_config = self.query_handler.global_dict['service_config']

        paus = set()
        for dict_list in dep_binds:
            if self.subject in dict_list[0]:
                for d in dict_list:
                    paus.add(d[self.subject])
        
        for pau in paus:
            short_uri = URIRef(pau.encode().split('?')[0])
            procedure = service_config[short_uri]
            
            known_in, var_in, default_in = self.get_input_specifiers(procedure)
            out_spec, default_out        = self.get_output_specifiers(procedure)
            var_nodes                    = [var_in[k] for k in var_in]
            var_in_values                = self.merge_and_filter(var_nodes,dep_binds)
            
            constants  = Graph()
            constants += self.get_descriptions(procedure,pau)
            for spec in known_in:
                constants.add(known_in[spec])

            for d in var_in_values:
                if d[self.subject] != pau: continue
                
                in_dict = dict()
                for k in known_in:
                    in_dict[k] = known_in[k][2]
                for k in var_in:
                    if k != self.subject:
                        in_dict[k] = d[var_in[k][2]]
                
                solution_dicts = procedure.execute(in_dict,out_spec.keys(),self.query_handler)
    
                if not solution_dicts:
                    continue # Abort if the function call produced no output
                elif isinstance(solution_dicts,list):
                    pass
                elif isinstance(solution_dicts,dict):
                    solution_dicts = [solution_dicts]
                elif isinstance(solution_dicts,(URIRef,Literal)):
                    solution_dicts = [{default_out:solution_dicts}]
                else:
                    raise SCRYError("Invalid output type: %s" % type(solution_dicts))
    
                for sd in solution_dicts:
                    # Add a subgraph and update self.bindings
                    binds = dict()
                    g     = Graph(self.query_handler.graph.store,BNode())
                    g    += constants
                    for k in var_in:
                        s,p,var    = var_in[k]
                        binds[var] = in_dict[k]
                        g.add((pau,p,in_dict[k]))

                    for k in out_spec:
                        s,p,var = out_spec[k]
                        if isinstance(var,Variable):
                            binds[var] = sd[k]
                        g.add((pau,p,sd[k]))

                    self.bindings.append(binds)
            
            #if not self.input_triples + self.output_triples: # If only descriptive predicates were used with this PAU...
            #    g  = Graph(self.query_handler.graph.store,BNode())
            #    g += constants

        self.executed = True

## END OF VarSubCallHandler

        
# Any variables mentioned within the Graph algebra are bound by this handler.
# NOTE: OrbHandlers *CAN NOT* have dependencies on other context handlers!
# If a query containing BIND or VALUES clauses in the GRAPH scry:orb_description { ... }
# block is received, it will most likely *NOT* evaluate correctly!
class OrbHandler(ContextHandler):
    def __init__(self,query_handler,algebra):
        super(OrbHandler,self).__init__(query_handler)
        self.algebra = algebra
        self.execute() # OrbHandlers must be independent of other context handlers.
                       # It should always be safe to execute upon instantiation.

    def describe_orb(self):
        if not self.query_handler.orb_description:
            scry = Namespace('http://www.scry.com/')
            g    = Graph(self.query_handler.graph.store,scry.orb_description)
            g   += self.query_handler.global_dict['orb_description']
            self.query_handler.orb_description = g
        return self.query_handler.orb_description
    
    def execute(self):
        alg = self.algebra
        g   = self.describe_orb()
        
        M = CompValue('Project',p=alg.p,PV=list(alg._vars))
        M = CompValue('Distinct',p=M)
        M = CompValue('SelectQuery',p=M,PV=M.p.PV)
        Q = Query(Prologue(),M)
        
        results = g.query(Q)
        
        self.output_vars = alg._vars
        self.bindings    = [dict(zip(results.vars,r)) for r in results]
        self.executed    = True

class ValuesHandler(ContextHandler):
    def __init__(self,query_handler,algebra):
        super(ValuesHandler,self).__init__(query_handler)
        self.algebra     = algebra
        self.execute() # A Values handler never requires other contexts to be evaluated first
                       # It should always be safe to execute upon instantiation.
        
    def execute(self):
        self.bindings    = self.algebra.res
        self.output_vars = set(self.bindings[0].keys())
        self.executed    = True
        

class BindHandler(ContextHandler):
    def __init__(self,query_handler,algebra):
        super(BindHandler,self).__init__(query_handler)
        self.algebra     = algebra
        self.expression  = algebra.expr
        self.output_vars.add(algebra.var)
        self.parse_expression()
        
    def parse_expression(self):
        if '_vars' in self.expression:
            self.input_vars = self.expression._vars
        else:
            self.execute()
    
    def execute(self):
        exp       = self.expression
        
        if self.dependencies:
            dep_binds = [dep.bindings for dep in self.dependencies]
            in_vars   = [var.encode() for var in self.input_vars]
            inputs    = self.merge_and_filter(in_vars,dep_binds)        
            for d in inputs:
                self.bindings.append({self.algebra.var:exp.eval(d)})

        else:
            if hasattr(exp,'eval'):
                exp = exp.eval()
            self.bindings = [{self.algebra.var:exp}]
            
        self.executed = True