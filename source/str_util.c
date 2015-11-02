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

static int widths_len = 2*38;
static const int widths[] = {
    126, 1,
    159, 0,
    687, 1,
    710, 0,
    711, 1,
    727, 0,
    733, 1,
    879, 0,
    1154, 1,
    1161, 0,
    4347, 1,
    4447, 2,
    7467, 1,
    7521, 0,
    8369, 1,
    8426, 0,
    9000, 1,
    9002, 2,
    11021, 1,
    12350, 2,
    12351, 1,
    12438, 2,
    12442, 0,
    19893, 2,
    19967, 1,
    55203, 2,
    63743, 1,
    64106, 2,
    65039, 1,
    65059, 0,
    65131, 2,
    65279, 1,
    65376, 2,
    65500, 1,
    65510, 2,
    120831, 1,
    262141, 2,
    1114109, 1
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

    for (i=0; i<widths_len; i+=2)
    {
        if (ord <= widths[i])
            return widths[i+1];
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
    if (ret==-1) //an error occured
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
    if (err==-1) //an error occured
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
