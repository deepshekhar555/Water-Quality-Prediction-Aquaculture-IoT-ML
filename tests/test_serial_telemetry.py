import unittest
from unittest.mock import patch

from aquasensepro.serial_telemetry import SerialTelemetryReader, SketchCSVDecoder


class FakeSerialConnection:
    def __init__(self):
        self.is_open = True
        self.buffer = bytearray()

    @property
    def in_waiting(self):
        return len(self.buffer)

    def read(self, size):
        data = self.buffer[:size]
        del self.buffer[:size]
        return bytes(data)

    def write_lines(self, text):
        self.buffer.extend(text.encode("utf-8"))

    def close(self):
        self.is_open = False


class SketchCSVDecoderTests(unittest.TestCase):
    def test_decodes_current_firmware_header_and_rows(self):
        decoder = SketchCSVDecoder()

        self.assertIsNone(
            decoder.feed_line("sample_id,timestamp_ms,pH,temperature_c,turbidity_ntu")
        )
        row = decoder.feed_line("100,1234,7.10,25.40,32.0")

        self.assertEqual(row["sample_id"], "100")
        self.assertEqual(row["timestamp_ms"], "1234")
        self.assertEqual(row["pH"], "7.10")
        self.assertEqual(row["temperature_c"], "25.40")
        self.assertEqual(row["turbidity_ntu"], "32.0")
        self.assertEqual(decoder.invalid_lines, 0)

    def test_rejects_malformed_rows_and_recovers(self):
        decoder = SketchCSVDecoder()
        decoder.feed_line("sample_id,timestamp_ms,pH,temperature_c,turbidity_ntu")

        self.assertIsNone(decoder.feed_line("broken,row"))
        self.assertEqual(decoder.invalid_lines, 1)
        self.assertIsNotNone(decoder.feed_line("101,2234,7.20,25.50,31.0"))

    def test_accepts_rows_without_header_using_current_firmware_schema(self):
        decoder = SketchCSVDecoder()
        row = decoder.feed_line("102,3234,7.30,25.60,30.0")

        self.assertEqual(row["sample_id"], "102")
        self.assertEqual(row["turbidity_ntu"], "30.0")

    def test_reader_connects_and_buffers_live_rows(self):
        connection = FakeSerialConnection()
        reader = SerialTelemetryReader()

        with patch("serial.Serial", return_value=connection) as serial_constructor:
            reader.connect("COM7", 9600)
            connection.write_lines(
                "sample_id,timestamp_ms,pH,temperature_c,turbidity_ntu\r\n"
                "103,4234,7.40,25.70,29.0\r\n"
            )

            self.assertEqual(reader.poll(), 1)
            serial_constructor.assert_called_once_with("COM7", baudrate=9600, timeout=0)

        self.assertTrue(reader.connected)
        self.assertEqual(reader.rows[-1]["sample_id"], "103")
        self.assertIn("received_at", reader.rows[-1])
        reader.disconnect()
        self.assertFalse(reader.connected)


if __name__ == "__main__":
    unittest.main()