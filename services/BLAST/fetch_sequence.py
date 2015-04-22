import re

from __init__         import __version__, BLAST, CACHE_SEQUENCES, CACHE_DIRECTORY
from services.classes import Procedure, Argument
from utility          import assert_dir, SCRYError

from rdflib.term      import URIRef, Literal

from urllib2          import urlopen
from os.path          import join, isfile

__all__ = ['FetchSequence']

if CACHE_SEQUENCES:
    assert_dir(CACHE_DIRECTORY)

def fetch_sequence(inputs,outputs,handler):
    if 'id' not in inputs:
        raise SCRYError("The FetchSequence procedure requires an identifier to be specified as input argument.")
    use_cache  = (True if CACHE_SEQUENCES and not 'reload' in inputs else False)
    identifier = inputs['id'].encode()
    source     = (inputs['source'].encode() if 'source' in inputs and inputs['source'].lower() in KNOWN_SOURCES else DEFAULT_SOURCE).lower()
    id_split   = re.split('\W',identifier)
    try:
        while not re.match(ID_EXPRESSIONS[source],identifier):
            identifier = id_split.pop()
    except IndexError:
        raise SCRYError('No valid %s identifier could be parsed from %s' % (source, inputs['id'].encode()))

    seq_type   = (inputs['seq_type'].encode() if 'seq_type' in inputs else 'protein').lower()
    format     = 'fasta'

    if use_cache or CACHE_SEQUENCES:
        file_dir  = join(CACHE_DIRECTORY,source,seq_type)
    else:
        file_dir  = handler.get_temp_dir()
    file_path = join(file_dir,'%s.%s' % (identifier,format))
    
    if not use_cache or not isfile(file_path):
        assert_dir(file_dir)
        fetch_fnc = KNOWN_SOURCES[source]
        fetch     = fetch_fnc(identifier,seq_type,inputs)
        with open(file_path,'w') as f:
            f.write(fetch)

    out = dict()
    out['file'] = URIRef(file_path)
    if any([spec in outputs for spec in ['seq','seq_len','definition']]):
        seq, definition   = parse_fasta(file_path)
        out['seq']        = Literal(seq)
        out['seq_len']    = Literal(len(seq))
        out['definition'] = definition
    return out


def fetch_uniprot(identifier,seq_type,inputs):
    # format:   fasta
    # seq_type: protein
    url   = 'http://www.uniprot.org/uniprot/%s.fasta' % identifier
    fetch = urlopen(url).read()
    return fetch


# WARNING: without appening &multiple_sequences=1 to the URL, this function is highly likely to
# fail fetching sequences because of how Ensembl's identifiers work... USE WITH CAUTION!
def fetch_ensembl(identifier,seq_type,inputs):
    # format:   fasta
    # seq_type: genomic,cds,cdna,protein
    url   = 'http://rest.ensembl.org/sequence/id/%s.fasta?type=%s' % (identifier, seq_type)
    fetch = urlopen(url).read()
    return fetch


# This function only parses the first sequence from a file!
def parse_fasta(file_path):
    sequence   = str()
    definition = None
    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith('>'):
                if not definition:
                    definition = line
                else:
                    break
            else:
                sequence += line
    return sequence, definition

DEFAULT_SOURCE = 'uniprot'
KNOWN_SOURCES  = {'uniprot' : fetch_uniprot,
                  'ensembl' : fetch_ensembl}
ID_EXPRESSIONS = {'uniprot' : re.compile('^[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$'),
                  'ensembl' : re.compile('^ENS[A-Z]+[0-9]{11}|[A-Z]{3}[0-9]{3}[A-Za-z](-[A-Za-z])?|CG[0-9]+|[A-Z0-9]+\.[0-9]+|YM[A-Z][0-9]{3}[a-z][0-9]$')}

p = Procedure(BLAST.fetch_sequence)
p.function    = fetch_sequence
p.author      = "Bas Stringer"
p.description = "A function which can fetch biological sequences from a variety of sources\nCurrently supported; %s" % ', '.join(KNOWN_SOURCES.keys())
p.provenance  = "Sequence fetched by SCRY BLAST version %s" % __version__
p.version     = __version__
FetchSequence = p

                                    
arg_dict = {'id'         : ('in'  , "The (source-specific) identifier for which to fetch a sequence"),
            'source'     : ('in'  , "The source to fetch a sequence from\nCurrently supported; %s" % ', '.join(KNOWN_SOURCES.keys())),
            'format'     : ('in'  , "The format in which to fetch a sequence\nCurrently supported; fasta"),
            'seq_type'   : ('in'  , "The type of sequence to fetch; Currently supported;\nUniProt; protein\nEnsembl; genomic, cdna, cds, protein"),
            'seq_db'     : ('in'  , "Used to narrow down which database to retrieve sequences from, where applicable.\nCurrently used by; ensembl"),
            'reload'     : ('in'  , "A boolean, used to overwrite a cached file if one exists.\nIgnored if caching is turned off or if no file is cached for the requested id."),
            'seq'        : ('out' , "The sequence string that was fetched"),
            'seq_len'    : ('out' , "The length of the fetched sequence"),
            'definition' : ('out' , "The definition or accession string of the fetched sequence"),
            'file'       : ('out' , "The path to the file where the fetched sequence is stored%s" % ('' if CACHE_SEQUENCES else ' temporarily'))}

for key in arg_dict:
    a             = Argument(key)
    a.uri         = BLAST['fetch/%s' % key]
    a.description = arg_dict[key][1]
    a.valuetype   = Literal
    if arg_dict[key][0] == 'in':
        if key == 'id':
            FetchSequence.add_input(a,True,True)
        else:
            FetchSequence.add_input(a)
    else:
        if key == 'file': a.valuetype = URIRef
        FetchSequence.add_output(a,key == 'seq')