#! /usr/bin/env python
import services
import flask

from __init__      import DEBUG, ALLOW_REMOTE_ACCESS, IP_WHITELIST, SERVICE_CONFIG_FILE, ORB_DESCRIPTION
from query_handler import QueryHandler

# Create and configure the web application -- config.from_object uses the DEBUG variable
orb = flask.Flask(__name__)
orb.config.from_object(__name__)

# Route functions
@orb.route('/')
def scry_home():
    print "HOME REQUEST RECEIVED"
    return 'Homepage Placeholder -- EXPAND WITH DIRECT QUERY INTERFACE?'

@orb.route('/scry/', methods=['GET', 'POST'])
def scry_query():
    print "SCRY REQUEST RECEIVED"
    ip = flask.request.remote_addr
    if ip in IP_WHITELIST:
        print flask.g['service_config']
        query = QueryHandler(flask.request, flask.g)
        return query.resolve()
    else:
        return "This IP address (%s) is not on the queried SCRY orb's whitelist." % ip, 500

@orb.errorhandler(500)
def scry_error(e):
    return e.description, 500

# Start the app
def launch():
    flask.g = dict() # A dictionary for passing globals
    flask.g['service_config']  = services.load_procedures(SERVICE_CONFIG_FILE)
    flask.g['orb_description'] = services.get_orb_description(ORB_DESCRIPTION, flask.g['service_config'])

    if ALLOW_REMOTE_ACCESS:
        orb.run(host='0.0.0.0')
    else:
        orb.run()
    
if __name__ == "__main__":
    launch()