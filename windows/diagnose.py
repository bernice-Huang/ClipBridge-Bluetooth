"""Read-only adapter probe; --advertise briefly tests a real GATT advertisement."""
import argparse
import asyncio
import json
from uuid import UUID

from winrt.windows.devices.bluetooth import BluetoothAdapter, BluetoothError
from winrt.windows.devices.bluetooth.genericattributeprofile import (
    GattServiceProvider, GattServiceProviderAdvertisingParameters,
)

SERVICE_UUID = UUID("8d6b3f00-e815-4c55-b109-45bdffb271f0")


async def probe(advertise=False):
    adapter = await BluetoothAdapter.get_default_async()
    if adapter is None:
        raise RuntimeError("No Bluetooth adapter found.")
    result = {
        "adapter_found": True,
        "central_supported": adapter.is_central_role_supported,
        "peripheral_supported": adapter.is_peripheral_role_supported,
    }
    if not adapter.is_peripheral_role_supported:
        print(json.dumps(result, indent=2))
        return 2
    service = await GattServiceProvider.create_async(SERVICE_UUID)
    result["gatt_error"] = service.error.name
    if service.error != BluetoothError.SUCCESS or service.service_provider is None:
        print(json.dumps(result, indent=2))
        return 3
    provider = service.service_provider
    if advertise:
        parameters = GattServiceProviderAdvertisingParameters()
        parameters.is_connectable = True
        parameters.is_discoverable = True
        provider.start_advertising_with_parameters(parameters)
        try:
            await asyncio.sleep(2)
            result["advertisement_status"] = provider.advertisement_status.name
        finally:
            provider.stop_advertising()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--advertise", action="store_true")
    options = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(probe(options.advertise)))
    except Exception as error:
        print(f"Bluetooth probe failed: {error}")
        raise SystemExit(1)
