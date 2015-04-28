"""SCRY - the SPARQL Compatible seRvice laYer.

.. moduleauthor:: Bas Stringer <b.stringer@vu.nl>
"""

__version__ = '0.2'

DEBUG               = True
ALLOW_REMOTE_ACCESS = True
IP_WHITELIST        = ['130.37.193.190']
LOG_DIRECTORY       = '/home/bas/Documents/SCRY/logs/'  # Directory for SCRY to log HTTP requests and responses in -- will be created if it does not exist
SERVICE_CONFIG_FILE = '/home/bas/Documents/SCRY/scry/services/registered_modules.txt'
ORB_DESCRIPTION     = {'author'      : "Bas Stringer",
                       'description' : "SCRY - the SPARQL Compatible seRvice laYer (version %s)" % __version__,
                       'provenance'  : "SCRY - the SPARQL Compatible seRvice laYer (version %s)" % __version__,
                       'version'     : __version__ }
                   
SUPPORTED_REQUEST_METHODS = ['get','url-encoded-post'] # Still have to implement 'direct-post'
SUPPORTED_RESPONSE_TYPES  = {'application/sparql-results+xml':'xml',
                             'text/csv'                      :'csv'}

# RDFLib's Result.serialize(format=*) function has serializers registered for the following formats:
# xml, csv, json, txt    (the source suggests tsv and rdf should be there too, but have to figure out how (or if) to register those)