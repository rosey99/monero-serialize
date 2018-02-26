#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Extremely minimal streaming codec for a Monero serialization.

For de-sererializing (loading) protobuf types, object with `AsyncReader`
interface is required:

>>> class AsyncReader:
>>>     async def areadinto(self, buffer):
>>>         """
>>>         Reads `len(buffer)` bytes into `buffer`, or raises `EOFError`.
>>>         """

For serializing (dumping) protobuf types, object with `AsyncWriter` interface is
required:

>>> class AsyncWriter:
>>>     async def awrite(self, buffer):
>>>         """
>>>         Writes all bytes from `buffer`, or raises `EOFError`.
>>>         """
'''

from .protobuf import const, load_uvarint, dump_uvarint, LimitedReader, CountingWriter


_UINT_BUFFER = bytearray(1)


async def load_uint(reader, width):
    buffer = _UINT_BUFFER
    result = 0
    shift = 0
    for _ in range(width):
        await reader.areadinto(buffer)
        result += buffer[0] << shift
        shift += 8
    return result


async def dump_uint(writer, n, width):
    buffer = _UINT_BUFFER
    for _ in range(width):
        buffer[0] = n & 0xff
        await writer.awrite(buffer)
        n >>= 8


def eq_obj_slots(l, r):
    """
    Compares objects with __slots__ defined
    :param l:
    :param r:
    :return:
    """
    for f in l.__slots__:
        if getattr(l, f, None) != getattr(r, f, None):
            return False
    return True


def eq_obj_contents(l, r):
    """
    Compares object contents, supports slots
    :param l:
    :param r:
    :return:
    """
    if l.__class__ is not r.__class__:
        return False
    if hasattr(l, '__slots__'):
        return eq_obj_slots(l, r)
    else:
        return l.__dict__ == r.__dict__


def slot_obj_dict(o):
    """
    Builds dict for o with __slots__ defined
    :param o:
    :return:
    """
    d = {}
    for f in o.__slots__:
        d[f] = getattr(o, f, None)
    return d


class UVarintType:
    WIRE_TYPE = 1


class IntType:
    WIRE_TYPE = 2
    WIDTH = 0
    SIGNED = 0


class BoolType(IntType):
    SIGNED = 0
    WIDTH = 1


class UInt8(IntType):
    SIGNED = 0
    WIDTH = 1


class Int8(IntType):
    SIGNED = 1
    WIDTH = 1


class UInt16(IntType):
    WIRE_TYPE = 2
    WIDTH = 2


class Int16(IntType):
    SIGNED = 1
    WIDTH = 2


class UInt32(IntType):
    SIGNED = 0
    WIDTH = 4


class Int32(IntType):
    SIGNED = 1
    WIDTH = 4


class UInt64(IntType):
    SIGNED = 0
    WIDTH = 8


class Int64(IntType):
    SIGNED = 1
    WIDTH = 8


class BlobType:
    """
    Binary data

    Represented as bytearray() or a list of values in data structures.
    Not wrapped in the BlobType, the BlobType is only a scheme descriptor.
    Behaves in the same way as primitive types

    Supports also the wrapped version (__init__, DATA_ATTR, eq, repr...),
    """
    DATA_ATTR = 'data'
    WIRE_TYPE = 3
    FIX_SIZE = 0
    SIZE = 0

    def __init__(self, *args, **kwargs):
        if len(args) > 1:
            raise ValueError()
        if len(args) > 0:
            setattr(self, self.DATA_ATTR, args[0])

    def __eq__(self, rhs):
        return eq_obj_contents(self, rhs)

    def __repr__(self):
        dct = slot_obj_dict(self) if hasattr(self, '__slots__') else self.__dict__
        return '<%s: %s>' % (self.__class__.__name__, dct)


class UnicodeType:
    WIRE_TYPE = 4


class VariantType:
    """
    Union of types, variant tags needed. is only one of the types. List in typedef, enum.
    Wraps the variant type in order to unambiguously support variant of variants.
    """
    WIRE_TYPE = 5
    FIELDS = []

    def __init__(self, *args, **kwargs):
        self.variant_elem = None
        self.variant_elem_type = None

        fname, fval = None, None
        if len(args) > 0:
            fname, fval = self.find_fdef(args[0])[0], args[0]
        if len(kwargs) > 0:
            key = list(kwargs.keys())[0]
            fname, fval = key, kwargs[key]
        if fname:
            self.set_variant(fname, fval)

    def find_fdef(self, elem):
        for x in self.FIELDS:
            if isinstance(elem, x[1]):
                return x
        raise ValueError('Unrecognized variant')

    def set_variant(self, fname, fvalue):
        self.variant_elem = fname
        self.variant_elem_type = fvalue.__class__
        setattr(self, fname, fvalue)

    def __eq__(self, rhs):
        return eq_obj_contents(self, rhs)

    def __repr__(self):
        dct = slot_obj_dict(self) if hasattr(self, '__slots__') else self.__dict__
        return '<%s: %s>' % (self.__class__.__name__, dct)


class ContainerType:
    """
    Array of elements
    Represented as a real array in the data structures, not wrapped in the ContainerType.
    The Container type is used only as a schema descriptor for serialization.
    """
    WIRE_TYPE = 6
    FIX_SIZE = 0
    SIZE = 0
    ELEM_TYPE = None


class MessageType:
    WIRE_TYPE = 7
    FIELDS = {}

    def __init__(self, **kwargs):
        for kw in kwargs:
            setattr(self, kw, kwargs[kw])

    def __eq__(self, rhs):
        return eq_obj_contents(self, rhs)

    def __repr__(self):
        dct = slot_obj_dict(self) if hasattr(self, '__slots__') else self.__dict__
        return '<%s: %s>' % (self.__class__.__name__, dct)


FLAG_REPEATED = const(1)


class MemoryReaderWriter:

    def __init__(self, buffer=None):
        self.buffer = buffer if buffer else []

    async def areadinto(self, buf):
        ln = len(buf)
        nread = min(ln, len(self.buffer))
        for idx in range(nread):
            buf[idx] = self.buffer.pop(0)
        return nread

    async def awrite(self, buf):
        self.buffer.extend(buf)
        nwritten = len(buf)
        return nwritten


class ElemRefObj:
    pass


class ElemRefArr:
    pass


def gen_elem_array(size, elem_type=None):
    if elem_type is None or not callable(elem_type):
        return [elem_type] * size
    if isinstance(elem_type, ContainerType) or issubclass(elem_type, ContainerType):
        elem_type = lambda: []
    res = []
    for _ in range(size):
        res.append(elem_type())
    return res


def is_elem_ref(elem_ref):
    return elem_ref and isinstance(elem_ref, tuple) and len(elem_ref) == 3 \
           and (elem_ref[0] == ElemRefObj or elem_ref[0] == ElemRefArr)


def get_elem(elem_ref, default=None):
    if not is_elem_ref(elem_ref):
        return elem_ref
    elif elem_ref[0] == ElemRefObj:
        return getattr(elem_ref[1], elem_ref[2], default)
    elif elem_ref[0] == ElemRefArr:
        return elem_ref[1][elem_ref[2]]


def set_elem(elem_ref, elem):
    if elem_ref is None or elem_ref == elem or not is_elem_ref(elem_ref):
        return elem

    elif elem_ref[0] == ElemRefObj:
        setattr(elem_ref[1], elem_ref[2], elem)
        return elem

    elif elem_ref[0] == ElemRefArr:
        elem_ref[1][elem_ref[2]] = elem
        return elem


class Archive(object):
    def __init__(self, iobj, writing=True):
        self.writing = writing
        self.iobj = iobj

    async def tag(self, tag):
        """

        :param tag:
        :return:
        """

    async def prepare_container(self, size, container, elem_type=None):
        """
        Prepares container for serialization
        :param size:
        :param container:
        :return:
        """
        if not self.writing:
            if container is None:
                return gen_elem_array(size, elem_type)

            fvalue = get_elem(container)
            if fvalue is None:
                fvalue = []
            fvalue += gen_elem_array(max(0, size - len(fvalue)), elem_type)
            set_elem(container, fvalue)
            return fvalue

    async def prepare_container_field(self, size, obj, name, elem_type=None):
        """
        Prepares container for serialization
        :param size:
        :param container:
        :param elem_type:
        :return:
        """
        if not self.writing:
            container = getattr(obj, name)
            if container is None:
                setattr(obj, name, gen_elem_array(size, elem_type))
                return

            container += gen_elem_array(max(0, size - len(container)), elem_type)
            return container

    async def uvarint(self, elem):
        """
        Uvarint
        :param elem:
        :return:
        """
        if self.writing:
            return await dump_uvarint(self.iobj, elem)
        else:
            return await load_uvarint(self.iobj)

    async def uint(self, elem, elem_type, params=None):
        """
        Fixed size int
        :param elem:
        :param elem_type:
        :param params:
        :return:
        """
        if self.writing:
            return await dump_uint(self.iobj, elem, elem_type.WIDTH)
        else:
            return await load_uint(self.iobj, elem_type.WIDTH)

    async def unicode_type(self, elem):
        """
        Unicode type
        :param elem:
        :return:
        """
        if self.writing:
            await dump_uvarint(self.iobj, len(elem))
            await self.iobj.awrite(bytes(elem, 'utf8'))
        else:
            ivalue = await load_uvarint(self.iobj)
            fvalue = bytearray(ivalue)
            await self.iobj.areadinto(fvalue)
            fvalue = str(fvalue, 'utf8')
            return fvalue

    async def blob(self, elem=None, elem_type=None, params=None):
        """
        Loads/dumps blob
        :return:
        """
        elem_type = elem_type if elem_type else elem.__class__
        if hasattr(elem_type, 'serialize_archive'):
            elem = elem_type() if elem is None else elem
            return await elem.serialize_archive(self, elem=elem, elem_type=elem_type, params=params)

        if self.writing:
            return await dump_blob(self.iobj, elem=elem, elem_type=elem_type, params=params)
        else:
            return await load_blob(self.iobj, elem_type=elem_type, params=params, elem=elem)

    async def container(self, container=None, container_type=None, params=None):
        """
        Loads/dumps container
        :return:
        """
        if hasattr(container_type, 'serialize_archive'):
            container = container_type() if container is None else container
            return await container.serialize_archive(self, elem=container, elem_type=container_type, params=params)

        if self.writing:
            return await dump_container(self.iobj, container, container_type, params,
                                        field_archiver=self.dump_field)
        else:
            return await load_container(self.iobj, container_type, params=params, container=container,
                                        field_archiver=self.load_field)

    async def variant(self, elem=None, elem_type=None, params=None):
        """
        Loads/dumps variant type
        :param elem:
        :param elem_type:
        :param params:
        :return:
        """
        elem_type = elem_type if elem_type else elem.__class__
        if hasattr(elem_type, 'serialize_archive'):
            elem = elem_type() if elem is None else elem
            return await elem.serialize_archive(self, elem=elem, elem_type=elem_type, params=params)

        if self.writing:
            return await dump_variant(self.iobj, elem=elem,
                                      elem_type=elem_type if elem_type else elem.__class__,
                                      params=params, field_archiver=self.dump_field)
        else:
            return await load_variant(self.iobj, elem_type=elem_type if elem_type else elem.__class__,
                                      params=params, elem=elem, field_archiver=self.load_field)

    async def message(self, msg):
        """
        Loads/dumps message
        :param msg:
        :return:
        """
        elem_type = msg.__class__
        if hasattr(elem_type, 'serialize_archive'):
            msg = elem_type() if msg is None else msg
            return await msg.serialize_archive(self)

        if self.writing:
            return await dump_message(self.iobj, msg, field_archiver=self.dump_field)
        else:
            return await load_message(self.iobj, msg.__class__, msg, field_archiver=self.load_field)

    async def message_field(self, msg, field):
        """
        Dumps/Loads message field
        :param msg:
        :param field:
        :return:
        """
        if self.writing:
            await dump_message_field(self.iobj, msg, field, field_archiver=self.dump_field)
        else:
            await load_message_field(self.iobj, msg, field, field_archiver=self.load_field)

    async def msg_fields(self, msg, fields):
        """
        Load/dump individual message fields
        :param msg:
        :param fields:
        :param field_archiver:
        :return:
        """
        for field in fields:
            await self.message_field(msg, field)
        return msg

    async def rfield(self, elem=None, elem_type=None, params=None):
        """
        Loads/Dumps message field
        :param elem:
        :param elem_type:
        :param params:
        :return:
        """
        if self.writing:
            return await dump_field(self.iobj, elem=elem,
                                    elem_type=elem_type if elem_type else elem.__class__,
                                    params=params)
        else:
            return await load_field(self.iobj,
                                    elem_type=elem_type if elem_type else elem.__class__,
                                    params=params,
                                    elem=elem)

    async def field(self, elem=None, elem_type=None, params=None):
        """
        Archive field
        :param elem:
        :param elem_type:
        :param params:
        :return:
        """
        elem_type = elem_type if elem_type else elem.__class__
        fvalue = None
        if issubclass(elem_type, UVarintType):
            fvalue = await self.uvarint(get_elem(elem))

        elif issubclass(elem_type, IntType):
            fvalue = await self.uint(elem=get_elem(elem), elem_type=elem_type, params=params)

        elif issubclass(elem_type, BlobType):
            fvalue = await self.blob(elem=get_elem(elem), elem_type=elem_type, params=params)

        elif issubclass(elem_type, UnicodeType):
            fvalue = await self.unicode_type(get_elem(elem))

        elif issubclass(elem_type, VariantType):
            fvalue = await self.variant(elem=get_elem(elem), elem_type=elem_type, params=params)

        elif issubclass(elem_type, ContainerType):  # container ~ simple list
            fvalue = await self.container(container=get_elem(elem), container_type=elem_type, params=params)

        elif issubclass(elem_type, MessageType):
            fvalue = await self.message(get_elem(elem))

        else:
            raise TypeError

        return fvalue if self.writing else set_elem(elem, fvalue)

    async def dump_field(self, writer, elem, elem_type, params=None):
        assert self.iobj == writer
        return await self.field(elem=elem, elem_type=elem_type, params=params)

    async def load_field(self, reader, elem_type, params=None, elem=None):
        assert self.iobj == reader
        return await self.field(elem=elem, elem_type=elem_type, params=params)


async def dump_blob(writer, elem, elem_type, params=None):
    if hasattr(elem, 'serialize_dump'):
        return await elem.serialize_dump(writer)
    if not elem_type.FIX_SIZE:
        await dump_uvarint(writer, len(elem))
    data = getattr(elem, BlobType.DATA_ATTR) if isinstance(elem, BlobType) else elem
    await writer.awrite(data)


async def load_blob(reader, elem_type, params=None, elem=None):
    if hasattr(elem_type, 'serialize_load'):
        elem = elem_type() if elem is None else elem
        return await elem.serialize_load(reader)

    ivalue = elem_type.SIZE if elem_type.FIX_SIZE else await load_uvarint(reader)
    fvalue = bytearray(ivalue)
    await reader.areadinto(fvalue)

    if elem is None:
        return fvalue  # array by default

    elif isinstance(elem, BlobType):
        setattr(elem, elem_type.DATA_ATTR, fvalue)
        return elem

    else:
        elem.extend(fvalue)

    return elem


async def dump_container(writer, container, container_type, params=None, field_archiver=None):
    if hasattr(container, 'serialize_dump'):
        return await container.serialize_dump(writer)
    if not container_type.FIX_SIZE:
        await dump_uvarint(writer, len(container))

    field_archiver = field_archiver if field_archiver else dump_field
    elem_type = params[0] if params else None
    if elem_type is None:
        elem_type = container_type.ELEM_TYPE
    for elem in container:
        await field_archiver(writer, elem, elem_type, params[1:] if params else None)


async def load_container(reader, container_type, params=None, container=None, field_archiver=None):
    if hasattr(container_type, 'serialize_load'):
        container = container_type() if container is None else container
        return await container.serialize_load(reader)

    field_archiver = field_archiver if field_archiver else load_field

    c_len = container_type.SIZE if container_type.FIX_SIZE else await load_uvarint(reader)
    if container and c_len != len(container):
        raise ValueError('Size mismatch')

    elem_type = params[0] if params else None
    if elem_type is None:
        elem_type = container_type.ELEM_TYPE

    res = container if container else []
    for i in range(c_len):
        fvalue = await field_archiver(reader, elem_type,
                                      params[1:] if params else None,
                                      (ElemRefArr, res, i) if container else None)
        if not container:
            res.append(fvalue)
    return res


async def dump_message_field(writer, msg, field, field_archiver=None):
    fname = field[0]
    ftype = field[1]
    params = field[2:]

    fvalue = getattr(msg, fname, None)
    field_archiver = field_archiver if field_archiver else dump_field
    await field_archiver(writer, fvalue, ftype, params)


async def load_message_field(reader, msg, field, field_archiver=None):
    fname = field[0]
    ftype = field[1]
    params = field[2:]

    field_archiver = field_archiver if field_archiver else load_field
    await field_archiver(reader, ftype, params, (ElemRefObj, msg, fname))


async def dump_message(writer, msg, field_archiver=None):
    if hasattr(msg, 'serialize_dump'):
        return await msg.serialize_dump(writer)

    mtype = msg.__class__
    fields = mtype.FIELDS

    for field in fields:
        await dump_message_field(writer, msg=msg, field=field, field_archiver=field_archiver)


async def load_message(reader, msg_type, msg=None, field_archiver=None):
    msg = msg_type() if msg is None else msg
    if hasattr(msg_type, 'serialize_load'):
        return await msg.serialize_load(reader)

    for field in msg_type.FIELDS:
        await load_message_field(reader, msg, field, field_archiver=field_archiver)

    return msg


async def dump_variant(writer, elem, elem_type=None, params=None, field_archiver=None):
    if hasattr(elem, 'serialize_dump'):
        return await elem.serialize_dump(writer)

    field_archiver = field_archiver if field_archiver else dump_field
    await dump_uvarint(writer, elem.variant_elem_type.VARIANT_CODE)
    await field_archiver(writer, getattr(elem, elem.variant_elem), elem.variant_elem_type)


async def load_variant(reader, elem_type, params=None, elem=None, field_archiver=None):
    elem = elem_type() if elem is None else elem
    if hasattr(elem_type, 'serialize_load'):
        return await elem.serialize_load(reader)

    field_archiver = field_archiver if field_archiver else load_field
    tag = await load_uvarint(reader)
    for field in elem_type.FIELDS:
        fname = field[0]
        ftype = field[1]
        if ftype.VARIANT_CODE == tag:
            params = field[2:]
            fvalue = await field_archiver(reader, ftype, params)
            elem.set_variant(fname, fvalue)
    return elem


async def dump_field(writer, elem, elem_type, params=None):
    if issubclass(elem_type, UVarintType):
        await dump_uvarint(writer, elem)

    elif issubclass(elem_type, IntType):
        await dump_uint(writer, elem, elem_type.WIDTH)

    elif issubclass(elem_type, BlobType):
        await dump_blob(writer, elem, elem_type, params)

    elif issubclass(elem_type, UnicodeType):
        await dump_uvarint(writer, len(elem))
        await writer.awrite(bytes(elem, 'utf8'))

    elif issubclass(elem_type, VariantType):
        await dump_variant(writer, elem, elem_type, params)

    elif issubclass(elem_type, ContainerType):  # container ~ simple list
        await dump_container(writer, elem, elem_type, params)

    elif issubclass(elem_type, MessageType):
        await dump_message(writer, elem)

    else:
        raise TypeError


async def load_field(reader, elem_type, params=None, elem=None):
    if issubclass(elem_type, UVarintType):
        fvalue = await load_uvarint(reader)
        return set_elem(elem, fvalue)

    elif issubclass(elem_type, IntType):
        fvalue = await load_uint(reader, elem_type.WIDTH)
        return set_elem(elem, fvalue)

    elif issubclass(elem_type, BlobType):
        fvalue = await load_blob(reader, elem_type, params=params, elem=get_elem(elem))
        return set_elem(elem, fvalue)

    elif issubclass(elem_type, UnicodeType):
        ivalue = await load_uvarint(reader)
        fvalue = bytearray(ivalue)
        await reader.areadinto(fvalue)
        fvalue = str(fvalue, 'utf8')
        return set_elem(elem, fvalue)

    elif issubclass(elem_type, VariantType):
        fvalue = await load_variant(reader, elem_type, params=params, elem=get_elem(elem))
        return set_elem(elem, fvalue)

    elif issubclass(elem_type, ContainerType):  # container ~ simple list
        fvalue = await load_container(reader, elem_type, params=params, container=get_elem(elem))
        return set_elem(elem, fvalue)

    elif issubclass(elem_type, MessageType):
        fvalue = await load_message(reader, msg_type=elem_type, msg=get_elem(elem))
        return set_elem(elem, fvalue)

    else:
        raise TypeError


