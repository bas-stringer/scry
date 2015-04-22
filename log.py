from __init__ import LOG_DIRECTORY
from utility  import assert_dir

from os.path  import join
from datetime import datetime
from shutil   import copyfile

REQUEST_DIR  = join(LOG_DIRECTORY,'requests')
RESPONSE_DIR = join(LOG_DIRECTORY,'responses')

assert_dir(REQUEST_DIR)
assert_dir(RESPONSE_DIR)

def log_request(request):
    now       = datetime.now()    
    date      = now.date().isoformat()
    time      = now.time().isoformat()
    last_path = join(LOG_DIRECTORY,'last_request.log')
    spacer    = '\n\n----------\n\n'
        
    vals = request.values
    print 'Logging HTTP request ('+time+')'
    with open(last_path,'w') as f:

        f.write('Method   :\t'+request.method+'\n')
        f.write('Time     :\t'+time+'\n')
        f.write('Base URL :\t'+request.base_url+'\n')
        f.write('Full Path:\t'+request.full_path+spacer)
        
        f.write('Values (Len '+str(len(vals))+'):'+'\t'+str(vals) + '\n')
        for k in vals:
            f.write('\n'+k+':\t'+vals[k])
        f.write(spacer)

        f.write('Content Length     :\t'+str(request.content_length)+'\n')
        f.write('Content Type       :\t'+str(request.content_type)+'\n')
        f.write('Parsed Content Type:\t'+str(request._parsed_content_type)+spacer)        
                    
        f.write('Accepted Response Types:\t'+str(request.accept_mimetypes)+spacer)
                
        f.write(str(dir(request)) + spacer)
        for prop in dir(request):

            if prop.find('__') != -1: continue
            elif prop == 'access_route': continue # Not sure why, but not skipping this causes issues
            
            f.write('=== ' + prop + ' ===\n\n')
            val = getattr(request,prop)
            fnc = hasattr(val,'__call__')
            if fnc:
                f.write(str(type(val)) + spacer)
            else:
                f.write(str(val) + spacer)

    # Copy the new last_request.log file to the appropriate location
    dir_path  = join(REQUEST_DIR,date)
    file_path = join(dir_path,'%s.log' % (time))
    assert_dir(dir_path)
    copyfile(last_path,file_path)
    
    return date, time

def log_response(response, date, time):
    print 'Logging HTTP response ('+time+')'
    last_path = join(LOG_DIRECTORY,'last_response.log')
    with open(last_path,'w') as f:
        f.write(response)

    # Copy the new last_response.log file to the appropriate location
    dir_path  = join(RESPONSE_DIR,date)
    file_path = join(dir_path,'%s.log' % (time))
    assert_dir(dir_path)
    copyfile(last_path,file_path)