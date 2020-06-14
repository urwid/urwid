/*  Urwid unicode character processing tables

    Copyright (C) 2006 Rebecca Breu.
    This file contains rewritten code of utable.py by Ian Ward.

    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU Lesser General Public
    License as published by the Free Software Foundation; either
    version 2.1 of the License, or (at your option) any later version.

    This library is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
    Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public
    License along with this library; if not, write to the Free Software
    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

    Urwid web site: http://excess.org/urwid/
*/

#define PY_SSIZE_T_CLEAN

#include <Python.h>

#define ENC_UTF8 1
#define ENC_WIDE 2
#define ENC_NARROW 3

#if PY_MAJOR_VERSION >= 3
#define PYTHON3
#endif

#if PY_MAJOR_VERSION == 2 && PY_MINOR_VERSION < 5
#define Py_ssize_t int
#define FMT_N "i"
#else
#define FMT_N "n"
#endif

static const int widths[] = {
    8, 0,
    9, 8,
    31, 0,
    126, 1,
    159, 0,
    767, 1,
    879, 0,
    1154, 1,
    1161, 0,
    1424, 1,
    1469, 0,
    1470, 1,
    1471, 0,
    1472, 1,
    1474, 0,
    1475, 1,
    1477, 0,
    1478, 1,
    1479, 0,
    1535, 1,
    1541, 0,
    1551, 1,
    1562, 0,
    1563, 1,
    1564, 0,
    1610, 1,
    1631, 0,
    1647, 1,
    1648, 0,
    1749, 1,
    1757, 0,
    1758, 1,
    1764, 0,
    1766, 1,
    1768, 0,
    1769, 1,
    1773, 0,
    1806, 1,
    1807, 0,
    1808, 1,
    1809, 0,
    1839, 1,
    1866, 0,
    1957, 1,
    1968, 0,
    2026, 1,
    2035, 0,
    2044, 1,
    2045, 0,
    2069, 1,
    2073, 0,
    2074, 1,
    2083, 0,
    2084, 1,
    2087, 0,
    2088, 1,
    2093, 0,
    2136, 1,
    2139, 0,
    2258, 1,
    2307, 0,
    2361, 1,
    2364, 0,
    2365, 1,
    2383, 0,
    2384, 1,
    2391, 0,
    2401, 1,
    2403, 0,
    2432, 1,
    2435, 0,
    2491, 1,
    2492, 0,
    2493, 1,
    2500, 0,
    2502, 1,
    2504, 0,
    2506, 1,
    2509, 0,
    2518, 1,
    2519, 0,
    2529, 1,
    2531, 0,
    2557, 1,
    2558, 0,
    2560, 1,
    2563, 0,
    2619, 1,
    2620, 0,
    2621, 1,
    2626, 0,
    2630, 1,
    2632, 0,
    2634, 1,
    2637, 0,
    2640, 1,
    2641, 0,
    2671, 1,
    2673, 0,
    2676, 1,
    2677, 0,
    2688, 1,
    2691, 0,
    2747, 1,
    2748, 0,
    2749, 1,
    2757, 0,
    2758, 1,
    2761, 0,
    2762, 1,
    2765, 0,
    2785, 1,
    2787, 0,
    2809, 1,
    2815, 0,
    2816, 1,
    2819, 0,
    2875, 1,
    2876, 0,
    2877, 1,
    2884, 0,
    2886, 1,
    2888, 0,
    2890, 1,
    2893, 0,
    2900, 1,
    2903, 0,
    2913, 1,
    2915, 0,
    2945, 1,
    2946, 0,
    3005, 1,
    3010, 0,
    3013, 1,
    3016, 0,
    3017, 1,
    3021, 0,
    3030, 1,
    3031, 0,
    3071, 1,
    3076, 0,
    3133, 1,
    3140, 0,
    3141, 1,
    3144, 0,
    3145, 1,
    3149, 0,
    3156, 1,
    3158, 0,
    3169, 1,
    3171, 0,
    3200, 1,
    3203, 0,
    3259, 1,
    3260, 0,
    3261, 1,
    3268, 0,
    3269, 1,
    3272, 0,
    3273, 1,
    3277, 0,
    3284, 1,
    3286, 0,
    3297, 1,
    3299, 0,
    3327, 1,
    3331, 0,
    3386, 1,
    3388, 0,
    3389, 1,
    3396, 0,
    3397, 1,
    3400, 0,
    3401, 1,
    3405, 0,
    3414, 1,
    3415, 0,
    3425, 1,
    3427, 0,
    3456, 1,
    3459, 0,
    3529, 1,
    3530, 0,
    3534, 1,
    3540, 0,
    3541, 1,
    3542, 0,
    3543, 1,
    3551, 0,
    3569, 1,
    3571, 0,
    3632, 1,
    3633, 0,
    3635, 1,
    3642, 0,
    3654, 1,
    3662, 0,
    3760, 1,
    3761, 0,
    3763, 1,
    3772, 0,
    3783, 1,
    3789, 0,
    3863, 1,
    3865, 0,
    3892, 1,
    3893, 0,
    3894, 1,
    3895, 0,
    3896, 1,
    3897, 0,
    3901, 1,
    3903, 0,
    3952, 1,
    3972, 0,
    3973, 1,
    3975, 0,
    3980, 1,
    3991, 0,
    3992, 1,
    4028, 0,
    4037, 1,
    4038, 0,
    4138, 1,
    4158, 0,
    4181, 1,
    4185, 0,
    4189, 1,
    4192, 0,
    4193, 1,
    4196, 0,
    4198, 1,
    4205, 0,
    4208, 1,
    4212, 0,
    4225, 1,
    4237, 0,
    4238, 1,
    4239, 0,
    4249, 1,
    4253, 0,
    4351, 1,
    4447, 2,
    4956, 1,
    4959, 0,
    5905, 1,
    5908, 0,
    5937, 1,
    5940, 0,
    5969, 1,
    5971, 0,
    6001, 1,
    6003, 0,
    6067, 1,
    6099, 0,
    6108, 1,
    6109, 0,
    6154, 1,
    6158, 0,
    6276, 1,
    6278, 0,
    6312, 1,
    6313, 0,
    6431, 1,
    6443, 0,
    6447, 1,
    6459, 0,
    6678, 1,
    6683, 0,
    6740, 1,
    6750, 0,
    6751, 1,
    6780, 0,
    6782, 1,
    6783, 0,
    6831, 1,
    6848, 0,
    6911, 1,
    6916, 0,
    6963, 1,
    6980, 0,
    7018, 1,
    7027, 0,
    7039, 1,
    7042, 0,
    7072, 1,
    7085, 0,
    7141, 1,
    7155, 0,
    7203, 1,
    7223, 0,
    7375, 1,
    7378, 0,
    7379, 1,
    7400, 0,
    7404, 1,
    7405, 0,
    7411, 1,
    7412, 0,
    7414, 1,
    7417, 0,
    7615, 1,
    7673, 0,
    7674, 1,
    7679, 0,
    8202, 1,
    8207, 0,
    8231, 1,
    8238, 0,
    8287, 1,
    8292, 0,
    8293, 1,
    8303, 0,
    8399, 1,
    8432, 0,
    8985, 1,
    8987, 2,
    9000, 1,
    9002, 2,
    9192, 1,
    9196, 2,
    9199, 1,
    9200, 2,
    9202, 1,
    9203, 2,
    9724, 1,
    9726, 2,
    9747, 1,
    9749, 2,
    9799, 1,
    9811, 2,
    9854, 1,
    9855, 2,
    9874, 1,
    9875, 2,
    9888, 1,
    9889, 2,
    9897, 1,
    9899, 2,
    9916, 1,
    9918, 2,
    9923, 1,
    9925, 2,
    9933, 1,
    9934, 2,
    9939, 1,
    9940, 2,
    9961, 1,
    9962, 2,
    9969, 1,
    9971, 2,
    9972, 1,
    9973, 2,
    9977, 1,
    9978, 2,
    9980, 1,
    9981, 2,
    9988, 1,
    9989, 2,
    9993, 1,
    9995, 2,
    10023, 1,
    10024, 2,
    10059, 1,
    10060, 2,
    10061, 1,
    10062, 2,
    10066, 1,
    10069, 2,
    10070, 1,
    10071, 2,
    10132, 1,
    10135, 2,
    10159, 1,
    10160, 2,
    10174, 1,
    10175, 2,
    11034, 1,
    11036, 2,
    11087, 1,
    11088, 2,
    11092, 1,
    11093, 2,
    11502, 1,
    11505, 0,
    11646, 1,
    11647, 0,
    11743, 1,
    11775, 0,
    11903, 1,
    11929, 2,
    11930, 1,
    12019, 2,
    12031, 1,
    12245, 2,
    12271, 1,
    12283, 2,
    12287, 1,
    12329, 2,
    12333, 0,
    12350, 2,
    12352, 1,
    12438, 2,
    12440, 1,
    12442, 0,
    12543, 2,
    12548, 1,
    12591, 2,
    12592, 1,
    12686, 2,
    12687, 1,
    12771, 2,
    12783, 1,
    12830, 2,
    12831, 1,
    12871, 2,
    12879, 1,
    19903, 2,
    19967, 1,
    40956, 2,
    40959, 1,
    42124, 2,
    42127, 1,
    42182, 2,
    42606, 1,
    42610, 0,
    42611, 1,
    42621, 0,
    42653, 1,
    42655, 0,
    42735, 1,
    42737, 0,
    43009, 1,
    43010, 0,
    43013, 1,
    43014, 0,
    43018, 1,
    43019, 0,
    43042, 1,
    43047, 0,
    43051, 1,
    43052, 0,
    43135, 1,
    43137, 0,
    43187, 1,
    43205, 0,
    43231, 1,
    43249, 0,
    43262, 1,
    43263, 0,
    43301, 1,
    43309, 0,
    43334, 1,
    43347, 0,
    43359, 1,
    43388, 2,
    43391, 1,
    43395, 0,
    43442, 1,
    43456, 0,
    43492, 1,
    43493, 0,
    43560, 1,
    43574, 0,
    43586, 1,
    43587, 0,
    43595, 1,
    43597, 0,
    43642, 1,
    43645, 0,
    43695, 1,
    43696, 0,
    43697, 1,
    43700, 0,
    43702, 1,
    43704, 0,
    43709, 1,
    43711, 0,
    43712, 1,
    43713, 0,
    43754, 1,
    43759, 0,
    43764, 1,
    43766, 0,
    44002, 1,
    44010, 0,
    44011, 1,
    44013, 0,
    44031, 1,
    55203, 2,
    63743, 1,
    64109, 2,
    64111, 1,
    64217, 2,
    64285, 1,
    64286, 0,
    65023, 1,
    65039, 0,
    65049, 2,
    65055, 1,
    65071, 0,
    65106, 2,
    65107, 1,
    65126, 2,
    65127, 1,
    65131, 2,
    65278, 1,
    65279, 0,
    65280, 1,
    65376, 2,
    65503, 1,
    65510, 2,
    65528, 1,
    65531, 0,
    66044, 1,
    66045, 0,
    66271, 1,
    66272, 0,
    66421, 1,
    66426, 0,
    68096, 1,
    68099, 0,
    68100, 1,
    68102, 0,
    68107, 1,
    68111, 0,
    68151, 1,
    68154, 0,
    68158, 1,
    68159, 0,
    68324, 1,
    68326, 0,
    68899, 1,
    68903, 0,
    69290, 1,
    69292, 0,
    69445, 1,
    69456, 0,
    69631, 1,
    69634, 0,
    69687, 1,
    69702, 0,
    69758, 1,
    69762, 0,
    69807, 1,
    69818, 0,
    69820, 1,
    69821, 0,
    69836, 1,
    69837, 0,
    69887, 1,
    69890, 0,
    69926, 1,
    69940, 0,
    69956, 1,
    69958, 0,
    70002, 1,
    70003, 0,
    70015, 1,
    70018, 0,
    70066, 1,
    70080, 0,
    70088, 1,
    70092, 0,
    70093, 1,
    70095, 0,
    70187, 1,
    70199, 0,
    70205, 1,
    70206, 0,
    70366, 1,
    70378, 0,
    70399, 1,
    70403, 0,
    70458, 1,
    70460, 0,
    70461, 1,
    70468, 0,
    70470, 1,
    70472, 0,
    70474, 1,
    70477, 0,
    70486, 1,
    70487, 0,
    70497, 1,
    70499, 0,
    70501, 1,
    70508, 0,
    70511, 1,
    70516, 0,
    70708, 1,
    70726, 0,
    70749, 1,
    70750, 0,
    70831, 1,
    70851, 0,
    71086, 1,
    71093, 0,
    71095, 1,
    71104, 0,
    71131, 1,
    71133, 0,
    71215, 1,
    71232, 0,
    71338, 1,
    71351, 0,
    71452, 1,
    71467, 0,
    71723, 1,
    71738, 0,
    71983, 1,
    71989, 0,
    71990, 1,
    71992, 0,
    71994, 1,
    71998, 0,
    71999, 1,
    72000, 0,
    72001, 1,
    72003, 0,
    72144, 1,
    72151, 0,
    72153, 1,
    72160, 0,
    72163, 1,
    72164, 0,
    72192, 1,
    72202, 0,
    72242, 1,
    72249, 0,
    72250, 1,
    72254, 0,
    72262, 1,
    72263, 0,
    72272, 1,
    72283, 0,
    72329, 1,
    72345, 0,
    72750, 1,
    72758, 0,
    72759, 1,
    72767, 0,
    72849, 1,
    72871, 0,
    72872, 1,
    72886, 0,
    73008, 1,
    73014, 0,
    73017, 1,
    73018, 0,
    73019, 1,
    73021, 0,
    73022, 1,
    73029, 0,
    73030, 1,
    73031, 0,
    73097, 1,
    73102, 0,
    73103, 1,
    73105, 0,
    73106, 1,
    73111, 0,
    73458, 1,
    73462, 0,
    78895, 1,
    78904, 0,
    92911, 1,
    92916, 0,
    92975, 1,
    92982, 0,
    94030, 1,
    94031, 0,
    94032, 1,
    94087, 0,
    94094, 1,
    94098, 0,
    94175, 1,
    94179, 2,
    94180, 0,
    94191, 1,
    94193, 2,
    94207, 1,
    100343, 2,
    100351, 1,
    101589, 2,
    101631, 1,
    101640, 2,
    110591, 1,
    110878, 2,
    110927, 1,
    110930, 2,
    110947, 1,
    110951, 2,
    110959, 1,
    111355, 2,
    113820, 1,
    113822, 0,
    113823, 1,
    113827, 0,
    119140, 1,
    119145, 0,
    119148, 1,
    119170, 0,
    119172, 1,
    119179, 0,
    119209, 1,
    119213, 0,
    119361, 1,
    119364, 0,
    121343, 1,
    121398, 0,
    121402, 1,
    121452, 0,
    121460, 1,
    121461, 0,
    121475, 1,
    121476, 0,
    121498, 1,
    121503, 0,
    121504, 1,
    121519, 0,
    122879, 1,
    122886, 0,
    122887, 1,
    122904, 0,
    122906, 1,
    122913, 0,
    122914, 1,
    122916, 0,
    122917, 1,
    122922, 0,
    123183, 1,
    123190, 0,
    123627, 1,
    123631, 0,
    125135, 1,
    125142, 0,
    125251, 1,
    125258, 0,
    126979, 1,
    126980, 2,
    127182, 1,
    127183, 2,
    127373, 1,
    127374, 2,
    127376, 1,
    127386, 2,
    127487, 1,
    127490, 2,
    127503, 1,
    127547, 2,
    127551, 1,
    127560, 2,
    127567, 1,
    127569, 2,
    127583, 1,
    127589, 2,
    127743, 1,
    127776, 2,
    127788, 1,
    127797, 2,
    127798, 1,
    127868, 2,
    127869, 1,
    127891, 2,
    127903, 1,
    127946, 2,
    127950, 1,
    127955, 2,
    127967, 1,
    127984, 2,
    127987, 1,
    127988, 2,
    127991, 1,
    128062, 2,
    128063, 1,
    128064, 2,
    128065, 1,
    128252, 2,
    128254, 1,
    128317, 2,
    128330, 1,
    128334, 2,
    128335, 1,
    128359, 2,
    128377, 1,
    128378, 2,
    128404, 1,
    128406, 2,
    128419, 1,
    128420, 2,
    128506, 1,
    128591, 2,
    128639, 1,
    128709, 2,
    128715, 1,
    128716, 2,
    128719, 1,
    128722, 2,
    128724, 1,
    128727, 2,
    128746, 1,
    128748, 2,
    128755, 1,
    128764, 2,
    128991, 1,
    129003, 2,
    129291, 1,
    129338, 2,
    129339, 1,
    129349, 2,
    129350, 1,
    129400, 2,
    129401, 1,
    129483, 2,
    129484, 1,
    129535, 2,
    129647, 1,
    129652, 2,
    129655, 1,
    129658, 2,
    129663, 1,
    129670, 2,
    129679, 1,
    129704, 2,
    129711, 1,
    129718, 2,
    129727, 1,
    129730, 2,
    129743, 1,
    129750, 2,
    131071, 1,
    173789, 2,
    173823, 1,
    177972, 2,
    177983, 1,
    178205, 2,
    178207, 1,
    183969, 2,
    183983, 1,
    191456, 2,
    194559, 1,
    195101, 2,
    196607, 1,
    201546, 2,
    917504, 1,
    917505, 0,
    917535, 1,
    917631, 0,
    917759, 1,
    917999, 0,
    1114111, 1,
    NULL
};


static short byte_encoding = ENC_UTF8;


static PyObject * to_bool(int val)
{
    if (val)  Py_RETURN_TRUE;
    else  Py_RETURN_FALSE;
}


//======================================================================
static char get_byte_encoding_doc[] =
"get_byte_encoding() -> string encoding\n\n\
Get byte encoding ('utf8', 'wide', or 'narrow').";

static PyObject * get_byte_encoding(PyObject *self, PyObject *args)
{
    if (!PyArg_ParseTuple(args, ""))
        return NULL;

    if (byte_encoding == ENC_UTF8)
        return Py_BuildValue("s", "utf8");
    if (byte_encoding == ENC_WIDE)
        return Py_BuildValue("s", "wide");
    if (byte_encoding == ENC_NARROW)
        return Py_BuildValue("s", "narrow");
    Py_RETURN_NONE; // should never happen
}


//======================================================================
static char set_byte_encoding_doc[] =
"set_byte_encoding(string encoding) -> None\n\n\
Set byte encoding. \n\n\
encoding -- one of 'utf8', 'wide', 'narrow'";

static PyObject * set_byte_encoding(PyObject *self, PyObject *args)
{
    char * enc;
    
    if (!PyArg_ParseTuple(args, "s", &enc))
        return NULL;

    if (strcmp(enc, "utf8") == 0)
        byte_encoding = ENC_UTF8;
    else if (strcmp(enc, "wide") == 0)
        byte_encoding = ENC_WIDE;
    else if (strcmp(enc, "narrow") == 0)
        byte_encoding = ENC_NARROW;
    else
    {
        // got wrong encoding
        PyErr_SetString(PyExc_ValueError, "Unknown encoding.");
        return NULL;
    }
    
    Py_RETURN_NONE;
}


//======================================================================
static char get_width_doc[] =
"get_width(int ord) -> int width\n\n\
Return the screen column width for unicode ordinal ord.\n\n\
ord -- ordinal";


static int Py_GetWidth(long int ord)
{
    int i;

    if ((ord == 0xe) || (ord == 0xf))
            return 0;

    for (i=0; ; i+=2)
    {
        if ( widths[i] == NULL )
            return widths[i-1];
        if (ord <= widths[i])
        {
            return widths[i+1];
        }
    }

    return 1;
}


static PyObject * get_width(PyObject *self, PyObject *args)
{
    long int ord;
    int ret;
    
    if (!PyArg_ParseTuple(args, "l", &ord))
        return NULL;

    ret = Py_GetWidth(ord);
    return Py_BuildValue("i", ret);
}


//======================================================================
static char decode_one_doc[] =
"decode_one(string text, int pos) -> (int ord, int nextpos)\n\n\
Return (ordinal at pos, next position) for UTF-8 encoded text.\n\n\
text -- string text\n\
pos -- position in text";


static void Py_DecodeOne(const unsigned char *text, Py_ssize_t text_len,
                         Py_ssize_t pos, Py_ssize_t *ret)
{
    int dummy;
    
    if (!(text[pos]&0x80))
    {
        ret[0] = text[pos];
        ret[1] = pos+1;
        return;
    }

    if (text_len - pos < 2) //error
    {
        ret[0] = '?';
        ret[1] = pos+1;
        return;
    }

    if ((text[pos]&0xe0) == 0xc0)
    {
        if ((text[pos+1]&0xc0) != 0x80) //error
        {
            ret[0] = '?';
            ret[1] = pos+1;
            return;
        }

        dummy = ((text[pos]&0x1f)<<6) | (text[pos+1]&0x3f);
        if (dummy < 0x80) //error
        {
            ret[0] = '?';
            ret[1] = pos+1;
            return;
        }

        ret[0] = dummy;
        ret[1] = pos+2;
        return;
    }
    
    if (text_len - pos < 3) //error
        {
            ret[0] = '?';
            ret[1] = pos + 1;
            return;
        }

    if ((text[pos]&0xf0) == 0xe0)
    {
        if ((text[pos+1]&0xc0) != 0x80) //error
        {
            ret[0] = '?';
            ret[1] = pos + 1;
            return;
        }
        
        if ((text[pos+2]&0xc0) != 0x80) //error
        {
            ret[0] = '?';
            ret[1] = pos + 1;
            return;
        }

        dummy = ((text[pos]&0x0f) << 12) | ((text[pos+1]&0x3f) << 6) |
            (text[pos+2]&0x3f);
        if (dummy < 0x800) //error
        {
            ret[0] = '?';
            ret[1] = pos + 1;
            return;
        }

        ret[0] = dummy;
        ret[1] = pos + 3;
        return;
    }

    if (text_len - pos < 4)
    {
        ret[0] = '?';
        ret[1] = pos + 1;
        return;
    }

    if ((text[pos]&0xf8) == 0xf0)
    {
        if ((text[pos+1]&0xc0) != 0x80) //error
        {
            ret[0] = '?';
            ret[1] = pos + 1;
            return;
        }
        
        if ((text[pos+2]&0xc0) != 0x80) //error
        {
            ret[0] = '?';
            ret[1] = pos + 1;
            return;
        }

        if ((text[pos+3]&0xc0) != 0x80) //error
        {
            ret[0] = '?';
            ret[1] = pos + 1;
            return;
        }

        dummy = ((text[pos]&0x07) << 18) | ((text[pos+1]&0x3f) << 12) |
            ((text[pos+2]&0x3f) << 6) | (text[pos+3]&0x3f);
        if (dummy < 0x10000) //error
        {
            ret[0] = '?';
            ret[1] = pos + 1;
            return;
        }
             
        ret[0] = dummy;
        ret[1] = pos + 4;
        return;
    }
        
    ret[0] = '?';
    ret[1] = pos + 1;
    return;
    
}


static PyObject * decode_one(PyObject *self, PyObject *args)
{
    PyObject *py_text;

    Py_ssize_t pos, text_len;
    char *text;
    Py_ssize_t ret[2];

    if (!PyArg_ParseTuple(args, "O" FMT_N, &py_text, &pos))
        return NULL;

#ifndef PYTHON3
    PyString_AsStringAndSize(py_text, &text, &text_len);
#else
    PyBytes_AsStringAndSize(py_text, &text, &text_len);
#endif

    Py_DecodeOne((unsigned char *)text, text_len, pos, ret);
    return Py_BuildValue("(" FMT_N ", " FMT_N ")", ret[0], ret[1]);
}

                                     

//======================================================================
static char decode_one_right_doc[] =
"decode_one_right(string text, int pos) -> (int ord, int nextpos)\n\n\
Return (ordinal at pos, next position) for UTF-8 encoded text.\n\
pos is assumed to be on the trailing byte of a utf-8 sequence.\n\
text -- text string \n\
pos -- position in text";


static void Py_DecodeOneRight(const unsigned char *text, Py_ssize_t text_len,
                             Py_ssize_t pos, Py_ssize_t *ret)
{
    Py_ssize_t subret[2];

    while (pos >= 0)
    {
        if ((text[pos]&0xc0) != 0x80)
        {
            Py_DecodeOne(text, text_len, pos, subret);
            ret[0] = subret[0];
            ret[1] = pos-1;
            return;
        }
        pos-=1;
        
        if (pos == pos-4) //error
        {
            ret[0] = '?';
            ret[1] = pos - 1;
            return;
        }
    }
}


static PyObject * decode_one_right(PyObject *self, PyObject *args)
{

    PyObject *py_text;

    Py_ssize_t pos, text_len;
    char *text;
    Py_ssize_t ret[2] = {'?',0};

    if (!PyArg_ParseTuple(args, "O" FMT_N, &py_text, &pos))
        return NULL;

#ifndef PYTHON3
    PyString_AsStringAndSize(py_text, &text, &text_len);
#else
    PyBytes_AsStringAndSize(py_text, &text, &text_len);
#endif

    Py_DecodeOneRight((const unsigned char *)text, text_len, pos, ret);
    return Py_BuildValue("(" FMT_N ", " FMT_N ")", ret[0], ret[1]);
}


//======================================================================
static char within_double_byte_doc[] =
"within_double_byte(strint text, int line_start, int pos) -> int withindb\n\n\
Return whether pos is within a double-byte encoded character.\n\n\
str -- string in question\n\
line_start -- offset of beginning of line (< pos)\n\
pos -- offset in question\n\n\
Return values:\n\
0 -- not within dbe char, or double_byte_encoding == False\n\
1 -- pos is on the 1st half of a dbe char\n\
2 -- pos is on the 2nd half of a dbe char";


static int Py_WithinDoubleByte(const unsigned char *str, Py_ssize_t line_start,
                               Py_ssize_t pos)
{
    Py_ssize_t i;

    if ((str[pos] >= 0x40) && (str[pos] < 0x7f))
    {
        //might be second half of big5, uhc or gbk encoding
        if (pos == line_start)  return 0;

        if (str[pos-1] >= 0x81)
        {
            if ((Py_WithinDoubleByte(str, line_start, pos-1)) == 1)  return 2;
            else return 0;
        }
    }

    if (str[pos] < 0x80)  return 0;
    
    for (i=pos-1; i>=line_start; i--)
        if (str[i] < 0x80)  break;
    
    if ((pos-i) & 1)  return 1;
    else  return 2;
}


static PyObject * within_double_byte(PyObject *self, PyObject *args)
{
    const unsigned char *str;
    Py_ssize_t str_len, line_start, pos;
    Py_ssize_t ret;

    if (!PyArg_ParseTuple(args, "s#" FMT_N FMT_N, &str, &str_len, &line_start, &pos))
        return NULL;
    if (line_start < 0 || line_start >= str_len) {
        PyErr_SetString(PyExc_IndexError,
            "is_wide_char: Argument \"line_start\" is outside of string.");
        return NULL;
    }
    if (pos < 0 || pos >= str_len) {
        PyErr_SetString(PyExc_IndexError,
            "is_wide_char: Argument \"pos\" is outside of string.");
        return NULL;
    }
    if (pos < line_start) {
        PyErr_SetString(PyExc_IndexError,
            "is_wide_char: Argument \"pos\" is before \"line_start\".");
        return NULL;
    }

    ret = Py_WithinDoubleByte(str, line_start, pos);
    return Py_BuildValue(FMT_N, ret);
}


//======================================================================
char is_wide_char_doc[] =
"is_wide_char(string/unicode text, int offs) -> bool iswide\n\n\
Test if the character at offs within text is wide.\n\n\
text -- string or unicode text\n\
offs -- offset";

static int Py_IsWideChar(PyObject *text, Py_ssize_t offs)
{
    const unsigned char *str;
    Py_UNICODE *ustr;
    Py_ssize_t ret[2], str_len;

    if (PyUnicode_Check(text))  //text_py is unicode string
    {
        ustr = PyUnicode_AS_UNICODE(text);
        return (Py_GetWidth((long int)ustr[offs]) == 2);
    }

#ifndef PYTHON3
    if (!PyString_Check(text)) {
#else
    if (!PyBytes_Check(text)) {
#endif
        PyErr_SetString(PyExc_TypeError,
            "is_wide_char: Argument \"text\" is not a string.");
        return -1;
    }

#ifndef PYTHON3
    str = (const unsigned char *)PyString_AsString(text);
    str_len = (int) PyString_Size(text);
#else
    str = (const unsigned char *)PyBytes_AsString(text);
    str_len = (int) PyBytes_Size(text);
#endif

    if (byte_encoding == ENC_UTF8)
    {
        Py_DecodeOne(str, str_len, offs, ret);
        return (Py_GetWidth(ret[0]) == 2);
    }

    if (byte_encoding == ENC_WIDE)
        return (Py_WithinDoubleByte(str, offs, offs) == 1);

    return 0;
}


static PyObject * is_wide_char(PyObject *self, PyObject *args)
{
    PyObject *text;
    Py_ssize_t offs;
    int ret;

    if (!PyArg_ParseTuple(args, "O" FMT_N, &text, &offs))
        return NULL;

    ret = Py_IsWideChar(text, offs);

    if ( ret == -1) // error
        return NULL;

    return Py_BuildValue("O", to_bool(ret));
}


//======================================================================
char move_prev_char_doc[] =
"move_prev_char(string/unicode text, int start_offs, int end_offs) -> int pos\n\n\
Return the position of the character before end_offs.\n\n\
text -- string or unicode text\n\
start_offs -- start offset\n\
end_offs -- end offset";


static Py_ssize_t Py_MovePrevChar(PyObject *text, Py_ssize_t start_offs,
                           Py_ssize_t end_offs)
{
    Py_ssize_t position;
    unsigned char *str;

    if (PyUnicode_Check(text))  //text_py is unicode string
        return end_offs-1;
    else
#ifndef PYTHON3
        str = (unsigned char *)PyString_AsString(text);
#else
        str = (unsigned char *)PyBytes_AsString(text);
#endif

    if (byte_encoding == ENC_UTF8) //encoding is utf8
    {
        position = end_offs - 1;
        while ((position > start_offs) && (str[position]&0xc0) == 0x80)
            position -=1;
        return position;
    }
    else if ((byte_encoding == ENC_WIDE) &&
             (Py_WithinDoubleByte(str, start_offs, end_offs-1) == 2))
        return end_offs-2;
    else
        return end_offs-1;
}


static PyObject * move_prev_char(PyObject *self, PyObject *args)
{
    PyObject *text;
    Py_ssize_t start_offs, end_offs;
    Py_ssize_t ret;

    if (!PyArg_ParseTuple(args, "O" FMT_N FMT_N, &text, &start_offs, &end_offs))
        return NULL; 

    ret = Py_MovePrevChar(text, start_offs, end_offs);
    return Py_BuildValue(FMT_N, ret);
}


//======================================================================
char move_next_char_doc[] =
"move_next_char(string/unicode text, int start_offs, int end_offs) -> int pos\n\n\
Return the position of the character after start_offs.\n\n\
text -- string or unicode text\n\
start_offs -- start offset\n\
end_offs -- end offset";


static Py_ssize_t Py_MoveNextChar(PyObject *text, Py_ssize_t start_offs,
                           Py_ssize_t end_offs)
{
    Py_ssize_t position;
    unsigned char * str;

    if (PyUnicode_Check(text))  //text_py is unicode string
        return start_offs+1;
    else
#ifndef PYTHON3
        str = (unsigned char *)PyString_AsString(text);
#else
        str = (unsigned char *)PyBytes_AsString(text);
#endif

    if (byte_encoding == ENC_UTF8) //encoding is utf8
    {
        position = start_offs + 1;
        while ((position < end_offs) && ((str[position]&0xc0) == 0x80))
            position +=1;

         return position;
    }
    else if ((byte_encoding == ENC_WIDE) &&
             (Py_WithinDoubleByte(str, start_offs, start_offs) == 1))
        return start_offs+2;
    else
        return start_offs+1;
}


static PyObject * move_next_char(PyObject *self, PyObject *args)
{
    PyObject *text;
    Py_ssize_t start_offs, end_offs;
    Py_ssize_t ret;

    if (!PyArg_ParseTuple(args, "O" FMT_N FMT_N, &text, &start_offs, &end_offs))
        return NULL;

    ret = Py_MoveNextChar(text, start_offs, end_offs);
    return Py_BuildValue(FMT_N, ret);
}


//======================================================================
char calc_width_doc[] =
"calc_width(string/unicode text, int start_off, int end_offs) -> int width\n\n\
Return the screen column width of text between start_offs and end_offs.\n\n\
text -- string or unicode text\n\
start_offs -- start offset\n\
end_offs -- end offset";


static Py_ssize_t Py_CalcWidth(PyObject *text, Py_ssize_t start_offs,
                        Py_ssize_t end_offs)
{
    unsigned char * str;
    Py_ssize_t i, ret[2], str_len;
    int screencols;
    Py_UNICODE *ustr;

    if (PyUnicode_Check(text))  //text_py is unicode string
    {
        ustr = PyUnicode_AS_UNICODE(text);
        screencols = 0;
 
        for(i=start_offs; i<end_offs; i++) 
            screencols += Py_GetWidth(ustr[i]);

        return screencols;
    }

#ifndef PYTHON3
    if (!PyString_Check(text))
#else
    if (!PyBytes_Check(text))
#endif
    {
        PyErr_SetString(PyExc_TypeError, "Neither unicode nor string.");
        return -1;
    }

#ifndef PYTHON3
    str = (unsigned char *)PyString_AsString(text);
    str_len = (int) PyString_Size(text);
#else
    str = (unsigned char *)PyBytes_AsString(text);
    str_len = PyBytes_Size(text);
#endif

    if (byte_encoding == ENC_UTF8)
    {
        i = start_offs;
        screencols = 0;

        while (i<end_offs) {
            Py_DecodeOne(str, str_len, i, ret);
            screencols += Py_GetWidth(ret[0]);
            i = ret[1];
        }

        return screencols;
    }

    return end_offs - start_offs; // "wide" and "narrow"    
}


static PyObject * calc_width(PyObject *self, PyObject *args)
{
    PyObject *text;
    int start_offs, end_offs;
    long ret;

    if (!PyArg_ParseTuple(args, "Oii", &text, &start_offs, &end_offs))
        return NULL; 

    ret = Py_CalcWidth(text, start_offs, end_offs);
    if (ret==-1) //an error occurred
        return NULL;

    return Py_BuildValue("l", ret);
}


//======================================================================
char calc_text_pos_doc[] =
"calc_text_pos(string/unicode text, int start_offs, int end_offs, int pref_col)\n\
-> (int pos, int actual_col)\n\n\
Calculate the closest position to the screen column pref_col in text\n\
where start_offs is the offset into text assumed to be screen column 0\n\
and end_offs is the end of the range to search.\n\n\
Returns (position, actual_col).\n\n\
text -- string or unicode text\n\
start_offs -- start offset\n\
end_offs -- end offset\n\
pref_col -- preferred column";


static int Py_CalcTextPos(PyObject *text, Py_ssize_t start_offs,
                          Py_ssize_t end_offs, int pref_col, Py_ssize_t *ret)
{
    unsigned char * str;
    Py_ssize_t i, dummy[2], str_len;
    int screencols, width;
    Py_UNICODE *ustr;

    if (PyUnicode_Check(text))  //text_py is unicode string
    {
        ustr = PyUnicode_AS_UNICODE(text);
        screencols = 0;
 
        for(i=start_offs; i<end_offs; i++)
        {
            width = Py_GetWidth(ustr[i]);
            
            if (width+screencols > pref_col)
            {
                ret[0] = i;
                ret[1] = screencols;
                return 0;
            }

            screencols += width;
        }
        
        ret[0] = i;
        ret[1] = screencols;
        return 0;
    }

#ifndef PYTHON3
    if (!PyString_Check(text))
#else
    if (!PyBytes_Check(text))
#endif
    {
        PyErr_SetString(PyExc_TypeError, "Neither unicode nor string.");
        return -1;
    }

#ifndef PYTHON3
    str = (unsigned char *)PyString_AsString(text);
    str_len = (int) PyString_Size(text);
#else
    str = (unsigned char *)PyBytes_AsString(text);
    str_len = PyBytes_Size(text);
#endif
    
    if (byte_encoding == ENC_UTF8)
    {
        i = start_offs;
        screencols = 0;

        while (i<end_offs)
        {
            Py_DecodeOne(str, str_len, i, dummy);
            width = Py_GetWidth(dummy[0]);

            if (width+screencols > pref_col)
            {
                ret[0] = i;
                ret[1] = screencols;
                return 0;
            }

            i = dummy[1];
            screencols += width;
        }
        
        ret[0] = i;
        ret[1] = screencols;
        return 0;
    }

    // "wide" and "narrow"
    i = start_offs + pref_col;

    if (i>= end_offs)
    {
        ret[0] = end_offs;
        ret[1] = end_offs - start_offs;
        return 0;
    }

    if (byte_encoding == ENC_WIDE)
        if (Py_WithinDoubleByte(str, start_offs, i)==2)
            i -= 1;

    ret[0] = i;
    ret[1] = i - start_offs;
    return 0;
}


static PyObject * calc_text_pos(PyObject *self, PyObject *args)
{
    PyObject *text;
    Py_ssize_t start_offs, end_offs, ret[2];
    int pref_col, err;

    if (!PyArg_ParseTuple(args, "O" FMT_N FMT_N "i", &text, &start_offs, &end_offs,
                          &pref_col))
        return NULL;

    err = Py_CalcTextPos(text, start_offs, end_offs, pref_col, ret);
    if (err==-1) //an error occurred
        return NULL;

    return Py_BuildValue("(" FMT_N FMT_N ")", ret[0], ret[1]);
}


//======================================================================

static PyMethodDef Str_UtilMethods[] = {
    {"get_byte_encoding", get_byte_encoding, METH_VARARGS,
     get_byte_encoding_doc},
    {"set_byte_encoding", set_byte_encoding, METH_VARARGS,
     set_byte_encoding_doc},
    {"get_width", get_width, METH_VARARGS, get_width_doc},
    {"decode_one", decode_one, METH_VARARGS, decode_one_doc},
    {"decode_one_right", decode_one_right, METH_VARARGS, decode_one_right_doc},
    {"within_double_byte", within_double_byte, METH_VARARGS,
     within_double_byte_doc},
    {"is_wide_char", is_wide_char, METH_VARARGS, is_wide_char_doc},
    {"move_prev_char", move_prev_char, METH_VARARGS, move_prev_char_doc},
    {"move_next_char", move_next_char, METH_VARARGS, move_next_char_doc},
    {"calc_width", calc_width, METH_VARARGS, calc_width_doc},
    {"calc_text_pos", calc_text_pos, METH_VARARGS, calc_text_pos_doc},
    {NULL, NULL, 0, NULL}        // Sentinel 
};

#ifndef PYTHON3
PyMODINIT_FUNC initstr_util(void)
{
    Py_InitModule("str_util", Str_UtilMethods);
}

int main(int argc, char *argv[])
{
    //Pass argv[0] to the Python interpreter:
    Py_SetProgramName(argv[0]);

    //Initialize the Python interpreter. 
    Py_Initialize();

    //Add a static module:
    initstr_util();

    return 0;
}
#else
static struct PyModuleDef Str_UtilModule = {
    PyModuleDef_HEAD_INIT,
    "str_util",
    NULL,
    -1,
    Str_UtilMethods
};

PyMODINIT_FUNC PyInit_str_util(void)
{
    return PyModule_Create(&Str_UtilModule);
}
#endif
