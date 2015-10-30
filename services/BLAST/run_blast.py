from __init__              import __version__, BLAST, BLAST_BIN_ROOT, BLAST_DB_ROOT, DEFAULT_DB
from services.classes      import Procedure, Argument
from options               import ALLOWED_OPTIONS, ALLOWED_FLAGS, SPECIAL_OPTIONS
from utility               import SCRYError

from rdflib.term           import Literal

from os                    import system
from os.path               import join
from subprocess            import check_call
from xml.etree.ElementTree import parse

__all__ = ['RunBLAST']

def run_blast(inputs,outputs,handler):
    
    def make_files():
        temp_dir = handler.get_temp_dir()
        out_file = join(temp_dir,'output.xml')
        if not ('seq' in inputs) ^ ('file' in inputs):
            raise SCRYError("SCRY BLAST requires exactly one of 'seq' or 'file' to be specified.")
        elif 'seq' in inputs:
            seq = inputs['seq'].encode()
            if not seq.startswith('>'):
                seq = '>query_sequence\n%s' % seq
            in_file = join(temp_dir,'input.fasta')
            with open(in_file,'w') as f: f.write(seq)
        else:
            in_file = inputs['file'].encode()
        return in_file, out_file
        
    def get_program():
        try:
            return inputs['program'].encode()
        except KeyError:
            if 'seq_type' in inputs:
                seq_type = inputs['seq_type'].encode().lower()
            else:
                seq_type = guess_type()
            if seq_type == 'protein':
                return 'blastp'
            else:
                return 'blastn'
    
    def guess_type():
        with open(in_file) as f:
            f.readline() # Skip the first line
            alphabet  = set(f.read().lower())
            prot_only = set('efijlopqz') # Characters only used for amino acid codes in the FASTA format
            if len(alphabet) > 12 or alphabet.intersection(prot_only):
                # If more than 12 different characters are used, or if any characters unique to proteins are used...
                return 'protein'
            else:
                return 'nucleotide'

    def get_cmd():
        cmd = '%s -query %s -out %s -db %s -outfmt 5' % (program_file, in_file, out_file, db_file)
        for k in inputs:
            if k in ALLOWED_OPTIONS and ALLOWED_OPTIONS[k]:
                cmd += ' -%s %s' % (k, inputs[k])
            elif k in ALLOWED_FLAGS and ALLOWED_FLAGS[k]:
                cmd += ' -%s' % k
        return cmd

    def parse_XML():
        hsp_dicts = list()
        with open(out_file) as f:
            doc = parse(f)
        root = doc.getroot()
        hits = root[-1][-1][-2].getchildren() # Output_iterations / Last iteration / Iteration hits
        for hit in hits:
            hit_dict = {elem.tag:elem.text for elem in hit.getchildren()}
            hsps = hit[-1].getchildren()
            for hsp in hsps:
                hsp_dict = {elem.tag:elem.text for elem in hsp.getchildren()}
                hsp_dict.update(hit_dict)
                for attr in ['identity','positive','gaps']:
                    frac = float(hsp_dict['Hsp_%s' % attr]) / float(hsp_dict['Hsp_align-len'])
                    hsp_dict['frac_%s' % attr] = frac
                    hsp_dict['perc_%s' % attr] = frac * 100
                hsp_dicts.append(hsp_dict)
        return hsp_dicts


    in_file, out_file = make_files()
    program           = get_program()
    program_file      = join(BLAST_BIN_ROOT,program)
    db                = (inputs['db'].encode() if 'db' in inputs else DEFAULT_DB)
    db_file           = join(BLAST_DB_ROOT,db)
    cmd               = get_cmd()

    system(cmd)
    hits     = parse_XML()
    num_hits = {}
    if 'num_hits' in outputs:
        num_hits = {'num_hits':Literal(len(hits))}
        outputs.remove('num_hits')
    
    out = list()
    for d in hits:
        od = {k : Literal(d[out_dict[k][0]]) for k in outputs}
        od.update(num_hits)
        out.append(od)
    
    return out

# PROCEDURE
p = Procedure(BLAST.blast)
p.function    = run_blast
p.author      = "Bas Stringer"
p.description = "The SCRY BLAST procedure; a bridge between NCBI's BLAST program suite and SPARQL"
p.provenance  = "Results generated by SCRY BLAST version %s" % __version__
p.version     = __version__
RunBLAST      = p

# ARGUMENTS
in_dict = {'seq'      : "A FASTA formatted input sequence BLAST should query with\nEither this or the 'file' argument *must* be specified",
           'seq_type' : "'protein' or 'nucleotide'",
           'file'     : "A URIRef with a file path to the input sequence BLAST should query with\nEither this or the 'seq' argument *must* be specified",
           'program'  : "The BLAST program you wish to run\nMust be one of; %s" % ', '.join(SPECIAL_OPTIONS['program']),
           'db'       : "The database BLAST should query\nThis Orb offers access to the following databases;\n%s" % ', '.join(SPECIAL_OPTIONS['db'])}

for k in in_dict:
    a             = Argument(k)
    a.uri         = BLAST['input/%s' % k]
    a.description = in_dict[k]
    RunBLAST.add_input(a,k=='seq')

options = dict()
options.update(ALLOWED_OPTIONS)
options.update(ALLOWED_FLAGS)
for opt in options:
    if not options[opt]: continue
    a = Argument(opt)
    a.uri = BLAST['option/%s' % opt]
    a.description = "SCRY BLAST option '%s'\nRefer to NCBI's BLAST documentation for more details" % opt
    a.valuetype   = Literal
    RunBLAST.add_input(a)

out_dict = {'num_hits'      : ( None             , "The total number of high-scoring segment pairs BLAST found in the database"),
            'id'            : ('Hit_id'          , "The identifier line of a query hit"),
            'def'           : ('Hit_def'         , "The definition line of a query hit"),
            'ac'            : ('Hit_accession'   , "The accession number of a query hit"),
            'len'           : ('Hit_len'         , "The length of a hit sequence"),
            'bitscore'      : ('Hsp_bit-score'   , "The bit-score of a hit; a log-scaled variant of the 'score' output"),
            'score'         : ('Hsp_score'       , "The raw score of a hit"),
            'e_val'         : ('Hsp_evalue'      , "The Expectation value of a hit"),
            'qry_from'      : ('Hsp_query-from'  , "The coordinate on the query sequence where this hit's alignment starts"),
            'qry_to'        : ('Hsp_query-to'    , "The coordinate on the query sequence where this hit's alignment ends"),
            'qry_frame'     : ('Hsp_query-frame' , "The reading frame for which the query sequence was translated;\nUsed by blastx, tblastx and tblastn"),
            'hit_from'      : ('Hsp_hit-from'    , "The coordinate on the hit sequence where this hit's alignment starts"),
            'hit_to'        : ('Hsp_hit-to'      , "The coordinate on the hit sequence where this hit's alignment ends"),
            'hit_frame'     : ('Hsp_hit-frame'   , "The reading frame for which the hit sequence was translated;\nUsed by blastx, tblastx and tblastn"),
            'identity'      : ('Hsp_identity'    , "The number of identical pairs of residues in the hit's alignment"),
            'positive'      : ('Hsp_positive'    , "The number of pairs of residues in the hit's alignment with a positive score given the used substitution matrix"),
            'gaps'          : ('Hsp_gaps'        , "The number of gaps in the alignment between the query and hit sequence"),
            'frac_identity' : ('frac_identity'   , "The fraction of identical pairs of residues in the hit's alignment"),
            'frac_positive' : ('frac_positive'   , "The fraction of aligned residues in the hit's alignment with a positive score given the used substitution matrix"),
            'frac_gaps'     : ('frac_gaps'       , "The fraction of gaps in the alignment between the query and hit sequence"),
            'perc_identity' : ('perc_identity'   , "The percentage of identical pairs of residues in the hit's alignment"),
            'perc_positive' : ('perc_positive'   , "The percentage of pairs of residues in the hit's alignment with a positive score given the used substitution matrix"),
            'perc_gaps'     : ('perc_gaps'       , "The percentage of gaps in the alignment between the query and hit sequence"),
            'align_len'     : ('Hsp_align-len'   , "The number of residues in the high-scoring segment pair"),
            'qry_seq'       : ('Hsp_qseq'        , "The aligned section of the query sequence"),
            'hit_seq'       : ('Hsp_hseq'        , "The aligned section of the hit sequence"),
            'midline'       : ('Hsp_midline'     , "The midline between 'qry_seq' and 'hit_seq'")}

for k in out_dict:
    a             = Argument(k)
    a.uri         = BLAST['output/%s' % k]
    a.description = out_dict[k][1]
    RunBLAST.add_output(a,k=='seq')
