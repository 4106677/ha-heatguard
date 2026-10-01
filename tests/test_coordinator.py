"""Coordinator behavior tests using a minimal HA interface stub."""
import asyncio
import importlib.util
import sys
import types
import unittest
from unittest.mock import patch
import test_protocol

class HAError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.translation = kwargs

class CoordinatorStub:
    def __init__(self, *args, **kwargs):
        self.data = None
        self.published = []
    def async_set_updated_data(self, data):
        self.data = data
        self.published.append(data)

def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result

stubs = {
    'homeassistant': module('homeassistant'),
    'homeassistant.const': module('homeassistant.const', Platform=types.SimpleNamespace(CLIMATE='climate', SENSOR='sensor')),
    'homeassistant.exceptions': module('homeassistant.exceptions', ConfigEntryNotReady=HAError, HomeAssistantError=HAError),
    'homeassistant.helpers': module('homeassistant.helpers'),
    'homeassistant.helpers.update_coordinator': module('homeassistant.helpers.update_coordinator', DataUpdateCoordinator=CoordinatorStub, UpdateFailed=HAError),
    'coordinator_under_test.api': sys.modules['protocol_under_test.api'],
    'coordinator_under_test.parser': sys.modules['protocol_under_test.parser'],
}
if not hasattr(test_protocol.sys.modules['aiohttp'], 'ClientError'):
    test_protocol.sys.modules['aiohttp'].ClientError = type('ClientError', (Exception,), {})
spec = importlib.util.spec_from_file_location('coordinator_under_test', test_protocol.ROOT / '__init__.py', submodule_search_locations=[str(test_protocol.ROOT)])
implementation = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(implementation)

class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.modules = patch.dict(sys.modules, stubs)
        self.modules.start()
        self.addCleanup(self.modules.stop)

    async def test_mode_is_visible_before_server_completes(self):
        started, finish = asyncio.Event(), asyncio.Event()
        async def write(changes):
            started.set()
            await finish.wait()
            return {'settings': {**test_protocol.SETTINGS, **changes}, 'command_pending': True}
        coordinator = implementation.HeatGuardCoordinator(None, None, types.SimpleNamespace(write=write))
        coordinator.data = {'settings': dict(test_protocol.SETTINGS)}
        task = asyncio.create_task(coordinator.write({'id_59':'1', 'id_60':'0'}))
        await started.wait()
        self.assertEqual(coordinator.data['settings']['id_60'], '0')
        self.assertEqual(coordinator.data['settings']['id_59'], '1')
        self.assertTrue(coordinator.data['command_pending'])
        finish.set()
        await task

    async def test_error_restores_previous_mode(self):
        async def write(changes):
            raise test_protocol.RemoteGuardError('rejected')
        coordinator = implementation.HeatGuardCoordinator(None, None, types.SimpleNamespace(write=write))
        original = {'settings': dict(test_protocol.SETTINGS)}
        coordinator.data = original
        with self.assertRaises(HAError):
            await coordinator.write({'id_59':'1'})
        self.assertIs(coordinator.data, original)

    async def test_poll_waits_until_command_finishes(self):
        started, finish = asyncio.Event(), asyncio.Event()
        reads = []
        async def write(changes):
            started.set()
            await finish.wait()
            return {'settings': {**test_protocol.SETTINGS, **changes}}
        async def read():
            reads.append(True)
            return {'settings': dict(test_protocol.SETTINGS)}
        coordinator = implementation.HeatGuardCoordinator(None, None, types.SimpleNamespace(write=write, read=read))
        coordinator.data = {'settings': dict(test_protocol.SETTINGS)}
        command = asyncio.create_task(coordinator.write({'id_59':'1'}))
        await started.wait()
        polling = asyncio.create_task(coordinator._async_update_data())
        await asyncio.sleep(0)
        self.assertEqual(reads, [])
        finish.set()
        await command
        await polling
        self.assertEqual(reads, [True])
