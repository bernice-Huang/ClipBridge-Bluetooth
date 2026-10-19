"""WinRT buffer conversion and subscribed-device identity; no BLE startup."""
from winrt.windows.storage.streams import DataReader, DataWriter


def as_buffer(data):
    writer = DataWriter()
    try:
        writer.write_bytes(data)
        return writer.detach_buffer()
    finally:
        writer.close()


def as_bytes(buffer):
    reader = DataReader.from_buffer(buffer)
    try:
        data = bytearray(buffer.length)
        reader.read_bytes(data)
        return bytes(data)
    finally:
        reader.close()


def device_id(session):
    return session.device_id.id
