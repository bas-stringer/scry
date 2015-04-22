from utility          import URIError
from services.classes import SCRY, STANDARD_ATTRIBUTES, Procedure

from rdflib.graph import Graph
from rdflib.term  import Literal

def load_procedures(config_file):

    service_config = dict()

    def import_file(string):
        path = string.split('.')
        mod  = __import__(string)
        while len(path) > 1: mod = getattr(mod,path.pop(1))
        var_list = dir(mod)
        if '__all__' in var_list:
            var_list = mod.__all__
        for i in var_list:
            v = getattr(mod,i)
            if isinstance(v,Procedure):
                v.assert_validity()
                if v.uri not in service_config:
                    service_config[v.uri] = v
                else:
                    raise URIError("More than one registered procedure is using the URI %s" % v.uri.encode() )

    with open(config_file) as f:
        for line in f:
            line = line.split('#')[0].strip()
            if not line: continue # Skip empty lines and full-line comments
            import_file(line)

    return service_config

def get_orb_description(desc_dict,service_config):
    g    = Graph()
    
    for attr in STANDARD_ATTRIBUTES:
        g.add((SCRY.orb, SCRY[attr], Literal(desc_dict[attr])))

    for uri_string in service_config:
        proc = service_config[uri_string]
        desc = proc.get_description()
        g   += desc

    return g