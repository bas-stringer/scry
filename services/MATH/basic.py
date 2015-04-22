import numpy as np

from __init__          import __version__
from services.classes  import Procedure, Argument
from rdflib            import Namespace
from rdflib.term       import Literal, URIRef

__all__ = list()

## Supported functions: (Note that if an array is given as input to a single value function, the function is applied element-wise.)

## SINGLE VALUE
#  Absolute
#  Arccosine
#  Arcsine
#  Arctangent
#  Ceiling
#  Cosine
#  Exponent
#  Floor
#  Log
#  Log10
#  Modulo           <-- takes a single parameter in the predicate
#  Power            <-- takes a single parameter in the predicate
#  Round
#  Sine
#  SquareRoot
#  Tangent
#  Truncate         <-- takes a single parameter in the predicate

## SINGLE ARRAY
#  Maximum
#  Minimum
#  Mean
#  Median
#  StDev

## MULTI-ARRAY FUNCTIONS
#  SumArrays
#  Covariance
#  PearsonR

MATH = Namespace('http://www.scry.com/math/')

# SOME ARGUMENTS
arg_dict = {'val_in'      : ('http://www.scry.com/math/single-value' , "A single floating point value (Can also be a comma-separated values array!)"),
            'val_out'     : ('http://www.scry.com/math/single-value' , "A single floating point value (Can also be a comma-separated values array!)"),
            'array_in'    : ('http://www.scry.com/math/csv-array'    , "An array of comma-separated values"),
            'array_out'   : ('http://www.scry.com/math/csv-array'    , "An array of comma-separated values"),
            'multi_in'    : ('http://www.scry.com/math/2D-array'     , "A rectangular, 2-D array\nRows are separated by semicolons (;)\nValues within rows are separated by commas (,)"),
            'multi_out'   : ('http://www.scry.com/math/2D-array'     , "A rectangular, 2-D array\nRows are separated by semicolons (;)\nValues within rows are separated by commas (,)"),
            'param'       : ('http://www.scry.com/math/parameter'    , "A parameter value used by certain multi-input functions")}

for key in arg_dict:
    id_string = key
    arg       = Argument(id_string,
                         uri         = MATH[id_string],
                         valuetype   = Literal,
                         datatype    = URIRef(arg_dict[key][0]),
                         description = Literal(arg_dict[key][1]))
    arg_dict[key] = arg

            
# SINGLE VALUE FUNCTIONS
class ValueProc(Procedure):
    def __init__(self,uri,operation):
        super(ValueProc,self).__init__(uri)
        self.operation = operation
        self.add_input(arg_dict['val_in'],required=True,default=True)
        self.add_output(arg_dict['val_out'])
    
    def execute(self,inputs,outputs,handler):
        arg = inputs['val_in'].encode()                  # Input argument; a single value or array of CSV values
        arr = np.array([float(i) for i in arg.split(',')]) # Split a list of CSV into array of floats
        if len(arr) == 0: return                           # Abort if no values were given
        try:
            ans   = [self.operation(i) for i in arr]       # Apply the specified operation to every element in the array
        except IndexError:
            param = float(inputs['param'].encode())
            ans   = [self.operation((i,param)) for i in arr]
        if len(ans) == 1:
            pred = Literal(ans[0])
        else:
            pred = Literal(','.join([str(i) for i in ans]))
        return pred # Specifying the argument is optional if a default output is defined!

single_val_fncs = {'Absolute'   : abs,
                   'Arccosine'  : np.arccos,
                   'Arcsine'    : np.arcsin,
                   'Arctangent' : np.arctan,
                   'Ceiling'    : np.ceil,
                   'Cosine'     : np.cos,
                   'Exponent'   : np.exp,
                   'Floor'      : np.floor,
                   'Log'        : np.log,
                   'Log10'      : np.log10 ,
                   'Modulo'     : lambda x: np.mod(x[0],x[1]),
                   'Power'      : lambda x: x[0]**x[1],
                   'Round'      : round,
                   'Sine'       : np.sin,
                   'Sqrt'       : np.sqrt,
                   'Tangent'    : np.tan,
                   'Truncate'   : lambda x: round(x[0],int(x[1]))}

for fnc in single_val_fncs:
    uri      = MATH[fnc.lower()]
    p        = ValueProc(uri,single_val_fncs[fnc])
    p.author = "Bas Stringer"
    p.description = 'Invokes the %s function on a value, or a comma-separated array of values' % fnc
    p.provenance  = "Generated by SCRY MATH service's %s function, version %s" % (fnc,__version__)
    p.version     = __version__
    if fnc in ['Modulo','Power','Truncate']:
        p.add_input(arg_dict['param'],required=True)
    vars()[fnc] = p # Bind the procedure to a variable with the name of $fnc$
    __all__.append(fnc)


# SINGLE ARRAY FUNCTIONS
class ArrayProc(Procedure):
    def __init__(self,uri,operation,in_id,out_id):
        super(ArrayProc,self).__init__(uri)
        self.operation = operation
        self.in_id     = in_id
        self.out_id    = out_id
        self.add_input(arg_dict[in_id],required=True) # Automatically set to 'default_input' if it's the only input argument!
        self.add_output(arg_dict[out_id])

    def execute(self,inputs,outputs,handler):
        arg = inputs[self.in_id].encode()                                              # Input argument; a single value or array of CSV values
        arr = np.array([[float(i) for i in row.split(',')] for row in arg.split(';')]) # Split the input into 1 or 2D array of floats

        if len(arr) == 0: return    # Abort if no values were given
        ans = self.operation(arr)   # Apply the specified operation to the array
        if np.size(ans) == 1:
            ans_string = str(ans)
        elif len(ans) == np.size(ans):
            ans_string = ','.join([str(i) for i in ans])
        else:
            ans_string = ';'.join([','.join([str(i) for i in row]) for row in ans])
        return {self.out_id : Literal(ans_string)}

array_fncs  = {'Covariance' : (np.cov                        , 'multi_in' , 'multi_out' , "Calculates the N-by-N covariance matrix of N arrays"),
               'Maximum'    : (max                           , 'array_in' , 'val_out'   , "Returns the Maximum value of an array"),
               'Mean'       : (np.mean                       , 'array_in' , 'val_out'   , "Returns the Mean value of an array"),
               'Median'     : (np.median                     , 'array_in' , 'val_out'   , "Returns the Median value of an array"),
               'Minimum'    : (min                           , 'array_in' , 'val_out'   , "Returns the Minimum value of an array"),
               'PearsonR'   : (lambda x:np.corrcoef(x)[0][1] , 'multi_in' , 'val_out'   , "Calculates the Pearson correlation coefficient between two arrays"),
               'StDev'      : (np.std                        , 'array_in' , 'val_out'   , "Calculates the Standard Deviation of an array"),
               'SumArrays'  : (lambda x:np.sum(x,axis=0)     , 'multi_in' , 'array_out' , "Returns N element-wise sums (for M arrays of length N)"),
               'Variance'   : (np.var                        , 'array_in' , 'val_out'   , "Calculates the Variance of an array")}


for fnc in array_fncs:
    spec     = array_fncs[fnc]
    uri      = MATH[fnc.lower()]
    p        = ArrayProc(uri,spec[0],spec[1],spec[2])
    p.author = "Bas Stringer"
    p.description = spec[3]
    p.provenance  = "Generated by SCRY MATH service's %s function, version %s" % (fnc,__version__)
    p.version     = __version__
    vars()[fnc] = p # Bind the procedure to a variable with the name of $fnc$
    __all__.append(fnc)