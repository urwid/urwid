#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Urwid unicode character processing tables
#    Copyright (C) 2004-2011  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/

from __future__ import division, print_function

import re

from urwid.compat import bytes, B, ord2, text_type

SAFE_ASCII_RE = re.compile(u"^[ -~]*$")
SAFE_ASCII_BYTES_RE = re.compile(B("^[ -~]*$"))

_byte_encoding = None

# GENERATED DATA
# generated from
# http://www.unicode.org/Public/4.0-Update/EastAsianWidth-4.0.0.txt

widths = [
    (8, 0),
    (9, 8),
    (31, 0),
    (126, 1),
    (159, 0),
    (767, 1),
    (879, 0),
    (1154, 1),
    (1161, 0),
    (1424, 1),
    (1469, 0),
    (1470, 1),
    (1471, 0),
    (1472, 1),
    (1474, 0),
    (1475, 1),
    (1477, 0),
    (1478, 1),
    (1479, 0),
    (1535, 1),
    (1541, 0),
    (1551, 1),
    (1562, 0),
    (1563, 1),
    (1564, 0),
    (1610, 1),
    (1631, 0),
    (1647, 1),
    (1648, 0),
    (1749, 1),
    (1757, 0),
    (1758, 1),
    (1764, 0),
    (1766, 1),
    (1768, 0),
    (1769, 1),
    (1773, 0),
    (1806, 1),
    (1807, 0),
    (1808, 1),
    (1809, 0),
    (1839, 1),
    (1866, 0),
    (1957, 1),
    (1968, 0),
    (2026, 1),
    (2035, 0),
    (2044, 1),
    (2045, 0),
    (2069, 1),
    (2073, 0),
    (2074, 1),
    (2083, 0),
    (2084, 1),
    (2087, 0),
    (2088, 1),
    (2093, 0),
    (2136, 1),
    (2139, 0),
    (2258, 1),
    (2307, 0),
    (2361, 1),
    (2364, 0),
    (2365, 1),
    (2383, 0),
    (2384, 1),
    (2391, 0),
    (2401, 1),
    (2403, 0),
    (2432, 1),
    (2435, 0),
    (2491, 1),
    (2492, 0),
    (2493, 1),
    (2500, 0),
    (2502, 1),
    (2504, 0),
    (2506, 1),
    (2509, 0),
    (2518, 1),
    (2519, 0),
    (2529, 1),
    (2531, 0),
    (2557, 1),
    (2558, 0),
    (2560, 1),
    (2563, 0),
    (2619, 1),
    (2620, 0),
    (2621, 1),
    (2626, 0),
    (2630, 1),
    (2632, 0),
    (2634, 1),
    (2637, 0),
    (2640, 1),
    (2641, 0),
    (2671, 1),
    (2673, 0),
    (2676, 1),
    (2677, 0),
    (2688, 1),
    (2691, 0),
    (2747, 1),
    (2748, 0),
    (2749, 1),
    (2757, 0),
    (2758, 1),
    (2761, 0),
    (2762, 1),
    (2765, 0),
    (2785, 1),
    (2787, 0),
    (2809, 1),
    (2815, 0),
    (2816, 1),
    (2819, 0),
    (2875, 1),
    (2876, 0),
    (2877, 1),
    (2884, 0),
    (2886, 1),
    (2888, 0),
    (2890, 1),
    (2893, 0),
    (2900, 1),
    (2903, 0),
    (2913, 1),
    (2915, 0),
    (2945, 1),
    (2946, 0),
    (3005, 1),
    (3010, 0),
    (3013, 1),
    (3016, 0),
    (3017, 1),
    (3021, 0),
    (3030, 1),
    (3031, 0),
    (3071, 1),
    (3076, 0),
    (3133, 1),
    (3140, 0),
    (3141, 1),
    (3144, 0),
    (3145, 1),
    (3149, 0),
    (3156, 1),
    (3158, 0),
    (3169, 1),
    (3171, 0),
    (3200, 1),
    (3203, 0),
    (3259, 1),
    (3260, 0),
    (3261, 1),
    (3268, 0),
    (3269, 1),
    (3272, 0),
    (3273, 1),
    (3277, 0),
    (3284, 1),
    (3286, 0),
    (3297, 1),
    (3299, 0),
    (3327, 1),
    (3331, 0),
    (3386, 1),
    (3388, 0),
    (3389, 1),
    (3396, 0),
    (3397, 1),
    (3400, 0),
    (3401, 1),
    (3405, 0),
    (3414, 1),
    (3415, 0),
    (3425, 1),
    (3427, 0),
    (3456, 1),
    (3459, 0),
    (3529, 1),
    (3530, 0),
    (3534, 1),
    (3540, 0),
    (3541, 1),
    (3542, 0),
    (3543, 1),
    (3551, 0),
    (3569, 1),
    (3571, 0),
    (3632, 1),
    (3633, 0),
    (3635, 1),
    (3642, 0),
    (3654, 1),
    (3662, 0),
    (3760, 1),
    (3761, 0),
    (3763, 1),
    (3772, 0),
    (3783, 1),
    (3789, 0),
    (3863, 1),
    (3865, 0),
    (3892, 1),
    (3893, 0),
    (3894, 1),
    (3895, 0),
    (3896, 1),
    (3897, 0),
    (3901, 1),
    (3903, 0),
    (3952, 1),
    (3972, 0),
    (3973, 1),
    (3975, 0),
    (3980, 1),
    (3991, 0),
    (3992, 1),
    (4028, 0),
    (4037, 1),
    (4038, 0),
    (4138, 1),
    (4158, 0),
    (4181, 1),
    (4185, 0),
    (4189, 1),
    (4192, 0),
    (4193, 1),
    (4196, 0),
    (4198, 1),
    (4205, 0),
    (4208, 1),
    (4212, 0),
    (4225, 1),
    (4237, 0),
    (4238, 1),
    (4239, 0),
    (4249, 1),
    (4253, 0),
    (4351, 1),
    (4447, 2),
    (4956, 1),
    (4959, 0),
    (5905, 1),
    (5908, 0),
    (5937, 1),
    (5940, 0),
    (5969, 1),
    (5971, 0),
    (6001, 1),
    (6003, 0),
    (6067, 1),
    (6099, 0),
    (6108, 1),
    (6109, 0),
    (6154, 1),
    (6158, 0),
    (6276, 1),
    (6278, 0),
    (6312, 1),
    (6313, 0),
    (6431, 1),
    (6443, 0),
    (6447, 1),
    (6459, 0),
    (6678, 1),
    (6683, 0),
    (6740, 1),
    (6750, 0),
    (6751, 1),
    (6780, 0),
    (6782, 1),
    (6783, 0),
    (6831, 1),
    (6848, 0),
    (6911, 1),
    (6916, 0),
    (6963, 1),
    (6980, 0),
    (7018, 1),
    (7027, 0),
    (7039, 1),
    (7042, 0),
    (7072, 1),
    (7085, 0),
    (7141, 1),
    (7155, 0),
    (7203, 1),
    (7223, 0),
    (7375, 1),
    (7378, 0),
    (7379, 1),
    (7400, 0),
    (7404, 1),
    (7405, 0),
    (7411, 1),
    (7412, 0),
    (7414, 1),
    (7417, 0),
    (7615, 1),
    (7673, 0),
    (7674, 1),
    (7679, 0),
    (8202, 1),
    (8207, 0),
    (8231, 1),
    (8238, 0),
    (8287, 1),
    (8292, 0),
    (8293, 1),
    (8303, 0),
    (8399, 1),
    (8432, 0),
    (8985, 1),
    (8987, 2),
    (9000, 1),
    (9002, 2),
    (9192, 1),
    (9196, 2),
    (9199, 1),
    (9200, 2),
    (9202, 1),
    (9203, 2),
    (9724, 1),
    (9726, 2),
    (9747, 1),
    (9749, 2),
    (9799, 1),
    (9811, 2),
    (9854, 1),
    (9855, 2),
    (9874, 1),
    (9875, 2),
    (9888, 1),
    (9889, 2),
    (9897, 1),
    (9899, 2),
    (9916, 1),
    (9918, 2),
    (9923, 1),
    (9925, 2),
    (9933, 1),
    (9934, 2),
    (9939, 1),
    (9940, 2),
    (9961, 1),
    (9962, 2),
    (9969, 1),
    (9971, 2),
    (9972, 1),
    (9973, 2),
    (9977, 1),
    (9978, 2),
    (9980, 1),
    (9981, 2),
    (9988, 1),
    (9989, 2),
    (9993, 1),
    (9995, 2),
    (10023, 1),
    (10024, 2),
    (10059, 1),
    (10060, 2),
    (10061, 1),
    (10062, 2),
    (10066, 1),
    (10069, 2),
    (10070, 1),
    (10071, 2),
    (10132, 1),
    (10135, 2),
    (10159, 1),
    (10160, 2),
    (10174, 1),
    (10175, 2),
    (11034, 1),
    (11036, 2),
    (11087, 1),
    (11088, 2),
    (11092, 1),
    (11093, 2),
    (11502, 1),
    (11505, 0),
    (11646, 1),
    (11647, 0),
    (11743, 1),
    (11775, 0),
    (11903, 1),
    (11929, 2),
    (11930, 1),
    (12019, 2),
    (12031, 1),
    (12245, 2),
    (12271, 1),
    (12283, 2),
    (12287, 1),
    (12329, 2),
    (12333, 0),
    (12350, 2),
    (12352, 1),
    (12438, 2),
    (12440, 1),
    (12442, 0),
    (12543, 2),
    (12548, 1),
    (12591, 2),
    (12592, 1),
    (12686, 2),
    (12687, 1),
    (12771, 2),
    (12783, 1),
    (12830, 2),
    (12831, 1),
    (12871, 2),
    (12879, 1),
    (19903, 2),
    (19967, 1),
    (40956, 2),
    (40959, 1),
    (42124, 2),
    (42127, 1),
    (42182, 2),
    (42606, 1),
    (42610, 0),
    (42611, 1),
    (42621, 0),
    (42653, 1),
    (42655, 0),
    (42735, 1),
    (42737, 0),
    (43009, 1),
    (43010, 0),
    (43013, 1),
    (43014, 0),
    (43018, 1),
    (43019, 0),
    (43042, 1),
    (43047, 0),
    (43051, 1),
    (43052, 0),
    (43135, 1),
    (43137, 0),
    (43187, 1),
    (43205, 0),
    (43231, 1),
    (43249, 0),
    (43262, 1),
    (43263, 0),
    (43301, 1),
    (43309, 0),
    (43334, 1),
    (43347, 0),
    (43359, 1),
    (43388, 2),
    (43391, 1),
    (43395, 0),
    (43442, 1),
    (43456, 0),
    (43492, 1),
    (43493, 0),
    (43560, 1),
    (43574, 0),
    (43586, 1),
    (43587, 0),
    (43595, 1),
    (43597, 0),
    (43642, 1),
    (43645, 0),
    (43695, 1),
    (43696, 0),
    (43697, 1),
    (43700, 0),
    (43702, 1),
    (43704, 0),
    (43709, 1),
    (43711, 0),
    (43712, 1),
    (43713, 0),
    (43754, 1),
    (43759, 0),
    (43764, 1),
    (43766, 0),
    (44002, 1),
    (44010, 0),
    (44011, 1),
    (44013, 0),
    (44031, 1),
    (55203, 2),
    (63743, 1),
    (64109, 2),
    (64111, 1),
    (64217, 2),
    (64285, 1),
    (64286, 0),
    (65023, 1),
    (65039, 0),
    (65049, 2),
    (65055, 1),
    (65071, 0),
    (65106, 2),
    (65107, 1),
    (65126, 2),
    (65127, 1),
    (65131, 2),
    (65278, 1),
    (65279, 0),
    (65280, 1),
    (65376, 2),
    (65503, 1),
    (65510, 2),
    (65528, 1),
    (65531, 0),
    (66044, 1),
    (66045, 0),
    (66271, 1),
    (66272, 0),
    (66421, 1),
    (66426, 0),
    (68096, 1),
    (68099, 0),
    (68100, 1),
    (68102, 0),
    (68107, 1),
    (68111, 0),
    (68151, 1),
    (68154, 0),
    (68158, 1),
    (68159, 0),
    (68324, 1),
    (68326, 0),
    (68899, 1),
    (68903, 0),
    (69290, 1),
    (69292, 0),
    (69445, 1),
    (69456, 0),
    (69631, 1),
    (69634, 0),
    (69687, 1),
    (69702, 0),
    (69758, 1),
    (69762, 0),
    (69807, 1),
    (69818, 0),
    (69820, 1),
    (69821, 0),
    (69836, 1),
    (69837, 0),
    (69887, 1),
    (69890, 0),
    (69926, 1),
    (69940, 0),
    (69956, 1),
    (69958, 0),
    (70002, 1),
    (70003, 0),
    (70015, 1),
    (70018, 0),
    (70066, 1),
    (70080, 0),
    (70088, 1),
    (70092, 0),
    (70093, 1),
    (70095, 0),
    (70187, 1),
    (70199, 0),
    (70205, 1),
    (70206, 0),
    (70366, 1),
    (70378, 0),
    (70399, 1),
    (70403, 0),
    (70458, 1),
    (70460, 0),
    (70461, 1),
    (70468, 0),
    (70470, 1),
    (70472, 0),
    (70474, 1),
    (70477, 0),
    (70486, 1),
    (70487, 0),
    (70497, 1),
    (70499, 0),
    (70501, 1),
    (70508, 0),
    (70511, 1),
    (70516, 0),
    (70708, 1),
    (70726, 0),
    (70749, 1),
    (70750, 0),
    (70831, 1),
    (70851, 0),
    (71086, 1),
    (71093, 0),
    (71095, 1),
    (71104, 0),
    (71131, 1),
    (71133, 0),
    (71215, 1),
    (71232, 0),
    (71338, 1),
    (71351, 0),
    (71452, 1),
    (71467, 0),
    (71723, 1),
    (71738, 0),
    (71983, 1),
    (71989, 0),
    (71990, 1),
    (71992, 0),
    (71994, 1),
    (71998, 0),
    (71999, 1),
    (72000, 0),
    (72001, 1),
    (72003, 0),
    (72144, 1),
    (72151, 0),
    (72153, 1),
    (72160, 0),
    (72163, 1),
    (72164, 0),
    (72192, 1),
    (72202, 0),
    (72242, 1),
    (72249, 0),
    (72250, 1),
    (72254, 0),
    (72262, 1),
    (72263, 0),
    (72272, 1),
    (72283, 0),
    (72329, 1),
    (72345, 0),
    (72750, 1),
    (72758, 0),
    (72759, 1),
    (72767, 0),
    (72849, 1),
    (72871, 0),
    (72872, 1),
    (72886, 0),
    (73008, 1),
    (73014, 0),
    (73017, 1),
    (73018, 0),
    (73019, 1),
    (73021, 0),
    (73022, 1),
    (73029, 0),
    (73030, 1),
    (73031, 0),
    (73097, 1),
    (73102, 0),
    (73103, 1),
    (73105, 0),
    (73106, 1),
    (73111, 0),
    (73458, 1),
    (73462, 0),
    (78895, 1),
    (78904, 0),
    (92911, 1),
    (92916, 0),
    (92975, 1),
    (92982, 0),
    (94030, 1),
    (94031, 0),
    (94032, 1),
    (94087, 0),
    (94094, 1),
    (94098, 0),
    (94175, 1),
    (94179, 2),
    (94180, 0),
    (94191, 1),
    (94193, 2),
    (94207, 1),
    (100343, 2),
    (100351, 1),
    (101589, 2),
    (101631, 1),
    (101640, 2),
    (110591, 1),
    (110878, 2),
    (110927, 1),
    (110930, 2),
    (110947, 1),
    (110951, 2),
    (110959, 1),
    (111355, 2),
    (113820, 1),
    (113822, 0),
    (113823, 1),
    (113827, 0),
    (119140, 1),
    (119145, 0),
    (119148, 1),
    (119170, 0),
    (119172, 1),
    (119179, 0),
    (119209, 1),
    (119213, 0),
    (119361, 1),
    (119364, 0),
    (121343, 1),
    (121398, 0),
    (121402, 1),
    (121452, 0),
    (121460, 1),
    (121461, 0),
    (121475, 1),
    (121476, 0),
    (121498, 1),
    (121503, 0),
    (121504, 1),
    (121519, 0),
    (122879, 1),
    (122886, 0),
    (122887, 1),
    (122904, 0),
    (122906, 1),
    (122913, 0),
    (122914, 1),
    (122916, 0),
    (122917, 1),
    (122922, 0),
    (123183, 1),
    (123190, 0),
    (123627, 1),
    (123631, 0),
    (125135, 1),
    (125142, 0),
    (125251, 1),
    (125258, 0),
    (126979, 1),
    (126980, 2),
    (127182, 1),
    (127183, 2),
    (127373, 1),
    (127374, 2),
    (127376, 1),
    (127386, 2),
    (127487, 1),
    (127490, 2),
    (127503, 1),
    (127547, 2),
    (127551, 1),
    (127560, 2),
    (127567, 1),
    (127569, 2),
    (127583, 1),
    (127589, 2),
    (127743, 1),
    (127776, 2),
    (127788, 1),
    (127797, 2),
    (127798, 1),
    (127868, 2),
    (127869, 1),
    (127891, 2),
    (127903, 1),
    (127946, 2),
    (127950, 1),
    (127955, 2),
    (127967, 1),
    (127984, 2),
    (127987, 1),
    (127988, 2),
    (127991, 1),
    (128062, 2),
    (128063, 1),
    (128064, 2),
    (128065, 1),
    (128252, 2),
    (128254, 1),
    (128317, 2),
    (128330, 1),
    (128334, 2),
    (128335, 1),
    (128359, 2),
    (128377, 1),
    (128378, 2),
    (128404, 1),
    (128406, 2),
    (128419, 1),
    (128420, 2),
    (128506, 1),
    (128591, 2),
    (128639, 1),
    (128709, 2),
    (128715, 1),
    (128716, 2),
    (128719, 1),
    (128722, 2),
    (128724, 1),
    (128727, 2),
    (128746, 1),
    (128748, 2),
    (128755, 1),
    (128764, 2),
    (128991, 1),
    (129003, 2),
    (129291, 1),
    (129338, 2),
    (129339, 1),
    (129349, 2),
    (129350, 1),
    (129400, 2),
    (129401, 1),
    (129483, 2),
    (129484, 1),
    (129535, 2),
    (129647, 1),
    (129652, 2),
    (129655, 1),
    (129658, 2),
    (129663, 1),
    (129670, 2),
    (129679, 1),
    (129704, 2),
    (129711, 1),
    (129718, 2),
    (129727, 1),
    (129730, 2),
    (129743, 1),
    (129750, 2),
    (131071, 1),
    (173789, 2),
    (173823, 1),
    (177972, 2),
    (177983, 1),
    (178205, 2),
    (178207, 1),
    (183969, 2),
    (183983, 1),
    (191456, 2),
    (194559, 1),
    (195101, 2),
    (196607, 1),
    (201546, 2),
    (917504, 1),
    (917505, 0),
    (917535, 1),
    (917631, 0),
    (917759, 1),
    (917999, 0),
    (1114111, 1),
]

# ACCESSOR FUNCTIONS

def get_width( o ):
    """Return the screen column width for unicode ordinal o."""
    global widths
    if o == 0xe or o == 0xf:
        return 0
    for num, wid in widths:
        if o <= num:
            return wid
    return 1

def decode_one( text, pos ):
    """
    Return (ordinal at pos, next position) for UTF-8 encoded text.
    """
    assert isinstance(text, bytes), text
    b1 = ord2(text[pos])
    if not b1 & 0x80:
        return b1, pos+1
    error = ord("?"), pos+1
    lt = len(text)
    lt = lt-pos
    if lt < 2:
        return error
    if b1 & 0xe0 == 0xc0:
        b2 = ord2(text[pos+1])
        if b2 & 0xc0 != 0x80:
            return error
        o = ((b1&0x1f)<<6)|(b2&0x3f)
        if o < 0x80:
            return error
        return o, pos+2
    if lt < 3:
        return error
    if b1 & 0xf0 == 0xe0:
        b2 = ord2(text[pos+1])
        if b2 & 0xc0 != 0x80:
            return error
        b3 = ord2(text[pos+2])
        if b3 & 0xc0 != 0x80:
            return error
        o = ((b1&0x0f)<<12)|((b2&0x3f)<<6)|(b3&0x3f)
        if o < 0x800:
            return error
        return o, pos+3
    if lt < 4:
        return error
    if b1 & 0xf8 == 0xf0:
        b2 = ord2(text[pos+1])
        if b2 & 0xc0 != 0x80:
            return error
        b3 = ord2(text[pos+2])
        if b3 & 0xc0 != 0x80:
            return error
        b4 = ord2(text[pos+2])
        if b4 & 0xc0 != 0x80:
            return error
        o = ((b1&0x07)<<18)|((b2&0x3f)<<12)|((b3&0x3f)<<6)|(b4&0x3f)
        if o < 0x10000:
            return error
        return o, pos+4
    return error

def decode_one_uni(text, i):
    """
    decode_one implementation for unicode strings
    """
    return ord(text[i]), i+1

def decode_one_right(text, pos):
    """
    Return (ordinal at pos, next position) for UTF-8 encoded text.
    pos is assumed to be on the trailing byte of a utf-8 sequence.
    """
    assert isinstance(text, bytes), text
    error = ord("?"), pos-1
    p = pos
    while p >= 0:
        if ord2(text[p])&0xc0 != 0x80:
            o, next = decode_one( text, p )
            return o, p-1
        p -=1
        if p == p-4:
            return error

def set_byte_encoding(enc):
    assert enc in ('utf8', 'narrow', 'wide')
    global _byte_encoding
    _byte_encoding = enc

def get_byte_encoding():
    return _byte_encoding

def calc_text_pos(text, start_offs, end_offs, pref_col):
    """
    Calculate the closest position to the screen column pref_col in text
    where start_offs is the offset into text assumed to be screen column 0
    and end_offs is the end of the range to search.

    text may be unicode or a byte string in the target _byte_encoding

    Returns (position, actual_col).
    """
    assert start_offs <= end_offs, repr((start_offs, end_offs))
    utfs = isinstance(text, bytes) and _byte_encoding == "utf8"
    unis = not isinstance(text, bytes)
    if unis or utfs:
        decode = [decode_one, decode_one_uni][unis]
        i = start_offs
        sc = 0
        n = 1 # number to advance by
        while i < end_offs:
            o, n = decode(text, i)
            w = get_width(o)
            if w+sc > pref_col:
                return i, sc
            i = n
            sc += w
        return i, sc
    assert type(text) == bytes, repr(text)
    # "wide" and "narrow"
    i = start_offs+pref_col
    if i >= end_offs:
        return end_offs, end_offs-start_offs
    if _byte_encoding == "wide":
        if within_double_byte(text, start_offs, i) == 2:
            i -= 1
    return i, i-start_offs

def calc_width(text, start_offs, end_offs):
    """
    Return the screen column width of text between start_offs and end_offs.

    text may be unicode or a byte string in the target _byte_encoding

    Some characters are wide (take two columns) and others affect the
    previous character (take zero columns).  Use the widths table above
    to calculate the screen column width of text[start_offs:end_offs]
    """

    assert start_offs <= end_offs, repr((start_offs, end_offs))

    utfs = isinstance(text, bytes) and _byte_encoding == "utf8"
    unis = not isinstance(text, bytes)
    if (unis and not SAFE_ASCII_RE.match(text)
            ) or (utfs and not SAFE_ASCII_BYTES_RE.match(text)):
        decode = [decode_one, decode_one_uni][unis]
        i = start_offs
        sc = 0
        n = 1 # number to advance by
        while i < end_offs:
            o, n = decode(text, i)
            w = get_width(o)
            i = n
            sc += w
        return sc
    # "wide", "narrow" or all printable ASCII, just return the character count
    return end_offs - start_offs

def is_wide_char(text, offs):
    """
    Test if the character at offs within text is wide.

    text may be unicode or a byte string in the target _byte_encoding
    """
    if isinstance(text, text_type):
        o = ord(text[offs])
        return get_width(o) == 2
    assert isinstance(text, bytes)
    if _byte_encoding == "utf8":
        o, n = decode_one(text, offs)
        return get_width(o) == 2
    if _byte_encoding == "wide":
        return within_double_byte(text, offs, offs) == 1
    return False

def move_prev_char(text, start_offs, end_offs):
    """
    Return the position of the character before end_offs.
    """
    assert start_offs < end_offs
    if isinstance(text, text_type):
        return end_offs-1
    assert isinstance(text, bytes)
    if _byte_encoding == "utf8":
        o = end_offs-1
        while ord2(text[o])&0xc0 == 0x80:
            o -= 1
        return o
    if _byte_encoding == "wide" and within_double_byte(text,
        start_offs, end_offs-1) == 2:
        return end_offs-2
    return end_offs-1

def move_next_char(text, start_offs, end_offs):
    """
    Return the position of the character after start_offs.
    """
    assert start_offs < end_offs
    if isinstance(text, text_type):
        return start_offs+1
    assert isinstance(text, bytes)
    if _byte_encoding == "utf8":
        o = start_offs+1
        while o<end_offs and ord2(text[o])&0xc0 == 0x80:
            o += 1
        return o
    if _byte_encoding == "wide" and within_double_byte(text,
        start_offs, start_offs) == 1:
        return start_offs +2
    return start_offs+1

def within_double_byte(text, line_start, pos):
    """Return whether pos is within a double-byte encoded character.

    text -- byte string in question
    line_start -- offset of beginning of line (< pos)
    pos -- offset in question

    Return values:
    0 -- not within dbe char, or double_byte_encoding == False
    1 -- pos is on the 1st half of a dbe char
    2 -- pos is on the 2nd half of a dbe char
    """
    assert isinstance(text, bytes)
    v = ord2(text[pos])

    if v >= 0x40 and v < 0x7f:
        # might be second half of big5, uhc or gbk encoding
        if pos == line_start: return 0

        if ord2(text[pos-1]) >= 0x81:
            if within_double_byte(text, line_start, pos-1) == 1:
                return 2
        return 0

    if v < 0x80: return 0

    i = pos -1
    while i >= line_start:
        if ord2(text[i]) < 0x80:
            break
        i -= 1

    if (pos - i) & 1:
        return 1
    return 2

# TABLE GENERATION CODE

def process_east_asian_width():
    import sys
    out = []
    last = None
    for line in sys.stdin.readlines():
        if line[:1] == "#": continue
        line = line.strip()
        hex,rest = line.split(";",1)
        wid,rest = rest.split(" # ",1)
        word1 = rest.split(" ",1)[0]

        if "." in hex:
            hex = hex.split("..")[1]
        num = int(hex, 16)

        if word1 in ("COMBINING","MODIFIER","<control>"):
            l = 0
        elif wid in ("W", "F"):
            l = 2
        else:
            l = 1

        if last is None:
            out.append((0, l))
            last = l

        if last == l:
            out[-1] = (num, l)
        else:
            out.append( (num, l) )
            last = l

    print("widths = [")
    for o in out[1:]:  # treat control characters same as ascii
        print("\t%r," % (o,))
    print("]")

if __name__ == "__main__":
    process_east_asian_width()
