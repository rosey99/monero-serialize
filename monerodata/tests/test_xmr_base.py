#!/usr/bin/env python
# -*- coding: utf-8 -*-
import random
import base64
import unittest
import pkg_resources

import asyncio
import aiounittest

from .. import xmrserialize as x
from .. import xmrtypes as xmr


__author__ = 'dusanklinec'


class XmrTypesBaseTest(aiounittest.AsyncTestCase):
    """Simple tests"""

    def __init__(self, *args, **kwargs):
        super(XmrTypesBaseTest, self).__init__(*args, **kwargs)

    async def test_simple_msg(self):
        """
        TxinGen
        :return:
        """
        msg = xmr.TxinGen(height=42)

        writer = x.MemoryReaderWriter()
        await x.dump_message(writer, msg)

        test_deser = await x.load_message(x.MemoryReaderWriter(writer.buffer), xmr.TxinGen)
        self.assertEqual(msg.height, test_deser.height)

    async def test_simple_msg_into(self):
        """
        TxinGen
        :return:
        """
        msg = xmr.TxinGen(height=42)

        writer = x.MemoryReaderWriter()
        await x.dump_message(writer, msg)

        msg2 = xmr.TxinGen()
        test_deser = await x.load_message(x.MemoryReaderWriter(writer.buffer), xmr.TxinGen, msg=msg2)
        self.assertEqual(msg.height, test_deser.height)
        self.assertEqual(msg.height, msg2.height)
        self.assertEqual(msg2, test_deser)

    async def test_ecpoint(self):
        """
        Ec point
        :return:
        """
        ec_data = bytearray(range(32))
        writer = x.MemoryReaderWriter()

        await x.dump_blob(writer, ec_data, xmr.ECPoint)
        self.assertTrue(len(writer.buffer), xmr.ECPoint.SIZE)

        test_deser = await x.load_blob(x.MemoryReaderWriter(writer.buffer), xmr.ECPoint)
        self.assertEqual(ec_data, test_deser)

    async def test_ecpoint_obj(self):
        """
        EC point into
        :return:
        """
        ec_data = bytearray(range(32))
        ec_point = xmr.ECPoint(ec_data)
        writer = x.MemoryReaderWriter()

        await x.dump_blob(writer, ec_point, xmr.ECPoint)
        self.assertTrue(len(writer.buffer), xmr.ECPoint.SIZE)

        ec_point2 = xmr.ECPoint()
        test_deser = await x.load_blob(x.MemoryReaderWriter(writer.buffer), xmr.ECPoint, elem=ec_point2)

        self.assertEqual(ec_data, ec_point2.data)
        self.assertEqual(ec_point, ec_point2)

    async def test_txin_to_key(self):
        """
        TxinToKey
        :return:
        """
        msg = xmr.TxinToKey(amount=123, key_offsets=[1, 2, 3, 2**76], k_image=bytearray(range(32)))

        writer = x.MemoryReaderWriter()
        await x.dump_message(writer, msg)

        test_deser = await x.load_message(x.MemoryReaderWriter(writer.buffer), xmr.TxinToKey)
        self.assertEqual(msg.amount, test_deser.amount)
        self.assertEqual(msg, test_deser)




if __name__ == "__main__":
    unittest.main()  # pragma: no cover


