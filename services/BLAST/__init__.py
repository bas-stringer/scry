# The SCRY BLAST scripts are intended for use with NCBI BLAST software version 2.2.29+
# Currently supported programs are blastn, blastp, blastx, tblastn and tblastx.

from rdflib  import Namespace
from os      import listdir
from os.path import basename

__version__     = '0.2'

BLAST           = Namespace('http://www.scry.com/blast/')
BLAST_BIN_ROOT  = '/usr/local/ncbi-blast-2.2.29+/bin/'  # Path to local BLAST 2.2.29+ binaries, i.e. where blastp, blastn, etc. are found
BLAST_DB_ROOT   = '/usr/local/ncbi-blast-2.2.29+/db/'   # Path to local BLAST 2.2.29+ compatible databases

CACHE_SEQUENCES = True  # Set to True if you want files of input sequences to be stored locally
CACHE_DIRECTORY = '/home/bas/Documents/SCRY/scry/services/BLAST/sequence_cache/'

DEFAULT_DB      = 'HPA'
DATABASES       = list()

for f in listdir(BLAST_DB_ROOT):
    if f.endswith('.psq'):
        DATABASES.append(f[:-4])